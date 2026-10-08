# PR testcase baseline ancestry, URLs, and terminal presentation

Design settled and shared understanding confirmed on 2026-10-08.
Work-tracker item 309. This changes the existing
`cubrid-pr-tc-base-check`; the separate `cubrid-pr-tc-info` is work item 308.

## Baseline ancestry

Use the engine PR's destination branch as the same-named published testcase
baseline in each of the public and private testcase repositories. For example,
an engine PR targeting `develop` compares each repository's `tc/pr-N` with
its latest published `develop` tip. A PR targeting `feature/name` compares
with that repository's `feature/name` tip. The check applies generally to
destination branches; a nonfeature branch name does not cause `SKIP`.

`develop` can advance after a PR testcase branch is created, just as a feature
baseline can. Both therefore require the same ancestry check. The current
feature-only limitation is removed.

After fetching origin heads, require the current testcase baseline tip to be
an ancestor of the PR testcase branch tip. Equality and additional testcase
commits pass. Incorporating the latest baseline by merge or rebase passes.
Stale or divergent history and missing branches fail. Both repositories are
inspected even when one fails. Shallow history remains a check error.

Preserve fetched hashes, TC-only/base-only commit counts, common ancestors,
and full Git graphs for both `develop` and feature baselines. Results describe
each repository at fetch time. Preserve the existing exit meanings: 0 when
both pass, 1 for ancestry failure or missing branches, and 2 for setup or
inspection errors; a check error takes precedence.

Continue fetching each configured directory's `origin` without changing
local branches or working files. Existing environment overrides remain
available. Generalize `--base` validation and help to accept destination
branch names beyond `feature/*`. With both `--pr` and `--base`, engine PR
metadata resolution is bypassed as before; the supplied base is not verified
against GitHub. The OOS wrapper remains a convenience for `feature/oos-merge`.

## Testcase PR URLs

Show testcase pull-request URLs for both `CUBRID/cubrid-testcases` and
`CUBRID/cubrid-testcases-private-ex`, including engine PRs targeting `develop`.
Branch browsing URLs are outside the requested output. Use [the repository
vocabulary](../../CONTEXT.md) to distinguish PR testcase branches from testcase
pull requests, whose numbers are independent of the engine PR number.

Match the exact `tc/pr-N` head branch owned by the canonical testcase
repository. Show every matching open PR. If none are open, show the most
recently updated merged/closed PR, with its state clearly labeled. Report
the absence of a matching PR explicitly.

Discover PR URLs by default, including with `--pr` plus `--base`. Missing
`gh`, unavailable authentication, and lookup errors report that the TC PR
URL is unavailable without changing the ancestry verdict or exit status.
Add `--no-pr-links` to disable discovery. In particular,
`--pr N --base develop --no-pr-links` needs only Git and performs no GitHub
queries. Default URL discovery explicitly changes the old Git-only promise
for `--pr` plus `--base` without this opt-out.

## Presentation

Start with a short overall result. Show separate Public and Private sections
with labeled testcase PR URLs, status words, aligned branch/hash/count details,
common ancestors, and full Git graphs. Status remains understandable without
color. Use the name "Baseline ancestry check" throughout; the check is no
longer limited to feature branches.

Provide `--color=auto|always|never`, defaulting to `auto`. Automatic colors
require stdout to be a terminal, with `TERM` other than `dumb` and without
a nonempty `NO_COLOR`. Captured output is plain by default. Agents using a
terminal can explicitly select `--color=never`. `always` explicitly requests
colors, and `never` disables them. No interactive prompts are needed.

## Verification

Preserve the existing ancestry and local-branch immutability checks. Extend
coverage to current and advanced `develop` baselines, restoration by merge
or rebase, generic `--base` names, testcase PR selection/fallback/unavailability,
the Git-only opt-out, and color behavior for terminal and captured output.
Stub PR discovery so tests using filesystem bare origins remain independent
of GitHub and network access. Check the OOS wrapper still forwards arguments.

## Evidence and workflow

The local CUBRID TC Branch Sync workflow creates `tc/pr-N` branches and draft
TC PRs in both testcase repositories for engine PRs targeting `develop` and
`feature/**`, normally using the engine base branch as the testcase baseline.
Relevant source: `/home/vimkim/gh/cb/develop/.github/workflows/tc-branch-sync.yml`.

The creation workflow can fall back to testcase `develop` when an engine
destination branch is missing. This checker instead reports a missing named
baseline as failure. Release branches use a separate CI workflow; generic
ancestry inspection supports them when their baseline and `tc/pr-N` exist
without assuming the same creation automation. The feature merge PR's separate
equal-tip checker retains its stronger rule.

Implementation includes destination-baseline checks, testcase PR lookup,
terminal color controls, and the report layout described above. Validation
is recorded in the work-tracker item and implementation commit.

Checkout: `/home/vimkim/my-cubrid-pr-tc-base-output`, branch
`feat/pr-tc-base-output`, starting branch and local merge destination `main`.
Local integration requires the user's established merge approval;
no push is authorized.
