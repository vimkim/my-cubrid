# PR testcase baseline ancestry check

`bin/cubrid-pr-tc-base-check` checks that a CUBRID PR's testcase branches
contain the latest testcase baseline corresponding to the engine PR's
destination branch. This includes `develop`, `feature/<name>`, and other
destination branches. A `develop` PR is checked against testcase `develop`;
it is no longer skipped.

Run it from a CUBRID source worktree to resolve the engine PR and destination
through `gh-pr-info`, or pass `--pr N` to resolve PR N in `CUBRID/cubrid`.

```sh
cubrid-pr-tc-base-check
cubrid-pr-tc-base-check --pr 8094
cubrid-pr-tc-base-check --pr 8094 --base develop --no-pr-links
cubrid-pr-tc-base-check --color=never
```

`bin/cubrid-pr-tc-base-check-oos` fixes the baseline to `feature/oos-merge`:
`cubrid-pr-tc-base-check --base feature/oos-merge [arguments]`.
With `--base` and no `--pr`, a detected PR targeting another destination is
a check error. With both `--base` and `--pr`, engine PR metadata is not
queried and the supplied destination is not verified. TC PR lookup still
runs unless `--no-pr-links` is supplied. The combination
`--pr N --base BRANCH --no-pr-links` requires only Git.

The global just recipes are `tc-base-check` and `tc-base-check-oos`; both
run in the invoking directory and forward their arguments.

## Ancestry rule

The checker fetches origin heads in both testcase repositories and checks
that `origin/<destination>` is an ancestor of `origin/tc/pr-N`. Equality,
rebasing TC changes onto the current baseline, and merging the current
baseline all pass. If testcase `develop` advances after a PR branch is created,
that branch fails until it incorporates the latest `develop` tip.

A stale baseline, divergence, unrelated history, or missing branch fails.
Both repositories are checked even when one fails. Shallow history is a check
error. Missing destination baselines fail rather than falling back to
`develop`. Release baselines can be inspected when their named branches and
`tc/pr-N` exist; the checker does not depend on how the TC branches were created.

Each result includes fetched tip hashes, TC-only/base-only commit counts,
common ancestors, and a terminal Git graph including the common ancestors.
Unrelated histories show both histories. Graph output is not truncated.

## Public and private TC PR links

Each Public/Private section shows testcase PR URLs from the corresponding
`CUBRID/cubrid-testcases` or `CUBRID/cubrid-testcases-private-ex` repository.
The testcase PR number is independent of the engine PR number.

Lookup matches the exact `tc/pr-N` head branch owned by that testcase
repository, excluding similarly named fork branches. Every matching open
PR is shown, with draft status when applicable. If none are open, the most
recently updated merged/closed PR is shown with its state. No matching PR
is reported explicitly. Branch browsing URLs are not printed.

TC PR discovery is best effort. Missing `gh`, authentication problems,
malformed responses, or lookup failures show `URL unavailable` without
changing the ancestry verdict or exit status. Each repository's lookup is
bounded to 30 seconds. `--no-pr-links` disables TC PR discovery; it also
preserves Git-only operation when both `--pr` and `--base` are given.

## Terminal presentation

The report starts with an overall PASS, FAIL, or ERROR result, followed by
Public and Private sections with PR links, branch tips, statuses, counts,
common ancestors, and full Git graphs.

- `--color=auto` (default): colors when stdout is a terminal, `TERM` is not
  `dumb`, and `NO_COLOR` is empty or unset.
- `--color=always`: explicitly enables colors, including in captured output.
- `--color=never`: disables colors, including when an agent uses a terminal.

Piped or redirected output is plain by default. Green indicates PASS, red
indicates FAIL/ERROR, and cyan identifies repository headings. Text statuses
retain their meaning without color. The checker never prompts.

## Paths and side effects

Override repository directories with `CUBRID_TESTCASES_DIR` and
`CUBRID_TESTCASES_PRIVATE_EX_DIR`. Fetches use each directory's `origin`;
TC PR lookup targets the canonical CUBRID testcase repositories.

Only fetched remote-tracking refs and Git fetch metadata change. The checker
never updates local branches or working files, merges, rebases, or pushes.
Results describe each repository at fetch time; the two remotes and GitHub
PR lookups are not an atomic snapshot. Git ancestry cannot prove which named
branch created a TC branch.

Exit status is 0 when both pass, 1 for ancestry failure/missing branch,
and 2 for setup or inspection errors. A check error takes precedence over
status 1. TC PR lookup availability does not change these statuses.

The existing sync checker requires equal tips and can offer to push a
fast-forward; this helper has a different acceptance rule and is check-only.
For the feature branch's own `develop <- feature/<name>` PR, use
`cubrid-feature-tc-sync-check` (OOS wrapper: `cubrid-feature-tc-sync-check-oos`),
which requires equal tips instead.

This helper was previously named `cubrid-pr-tc-oos-check`.

Verification: `python3 tests/test_pr_tc_base_check.py`. Tests use disposable
local Git remotes and stub GitHub lookup; they require no network access.
