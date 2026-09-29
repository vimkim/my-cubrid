# PR testcase OOS ancestry check

Run `bin/cubrid-pr-tc-oos-check` from a CUBRID source worktree to resolve its PR
with `gh pr view`, or run `bin/cubrid-pr-tc-oos-check --pr 7990` from anywhere.
The default requires authenticated GitHub CLI; the explicit number only requires Git.

The checker fetches origin heads in both testcase repositories and checks that
`origin/feature/oos-merge` is an ancestor of `origin/tc/pr-N`. Equality, rebasing
TC changes onto the current baseline, and merging the current baseline all pass.
A stale baseline, divergence, unrelated history, or missing branch fails. Both
repositories are checked even when one fails. Shallow history is a check error.

Each result includes fetched tip hashes, TC-only/OOS-only commit counts, common
ancestors, and a terminal Git graph including the common ancestors. Unrelated
histories show both histories. Graph output is not truncated.

Only fetched remote-tracking refs and Git fetch metadata change. The checker
never updates local branches or working files, merges, rebases, or pushes.
Results describe each repository at fetch time; the two remotes are not an atomic
snapshot. Git ancestry cannot prove which named branch created a TC branch.

Repository paths follow `cubrid-pr-tc-sync-check`: override with
`CUBRID_TESTCASES_DIR` and `CUBRID_TESTCASES_PRIVATE_EX_DIR`.
Exit status is 0 when both pass, 1 for ancestry failure/missing branch, and 2 for
setup or inspection errors. A check error takes precedence over status 1.

The existing sync checker requires equal tips and can offer to push a
fast-forward; this helper has a different acceptance rule and is check-only.
The existing OOS sync wrapper remains specific to PR 7990.

Verification: `python3 tests/test_pr_tc_oos_check.py`.
