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

## Round 1: awaiting answers

1. URL destinations: branch links, testcase pull-request links, or both?
   Recommendation: both, clearly labeled, when available.
2. Color selection: automatic terminal detection or explicit opt-in?
   Recommendation: stdout TTY detection, `TERM=dumb` and `NO_COLOR` support,
   with `--color=auto|always|never`. Agents using a TTY can request plain output.
3. Presentation: a short overall summary and separate Public/Private sections,
   or minimal edits to the existing layout?
   Recommendation: summary and sections, labeled URLs, status colors, aligned
   details, and full graphs. Status remains understandable without color.

## Decisions dependent on round 1

If testcase pull-request links are selected, settle discovery behavior:
Git-only compatibility, lookup failures, missing pull requests, and multiple
historical pull requests for one branch.

Settle link presentation when a branch is missing, inspection fails, a
nonfeature PR is skipped, or a configured origin differs from the canonical
repository. Settle whether plain text is sufficient for agents or a new
machine-readable output mode is in scope. These are open questions, not
accepted requirements.

## Workflow

Documentation checkout: `/home/vimkim/my-cubrid-pr-tc-base-output`, branch
`feat/pr-tc-base-output`, starting branch and local merge destination `main`.
No functional changes have been made. Local integration requires the user's
established merge approval; no push is authorized.
