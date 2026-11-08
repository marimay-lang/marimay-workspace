<div align="center">
<img src=".github/banner.png" alt="Marimay — a small language, a lot to learn" width="960" />
<p><strong>Open source. Personal. Built to learn and have fun.</strong></p>
</div>

# Marimay workspace

> **Personal learning project.** This repository is part of Marimay, my hobby programming-language project. I maintain it in my spare time to learn by building. APIs and tooling may change, and progress may be intermittent.

This is a small index and a set of local tools for **18 independent repositories**: 17 language and ecosystem repositories, plus the organization's `.github` profile repository. The compiler, editor support, course material, benchmarks, and example applications each keep their own Git history. A GitHub organization groups them; it does not require combining their source trees.

The component list and local layout live in [workspace.json](workspace.json). Child repositories are ignored here. The optional public repository for this index is named `marimay-workspace`; it is additional to the 18 components.

| Area | Local folder | Repositories |
| --- | --- | --- |
| Language | `marimay/` | `marimay` |
| Editors | `editors/` | `tree-sitter-marimay`, `marimay-zed` |
| Examples | `examples/` | Nine CLI examples, `marimay-notes`, `route-planner` |
| Learning | `learning/` | `algorithms-course`, `marimay-first-project` |
| Benchmarks | `benchmarks/` | `algorithm-benchmarks` |
| Community | `community/github-profile/` | `.github` |

Use Python 3.10 or newer and Git. GitHub CLI is needed only for an explicitly executed publication.

```sh
python3 tools/workspace.py inventory
python3 tools/workspace.py check
python3 -m unittest discover -s tests
```

The inventory reports repository identities, commit IDs, counts, and readiness. It omits remote URLs, personal directory names, commit messages, and working-file contents. `check` requires every component to have a clean committed snapshot, a `main` branch at its current commit, a README, and a license. It does not replace compiler tests or the separate publication security review.

The [collection guide](docs/collection.md) covers private bundle exports, tested restoration, and a publication plan. Every command that writes files or contacts GitHub defaults to a dry run and requires `--execute` to act. The organization name is supplied at invocation time.

Deferred experiments and private backups live together under `review-later/`, outside the component manifest. The five experimental worktrees are kept for a later review; none of their features is being integrated into the active language. Private archives are under `review-later/private-archive/`. This entire area is ignored by the workspace repository and rejected by the export tools. Keep full private filesystem backups: Git bundles preserve commits and refs, but cannot preserve uncommitted files, ignored local data, or objects reachable only through reflogs.
