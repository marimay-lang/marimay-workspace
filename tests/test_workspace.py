"""Exercise history preservation and the no-write defaults with real local Git."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "tools/workspace.py"
SPEC = importlib.util.spec_from_file_location("workspace", SCRIPT)
workspace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workspace)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "source"
        self.repo = self.root / "component"
        self.repo.mkdir(parents=True)
        workspace.git(self.repo, "init", "--quiet", "--initial-branch=main")
        workspace.git(self.repo, "config", "user.name", "Workspace Test")
        workspace.git(self.repo, "config", "user.email", "test@example.invalid")
        (self.repo / "README.md").write_text("Fixture\n")
        (self.repo / "LICENSE").write_text("Fixture license\n")
        workspace.git(self.repo, "add", "README.md", "LICENSE")
        workspace.git(self.repo, "commit", "--quiet", "-m", "Initial fixture")
        self.first = workspace.out(self.repo, "rev-parse", "HEAD")
        self.manifest = {"schema_version": 1, "workspace_repository": "collection",
                         "repositories": [{"name": "component", "path": "component"}]}
        workspace.write_json(self.root / "workspace.json", self.manifest)
        self.entries = self.manifest["repositories"]
        self.backup = self.base / "export"

    def invoke(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = workspace.main(["--root", str(self.root), *args])
        return code, output.getvalue()

    def export(self):
        workspace.create_export(self.root, self.backup, self.entries, self.manifest)
        return workspace.load_backup(self.backup)

    def test_dry_export_does_not_write(self):
        code, report = self.invoke("export", "--output", str(self.backup))
        self.assertEqual(code, 0, report)
        self.assertIn('"dry-run"', report)
        self.assertFalse(self.backup.exists())

    def test_dirty_sources_are_rejected_without_export(self):
        (self.repo / "uncommitted.txt").write_text("Preserve this locally\n")
        code, _ = self.invoke("export", "--output", str(self.backup), "--execute")
        self.assertEqual(code, 1)
        self.assertFalse(self.backup.exists())
        self.assertTrue((self.repo / "uncommitted.txt").exists())

    def test_all_refs_roundtrip_and_remote_history_promotion(self):
        workspace.git(self.repo, "checkout", "--quiet", "--detach")
        (self.repo / "evidence.txt").write_text("Separate historical branch\n")
        workspace.git(self.repo, "add", "evidence.txt")
        workspace.git(self.repo, "commit", "--quiet", "-m", "Evidence history")
        remote_commit = workspace.out(self.repo, "rev-parse", "HEAD")
        workspace.git(self.repo, "update-ref", "refs/remotes/origin/evidence/topic", remote_commit)
        workspace.git(self.repo, "checkout", "--quiet", "main")
        workspace.git(self.repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/heads/main")
        workspace.git(self.repo, "tag", "v0.0.1")
        workspace.git(self.repo, "update-ref", "refs/custom/retained", self.first)
        before = workspace.ref_snapshot(self.repo)
        index = self.export()
        self.assertEqual(self.backup.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.backup / "component.bundle").stat().st_mode & 0o777, 0o600)
        target = self.base / "restored"
        workspace.restore_collection(self.backup, target, index)
        repo = target / "component"
        actual = {r["name"]: r for r in workspace.ref_snapshot(repo)}
        for ref in before:
            self.assertEqual(actual[ref["name"]], ref)
        self.assertEqual(workspace.out(repo, "rev-parse", "refs/heads/legacy/remotes/origin/evidence/topic"), remote_commit)
        self.assertEqual(workspace.out(repo, "rev-parse", "HEAD"), self.first)
        self.assertEqual(workspace.ref_snapshot(self.repo), before)
        workspace.publication_ready(repo, index["repositories"][0])

    def test_checksum_change_is_rejected(self):
        self.export()
        with (self.backup / "component.bundle").open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaises(workspace.WorkspaceError):
            workspace.load_backup(self.backup)

    def test_restore_and_publish_dry_runs_never_start_network_or_mutate(self):
        index = self.export()
        target = self.base / "dry-restored"
        with mock.patch.object(workspace, "restore_collection", side_effect=AssertionError("unexpected write")):
            code, report = self.invoke("restore", "--backup", str(self.backup), "--destination", str(target))
        self.assertEqual(code, 0, report)
        self.assertFalse(target.exists())
        with mock.patch.object(workspace, "run", side_effect=AssertionError("unexpected subprocess")):
            report = workspace.publish(self.backup, index, "example-organization", False)
        self.assertEqual(report["mode"], "dry-run")

    def test_private_and_escaping_manifest_paths_are_rejected(self):
        for value in ("../outside", "/absolute", ".local-archive/repo", "nested/.git", "review-later/repo", "review-later/private-archive/repo", "nested/private-archive/repo"):
            with self.subTest(value=value), self.assertRaises(workspace.WorkspaceError):
                workspace.validate_entries([{"name": "component", "path": value}])

    def test_profile_component_and_optional_workspace_are_valid(self):
        entries = [{"name": ".github", "path": "community/github-profile"},
                   {"name": "collection", "path": ".", "workspace": True}]
        self.assertEqual(workspace.validate_entries(entries), entries)

    def test_optional_workspace_roundtrip_keeps_child_independent(self):
        workspace.git(self.root, "init", "--quiet", "--initial-branch=main")
        workspace.git(self.root, "config", "user.name", "Workspace Test")
        workspace.git(self.root, "config", "user.email", "test@example.invalid")
        (self.root / "README.md").write_text("Workspace fixture\n")
        (self.root / "LICENSE").write_text("Fixture license\n")
        (self.root / ".gitignore").write_text("/component/\n")
        workspace.git(self.root, "add", "workspace.json", "README.md", "LICENSE", ".gitignore")
        workspace.git(self.root, "commit", "--quiet", "-m", "Workspace index")
        manifest, entries = workspace.manifest_at(self.root, True)
        workspace.create_export(self.root, self.backup, entries, manifest)
        index = workspace.load_backup(self.backup)
        target = self.base / "restored-with-index"
        workspace.restore_collection(self.backup, target, index)
        self.assertEqual(workspace.out(target, "rev-parse", "--show-toplevel"), str(target))
        self.assertEqual(workspace.out(target / "component", "rev-parse", "--show-toplevel"), str(target / "component"))
        self.assertEqual(workspace.out(target, "status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
