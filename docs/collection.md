# Collect, restore, and publish the workspace

> **Personal learning project.** This repository is part of Marimay, my hobby programming-language project. I maintain it in my spare time to learn by building. APIs and tooling may change, and progress may be intermittent.

## Local layout

The compiler stays in `marimay/`. Independent component repositories are grouped
under `editors/`, `examples/`, `learning/`, `benchmarks/`, and `community/`.
`workspace.json` records their exact relative paths. Root documentation, tools,
and tests belong to this small workspace repository.

`review-later/` is local and private. It contains the five deferred experimental
worktrees and `private-archive/`, which holds the original checkout, complete
filesystem backups, recovery evidence, and private local data. These are not
part of the current implementation. Keep them until a separate review decides
what to retain or remove; no feature is cherry-picked by this layout change.

## Before an export

Keep a separate private filesystem backup containing complete `.git` directories, ignored files, untracked files, and local application data. Retain those backups after publication. A bundle is an additional portable history export, not a replacement for that backup.

Finish each repository's preparation and validation, then commit its reviewed source snapshot. Preserve historical branches before advancing `main`. `check` verifies the mechanical preconditions; it does not decide whether source, historical commits, licenses, or examples are ready for public release.

```sh
python3 tools/workspace.py check
```

The tools select only manifest entries. They do not recursively discover and publish arbitrary local Git directories. Archives and experimental copies stay private under `review-later/`; they are not active language features or publication sources. The five experimental worktrees remain intact for a separate decision about retaining, integrating, or deleting them later.

## Export all named histories

Choose an export directory outside the component repositories. The directory must not exist. Paths below are placeholders for locations you choose locally.

```sh
python3 tools/workspace.py export --output /path/to/private/export
python3 tools/workspace.py export --output /path/to/private/export --execute
```

For each component, the tool runs `git bundle create ... --all`, verifies the bundle, restores it in a temporary clean directory, and checks every recorded ref and commit ID. It writes a JSON index with bundle checksums and a copy of the portable workspace manifest. The operation stops if a source is dirty, unborn, shallow, missing, or not an independent repository. It does not initialize, commit, change remotes, or update refs in a source repository.

Local branches, tags, remote-tracking refs, and other named refs are included. Detached `HEAD` is recorded too. Symbolic refs are reconstructed. Remote-tracking commit refs receive additional local `legacy/remotes/...` branches in the restored copy so their histories can be pushed later. Original ref names and hashes remain available. A ref-name conflict stops restoration rather than overwriting a different history.

Git bundles omit working-tree changes, ignored files, reflog-only objects, and empty unborn repositories. An export never reads `review-later/` or `review-later/private-archive/`. Bundle files may contain historical content, so keep the export private until its contents have passed the separate review.

Add `--include-workspace` to export this small index repository as an additional nineteenth repository. Its own commit must be clean too.

## Restore without network access

```sh
python3 tools/workspace.py restore --backup /path/to/private/export --destination /path/to/new-workspace
python3 tools/workspace.py restore --backup /path/to/private/export --destination /path/to/new-workspace --execute
```

The destination must not exist. Restoration checks bundle checksums and advertised refs before importing them. It reconstructs the original layout, every recorded ref, and the selected working commit. It creates no publication remotes. A successful restore is assembled in a temporary sibling directory and moved into place only after verification. A failed temporary restore is removed.

Restore this index repository separately, or use an export made with `--include-workspace`, if you also need the root README and tools. Component sources always remain separate Git repositories; this index must not track them as nested repositories or submodules.

## Plan publication to the organization

Pass the actual GitHub organization name, such as `marimay-lang`. No owner is stored in the manifest.

```sh
python3 tools/workspace.py publish --backup /path/to/private/export --owner YOUR_ORGANIZATION
```

This prints the proposed public repository URLs, branch and tag counts, and default branch. It makes no GitHub requests and writes nothing. The plan includes only the repositories in that export; use the optional workspace export above to include this index.

After reviewing the exact export and its historical contents, publication can be explicitly executed:

```sh
python3 tools/workspace.py publish --backup /path/to/private/export --owner YOUR_ORGANIZATION --execute
```

Execution requires an authenticated `gh` and working GitHub Git authentication. It restores the verified export into temporary local repositories, creates missing public GitHub repositories, pushes branches and tags without force, and sets `main` as the default branch. It does not change source remotes. Existing incompatible remote branches cause a push failure; they are not overwritten. Publication can stop partway through a collection, so its result reports which repositories completed.

Only branches and tags are pushed. Restoration preserves all other refs locally. Publication refuses an export containing additional commit histories reachable only through non-branch, non-tag refs; give those reviewed histories explicit branches before exporting. Remote-tracking histories already receive preservation branches during restoration.

No command uploads private filesystem archives, local databases, dirty files, or experimental worktrees. The tool does not run a security scanner automatically: use the project's separate review process before passing `--execute`.
