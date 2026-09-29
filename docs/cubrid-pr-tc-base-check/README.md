# PR testcase feature-base ancestry check

`bin/cubrid-pr-tc-base-check` checks that a CUBRID PR targeting
`feature/<name>` has testcase branches built on that feature's testcase
baseline. Run it from a CUBRID source worktree to resolve the PR and its base
with `gh pr view`, or pass `--pr N` to resolve PR N in `CUBRID/cubrid`.
A PR whose base is not `feature/*` (for example `develop`) is reported as
`SKIP` with exit status 0.

`bin/cubrid-pr-tc-base-check-oos` is the `feature/oos-merge` wrapper:
`cubrid-pr-tc-base-check --base feature/oos-merge [--pr N]`. With `--base` and
no `--pr`, a detected PR targeting another base is a check error. With both
`--base` and `--pr`, GitHub is not queried, so only Git is required and the PR
base is not verified. The global just recipes are `tc-base-check` and
`tc-base-check-oos`; both run in the invoking directory.

The checker fetches origin heads in both testcase repositories and checks that
`origin/feature/<name>` is an ancestor of `origin/tc/pr-N`. Equality, rebasing
TC changes onto the current baseline, and merging the current baseline all pass.
A stale baseline, divergence, unrelated history, or missing branch fails. Both
repositories are checked even when one fails. Shallow history is a check error.

Each result includes fetched tip hashes, TC-only/base-only commit counts, common
ancestors, and a terminal Git graph including the common ancestors. Unrelated
histories show both histories. Graph output is not truncated.

Only fetched remote-tracking refs and Git fetch metadata change. The checker
never updates local branches or working files, merges, rebases, or pushes.
Results describe each repository at fetch time; the two remotes are not an atomic
snapshot. Git ancestry cannot prove which named branch created a TC branch.

Repository paths follow `cubrid-pr-tc-sync-check`: override with
`CUBRID_TESTCASES_DIR` and `CUBRID_TESTCASES_PRIVATE_EX_DIR`.
Exit status is 0 when both pass or the check is skipped, 1 for ancestry
failure/missing branch, and 2 for setup or inspection errors. A check error
takes precedence over status 1.

The existing sync checker requires equal tips and can offer to push a
fast-forward; this helper has a different acceptance rule and is check-only.
The existing OOS sync wrapper remains specific to PR 7990.

This helper was previously named `cubrid-pr-tc-oos-check`.

Verification: `python3 tests/test_pr_tc_base_check.py`.
