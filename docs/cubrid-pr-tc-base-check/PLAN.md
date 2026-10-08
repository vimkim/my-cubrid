# TC URLs and terminal presentation

Design interview in progress, 2026-10-08. Work-tracker item 309.
This document records the `grill-with-docs` interview for the existing
`cubrid-pr-tc-base-check`; implementation awaits confirmation of shared
understanding. The separate `cubrid-pr-tc-info` design is work item 308.

## Requested behavior

- Show public and private testcase URLs.
- Improve the visuals with colors when the user runs the checker directly.

## Established context

The public testcase repository is `CUBRID/cubrid-testcases`; the private
testcase repository is `CUBRID/cubrid-testcases-private-ex`. A PR testcase
branch is `tc/pr-N`, where N is the engine PR number. A testcase pull request
has its own independent number. These terms are defined in [the repository
vocabulary](../../CONTEXT.md).

The existing checker reports whether each PR testcase branch includes the
latest published feature testcase baseline. Its text output includes fetched
hashes, commit counts, common ancestors, and full Git graphs. It has no JSON
or color mode. `--pr` together with `--base` currently avoids GitHub queries
and requires only Git. Nonfeature PR bases return `SKIP` before inspecting
testcase repositories.

Configured testcase directories can override the defaults. Fetches use their
`origin` remotes, while the current repository labels remain canonical CUBRID
names. The six existing tests use local bare origins and pass; they do not
cover URL rendering or terminal color behavior.

## Round 1: answers

1. URL destinations: testcase pull-request URLs only. Branch browsing URLs
   are outside the requested output.
2. Color selection: automatic terminal colors with `--color=auto|always|never`,
   `TERM=dumb`, and `NO_COLOR` support. Captured output is plain by default;
   an agent using a terminal can explicitly select `--color=never`.
   The user's question about an existing interactive selector was investigated:
   this checker has none and never prompts. Related sync checkers' `--check`
   suppresses confirmation/pushing, while `cubrid-pr-status` has separate
   `--human`/`--json` output modes. Neither controls this checker's presentation.
3. Presentation: accepted a short overall summary and separate Public/Private
   sections, labeled URLs, status colors, aligned details, and full graphs.
   Status remains understandable without color.

## Round 2: answers

4. PR selection: prefer open testcase PRs for `tc/pr-N`, showing every open
   match; otherwise show the most recently updated merged/closed PR with a
   state label. Report no matching PR explicitly. Accepted.
5. PR discovery: query GitHub by default, including with `--pr` plus `--base`;
   report lookup unavailability without changing the ancestry verdict or exit
   status. Add `--no-pr-links` for Git-only operation. Accepted.
   This explicitly changes the previous Git-only default for that combination.
6. Nonfeature bases: pending clarification. For an engine PR targeting
   `develop`, this command currently prints `SKIP` and exits before testcase
   inspection. The proposal keeps ancestry skipped and exit 0, but still shows
   both repositories' testcase PR URLs. A concrete output example was provided;
   recommendation remains yes.

## Lookup facts

The generic `gh-pr-info` helper can resolve a testcase branch, but requires a
unique matching PR and cannot directly implement the proposed multiple-open
or latest-historical selection. A bare branch selector can also match fork
branches; discovery must constrain the head repository and exact branch.

The existing ancestry tests use filesystem bare origins. PR discovery must
be stubbed or disabled in tests so they continue to run without network access.
Ancestry fetches continue using each configured directory's `origin`; testcase
PR lookup concerns the canonical public/private CUBRID repositories named by
the checker.

## Workflow

Documentation checkout: `/home/vimkim/my-cubrid-pr-tc-base-output`, branch
`feat/pr-tc-base-output`, starting branch and local merge destination `main`.
No functional changes have been made. Local integration requires the user's
established merge approval; no push is authorized.
