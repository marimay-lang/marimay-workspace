# Collection preparation — 2026-11-08

This workspace organizes Marimay as a personal MIT-licensed open-source learning
project. The compiler, editor tools, examples, learning material, benchmarks,
and community profile remain independent repositories.

## Local layout and recovery

The active compiler checkout is `marimay/`. Editors, examples, learning projects,
benchmarks and community files have separate named directories recorded in
`workspace.json`. GitHub groups the published repositories under
[marimay-lang](https://github.com/marimay-lang).

Five experimental worktrees and private recovery material are retained in the
local `review-later/` directory for a future decision. They are excluded from
Git, exports and publication; moving them did not integrate experimental
language features. Original filesystem backups include ignored local data,
untracked files, reflogs, stashes and all Git objects, including unreachable ones.
The public bundle export is an additional reproducibility tool, not a substitute
for those private recovery copies.

## History and privacy

The 16 companion repositories retain all 109 commits reachable at preparation
snapshot time, with every parent edge checked before and after sanitization.
Additional remote-only histories were promoted to explicit preservation branches.
Public histories remove exact private paths, internal host details, personal email
addresses and private instruction files. Contributor display names are retained.
Exact original histories and old-to-new commit maps remain in the private archive.
The already-public compiler history was retained without rewriting it.

Repository descriptions, README files, banners and supporting documentation use
English and describe the hobby and learning scope. Existing multilingual program
messages and Unicode test fixtures remain intentional application behavior.
Original code and documentation carry the MIT License; third-party material keeps
its own terms.

Historical benchmark artifacts were anonymized without changing measurements.
Their linked checksums were updated to identify the public artifact bytes; see
[benchmark provenance](https://github.com/marimay-lang/algorithm-benchmarks/blob/main/benchmarks/results/PUBLICATION-PROVENANCE.md).
Old measurement reports do not establish current performance or release readiness.

## Validation scope

On macOS ARM64, the relocated C17 compiler builds and passes all 89 debug CTest
entries. Architecture, roadmap and C-memory-policy gates pass. The 13 Marimay
application and learning repositories pass canonical formatting, type checks and
VM/native tests. Two course examples were updated to the accepted `for ... in`
and match-arm syntax; no compiler language semantics were changed.

The Tree-sitter corpus, query checks, invalid fixtures and compiler formatter
checks pass. Zed queries pass against that grammar. The benchmark Python suite
passes 105 tests. The workspace export and restore tooling passes eight real-Git
fixture tests, including checksum failures, extra histories, clean snapshots,
private-directory rejection and restoration of independent nested repositories.

Gitleaks 8.30.1 is used for redacted Git-history and reviewed-source scans. Scanning
is evidence of those checks, not a guarantee that every possible secret or
vulnerability is absent. GitHub repositories enable secret scanning, push
protection and private vulnerability reporting. CI workflows are configured for
published main branches; a configured or queued workflow is not a passing result.
Local results are not Tier 1 cross-platform release verification.
