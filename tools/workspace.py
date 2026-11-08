#!/usr/bin/env python3
"""Manage an explicit collection of independent Git repositories."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile


class WorkspaceError(Exception):
    """An actionable failure whose text is safe to include in a report."""


def run(argv, cwd=None, *, allow_failure=False, user_config=False):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("GIT_"):
            env.pop(key)
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    if Path(argv[0]).name == "gh":
        env["GH_HOST"] = "github.com"
    if not user_config:
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    try:
        result = subprocess.run(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=False)
    except OSError as exc:
        raise WorkspaceError(f"Cannot start required tool: {Path(argv[0]).name}") from exc
    if result.returncode and not allow_failure:
        # Command stderr may contain private URLs, local paths, or credentials.
        raise WorkspaceError(f"{Path(argv[0]).name} operation failed (exit {result.returncode})")
    return result


def git(path, *args, **kwargs):
    return run(["git", "-c", f"core.hooksPath={os.devnull}", "-C", str(path), *args], **kwargs)


def out(path, *args):
    return git(path, *args).stdout.decode("utf-8").strip()


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise WorkspaceError("Cannot read a valid JSON manifest or export index") from exc


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_name(value):
    return isinstance(value, str) and (value == ".github" or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", value))


def validate_entries(entries):
    if not isinstance(entries, list) or not entries:
        raise WorkspaceError("The repository list is empty or invalid")
    names, paths = set(), set()
    for item in entries:
        name, raw = item.get("name"), item.get("path")
        if not safe_name(name) or not isinstance(raw, str) or "\\" in raw:
            raise WorkspaceError("Invalid repository name or path")
        path = PurePosixPath(raw)
        if path.is_absolute() or ".." in path.parts or any(p.startswith(".") and p != ".github-profile" for p in path.parts):
            raise WorkspaceError("Repository paths must be public relative component paths")
        if any(p in {"review-later", "private-archive"} for p in path.parts):
            raise WorkspaceError("Deferred work and private archives cannot be component repositories")
        if raw == "." and item.get("workspace") is not True:
            raise WorkspaceError("Only the workspace entry may use the root path")
        if name in names or raw in paths:
            raise WorkspaceError("Duplicate repository name or path")
        names.add(name)
        paths.add(raw)
    # Component Git repositories cannot contain one another.
    components = [PurePosixPath(p) for p in paths if p != "."]
    for a in components:
        if any(a != b and a in b.parents for b in components):
            raise WorkspaceError("Component repository paths overlap")
    return entries


def manifest_at(root, include_workspace=False):
    manifest = read_json(root / "workspace.json")
    if manifest.get("schema_version") != 1:
        raise WorkspaceError("Unsupported workspace schema")
    entries = list(manifest.get("repositories", []))
    if include_workspace:
        entries.append({"name": manifest.get("workspace_repository"), "path": ".", "workspace": True})
    return manifest, validate_entries(entries)


def component_path(root, item):
    path = (root / item["path"]).resolve()
    if not path.is_relative_to(root.resolve()):
        raise WorkspaceError("A component path escapes the workspace")
    return path


def ref_snapshot(path):
    text = out(path, "for-each-ref", "--format=%(refname)%09%(objectname)%09%(symref)")
    refs = []
    for line in text.splitlines():
        fields = line.split("\t")
        refs.append({"name": fields[0], "oid": fields[1], "symbolic": fields[2] if len(fields) > 2 else ""})
    return refs


def inspect(root, item):
    path = component_path(root, item)
    result = {"name": item["name"], "path": item["path"], "ready": False}
    if not path.is_dir():
        return {**result, "reason": "missing directory"}
    top = git(path, "rev-parse", "--show-toplevel", allow_failure=True)
    if top.returncode or Path(os.fsdecode(top.stdout).strip()).resolve() != path:
        return {**result, "reason": "not an independent Git repository"}
    head = git(path, "rev-parse", "--verify", "HEAD", allow_failure=True)
    if head.returncode:
        return {**result, "reason": "no committed snapshot"}
    dirty = bool(git(path, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout)
    shallow = out(path, "rev-parse", "--is-shallow-repository") == "true"
    main = git(path, "rev-parse", "--verify", "refs/heads/main", allow_failure=True)
    oid = head.stdout.decode().strip()
    licenses = any((path / n).is_file() for n in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"))
    readme = (path / "README.md").is_file()
    refs = ref_snapshot(path)
    problems = []
    if dirty:
        problems.append("uncommitted files")
    if shallow:
        problems.append("shallow history")
    if main.returncode or main.stdout.decode().strip() != oid:
        problems.append("main is not the current snapshot")
    if not readme:
        problems.append("missing README")
    if not licenses:
        problems.append("missing license")
    return {**result, "head": oid, "dirty": dirty, "shallow": shallow,
            "ref_count": len(refs), "ready": not problems, "problems": problems}


def load_backup(path):
    index = read_json(path / "collection.json")
    if index.get("schema_version") != 1:
        raise WorkspaceError("Unsupported export schema")
    validate_entries(index.get("repositories"))
    for item in index["repositories"]:
        bundle = path / (item["name"] + ".bundle")
        if bundle.is_symlink() or not bundle.is_file() or digest(bundle) != item.get("sha256"):
            raise WorkspaceError(f"Bundle checksum mismatch: {item['name']}")
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", item.get("head", "")):
            raise WorkspaceError("Invalid exported commit ID")
        refs = item.get("refs")
        if not isinstance(refs, list):
            raise WorkspaceError("Invalid exported refs")
        names = set()
        for ref in refs:
            name, oid = ref.get("name", ""), ref.get("oid", "")
            if not name.startswith("refs/") or name in names or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid):
                raise WorkspaceError("Invalid exported ref identity")
            names.add(name)
            if run(["git", "check-ref-format", name], allow_failure=True).returncode:
                raise WorkspaceError("Invalid exported ref name")
            if ref.get("symbolic") and run(["git", "check-ref-format", ref["symbolic"]], allow_failure=True).returncode:
                raise WorkspaceError("Invalid exported symbolic target")
        if item.get("head_ref") and item["head_ref"] not in names:
            raise WorkspaceError("Exported HEAD names an absent ref")
    return index


def add_preservation_branch(path, name, oid):
    ref = "refs/heads/legacy/remotes/" + name.removeprefix("refs/remotes/")
    existing = git(path, "rev-parse", "--verify", ref, allow_failure=True)
    if not existing.returncode and existing.stdout.decode().strip() != oid:
        raise WorkspaceError("A preservation branch conflicts with an existing history")
    git(path, "update-ref", ref, oid)


def restore_repo(backup, destination, item):
    destination.mkdir(parents=True)
    git(destination, "init", "--quiet", "--initial-branch=workspace-restore-unused")
    bundle = (backup / (item["name"] + ".bundle")).resolve()
    git(destination, "bundle", "verify", str(bundle))
    if item["refs"]:
        git(destination, "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "--no-recurse-submodules",
            str(bundle), "+refs/*:refs/*")
    else:
        git(destination, "fetch", "--quiet", "--no-write-fetch-head", str(bundle), "HEAD")
    for ref in item["refs"]:
        if ref["symbolic"]:
            git(destination, "symbolic-ref", ref["name"], ref["symbolic"])
    actual = {r["name"]: r for r in ref_snapshot(destination)}
    for ref in item["refs"]:
        if actual.get(ref["name"]) != ref:
            raise WorkspaceError(f"Restored ref verification failed: {item['name']}")
    git(destination, "cat-file", "-e", item["head"] + "^{commit}")
    for ref in item["refs"]:
        if ref["name"].startswith("refs/remotes/") and not ref["symbolic"]:
            if out(destination, "cat-file", "-t", ref["oid"]) == "commit":
                add_preservation_branch(destination, ref["name"], ref["oid"])
    if item.get("head_ref", "").startswith("refs/heads/"):
        git(destination, "symbolic-ref", "HEAD", item["head_ref"])
        git(destination, "reset", "--quiet", "--hard", "HEAD")
    else:
        git(destination, "checkout", "--quiet", "--detach", item["head"])
    if out(destination, "rev-parse", "HEAD") != item["head"]:
        raise WorkspaceError("Restored working commit does not match its snapshot")
    git(destination, "fsck", "--full", "--no-dangling", "--no-progress")


def create_export(root, destination, entries, manifest):
    if destination.exists():
        raise WorkspaceError("Export destination already exists")
    readiness = [inspect(root, item) for item in entries]
    if any(not item["ready"] for item in readiness):
        raise WorkspaceError("Export requires clean, committed, licensed repositories with current main")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".workspace-export-", dir=destination.parent) as temporary:
        stage = Path(temporary) / "export"
        stage.mkdir(mode=0o700)
        records = []
        for item in entries:
            source = component_path(root, item)
            record = {**item, "head": out(source, "rev-parse", "HEAD"), "refs": ref_snapshot(source)}
            symbolic = git(source, "symbolic-ref", "-q", "HEAD", allow_failure=True)
            record["head_ref"] = symbolic.stdout.decode().strip() if not symbolic.returncode else ""
            git(source, "bundle", "create", str(stage / (item["name"] + ".bundle")), "--all")
            record["sha256"] = digest(stage / (item["name"] + ".bundle"))
            with tempfile.TemporaryDirectory(prefix="restore-test-", dir=temporary) as test:
                restore_repo(stage, Path(test) / "repo", record)
            # Ref and status rechecks detect normal concurrent source edits.
            if ref_snapshot(source) != record["refs"] or inspect(root, item) != next(r for r in readiness if r["name"] == item["name"]):
                raise WorkspaceError("A source repository changed during export; retry after edits finish")
            records.append(record)
        write_json(stage / "workspace.json", manifest)
        write_json(stage / "collection.json", {"schema_version": 1, "repositories": records,
                                               "restore_test": "passed"})
        for exported in stage.iterdir():
            exported.chmod(0o600)
        stage.rename(destination)
    return {"mode": "executed", "operation": "export", "repositories": len(entries), "restore_test": "passed"}


def restore_collection(backup, destination, index):
    if destination.exists():
        raise WorkspaceError("Restore destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".workspace-restore-", dir=destination.parent) as temporary:
        stage = Path(temporary) / "workspace"
        stage.mkdir()
        for item in sorted(index["repositories"], key=lambda x: x["path"] != "."):
            target = stage if item["path"] == "." else stage / item["path"]
            # The root exists to contain component repositories.
            if item["path"] == ".":
                stage.rmdir()
            restore_repo(backup, target, item)
        if not (stage / "workspace.json").exists():
            shutil.copyfile(backup / "workspace.json", stage / "workspace.json")
        stage.rename(destination)
    return {"mode": "executed", "operation": "restore", "repositories": len(index["repositories"])}


def publication_ready(path, item):
    main = git(path, "rev-parse", "--verify", "refs/heads/main", allow_failure=True)
    if main.returncode or main.stdout.decode().strip() != item["head"]:
        raise WorkspaceError("Publication requires main to identify the exported snapshot")
    public = set(out(path, "rev-list", "--branches", "--tags").splitlines())
    all_named = set(out(path, "rev-list", "--all").splitlines())
    if not all_named.issubset(public):
        raise WorkspaceError("Additional histories need explicit publication branches before export")


def publish(backup, index, owner, execute):
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", owner):
        raise WorkspaceError("Invalid GitHub organization name")
    plans = []
    for item in index["repositories"]:
        refs = item["refs"]
        if not any(r["name"] == "refs/heads/main" and r["oid"] == item["head"] for r in refs):
            raise WorkspaceError("Publication requires current main in every exported repository")
        plans.append({"name": item["name"], "url": f"https://github.com/{owner}/{item['name']}",
                      "default_branch": "main", "visibility": "public",
                      "branches": sum(r["name"].startswith("refs/heads/") for r in refs),
                      "tags": sum(r["name"].startswith("refs/tags/") for r in refs),
                      "extra_remote_refs": sum(r["name"].startswith("refs/remotes/") and not r["symbolic"] for r in refs)})
    if not execute:
        return {"mode": "dry-run", "operation": "publish", "repositories": plans}
    completed = []
    with tempfile.TemporaryDirectory(prefix="marimay-publish-") as temporary:
        stage = Path(temporary)
        # Verify the entire collection before the first network operation.
        for item in index["repositories"]:
            restore_repo(backup, stage / item["name"], item)
            publication_ready(stage / item["name"], item)
        for item in index["repositories"]:
            target = f"{owner}/{item['name']}"
            try:
                view = run(["gh", "repo", "view", target, "--json", "nameWithOwner"], allow_failure=True, user_config=True)
                if view.returncode:
                    run(["gh", "repo", "create", target, "--public", "--description", "Part of the Marimay hobby programming-language project"], user_config=True)
                repo = stage / item["name"]
                specs = ["refs/heads/*:refs/heads/*"]
                if any(r["name"].startswith("refs/tags/") for r in item["refs"]):
                    specs.append("refs/tags/*:refs/tags/*")
                git(repo, "push", "--atomic", f"https://github.com/{target}.git", *specs, user_config=True)
                run(["gh", "repo", "edit", target, "--default-branch", "main"], user_config=True)
                completed.append(item["name"])
            except WorkspaceError as exc:
                raise WorkspaceError(f"Publication stopped; completed {len(completed)} repositories: {', '.join(completed) or 'none'}. {exc}") from exc
    return {"mode": "executed", "operation": "publish", "completed": completed}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inventory", "check", "export"):
        sub = commands.add_parser(name)
        sub.add_argument("--include-workspace", action="store_true")
        if name == "export":
            sub.add_argument("--output", required=True, type=Path)
            sub.add_argument("--execute", action="store_true")
    sub = commands.add_parser("restore")
    sub.add_argument("--backup", required=True, type=Path)
    sub.add_argument("--destination", required=True, type=Path)
    sub.add_argument("--execute", action="store_true")
    sub = commands.add_parser("publish")
    sub.add_argument("--backup", required=True, type=Path)
    sub.add_argument("--owner", required=True)
    sub.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command in ("inventory", "check", "export"):
            root = args.root.resolve()
            manifest, entries = manifest_at(root, args.include_workspace)
            readiness = [inspect(root, item) for item in entries]
            report = {"operation": args.command, "repositories": readiness}
            if args.command == "export":
                output = args.output.resolve()
                if output.exists() or any(output.is_relative_to(component_path(root, item)) for item in entries):
                    raise WorkspaceError("Export needs a new destination outside source repositories")
                report = create_export(root, output, entries, manifest) if args.execute else {**report, "mode": "dry-run"}
            print(json.dumps(report, indent=2))
            return 1 if args.command == "check" and any(not r["ready"] for r in readiness) else 0
        backup = args.backup.resolve()
        index = load_backup(backup)
        if args.command == "restore":
            destination = args.destination.resolve()
            if destination.exists():
                raise WorkspaceError("Restore destination already exists")
            report = restore_collection(backup, destination, index) if args.execute else {"mode": "dry-run", "operation": "restore", "repositories": len(index["repositories"])}
        else:
            report = publish(backup, index, args.owner, args.execute)
        print(json.dumps(report, indent=2))
        return 0
    except WorkspaceError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"error": "Workspace operation failed; check permissions and manifest structure"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
