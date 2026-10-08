# CUBRID PR testcase information CLI

The user confirmed the design on 2026-10-08 through `grill-with-docs`.

## Agreed requirements

- Add `cubrid-pr-tc-info` to the personal CUBRID tools in `my-cubrid`.
- Accept a CUBRID engine PR URL from any working directory.
- Without a selector, resolve the corresponding engine PR from the current
  CUBRID checkout or worktree using the existing PR-context interface.
- Display the public and private testcase repositories, TC branch name,
  published branch tip, associated TC PR URL, and baseline information.
- Provide colored human-readable terminal output and `--json` for agents.
- A completed informational lookup exits successfully even when a TC branch
  is missing or does not contain the latest baseline. Lookup errors exit 2
  and retain successfully collected repository information.
- Prefer open TC PRs. If none are open, show the latest closed or merged PR
  with its state. Show all matching open PRs.

## Existing vocabulary and interfaces

The root [CONTEXT.md](../../CONTEXT.md) defines PR testcase branches and
feature-current PR testcase branches. Published branches use `tc/pr-N` in each
testcase repository, where N is the engine PR number.

`gh-pr-info --repo CUBRID/cubrid` already resolves an explicit URL or the current
worktree context. `cubrid-pr-tc-base-check` provides the existing feature-baseline
ancestry check. The new command's output requirements include TC PR metadata
that the existing checker does not display.

PR #7927 has both open and closed historical TC PRs in each repository. A branch
name alone therefore does not identify a unique historical TC PR.

## Baseline

The current baseline is the testcase branch matching the engine PR's target,
with an explicit `develop` fallback when that branch is absent. Display its
published tip and whether the TC tip includes that tip. A TC PR's actual target
is also displayed when it differs from the current expected baseline.

This describes current published branches. Git ancestry does not establish the
original named branch from which a TC branch was created or the testcase
revision used by a past CI run.

## Implementation and verification

Use the existing `gh-pr-info` selection interface and authenticated read-only
GitHub API calls. The command works without local testcase clones. Probe each
repository before interpreting ref-level 404s as missing branches; inaccessible
repositories remain errors. Compare pinned baseline and TC SHAs.

Human output uses one compact block per repository. Color is enabled on a
terminal and disabled when redirected, when TERM is dumb, or when NO_COLOR is
nonempty. JSON output is a single versioned snapshot with complete/error fields
and full SHAs, including on exit 2. Results are informational and do not prove
CI success.

Verify the public executable with controlled `gh` and `gh-pr-info` responses:
URL selection, implicit worktree selection, both repositories, baseline
relationships/fallback, TC PR history and pagination, partial errors, missing
refs versus inaccessible repositories, JSON argument errors, and terminal
colors. Then check both URL selection from outside a Git checkout and no-argument
selection inside the original CUBRID worktree against live GitHub data.

## Checkout

Implementation and design documents belong to branch `feat/pr-tc-info` in
`/home/vimkim/my-cubrid-pr-tc-info`, starting from `my-cubrid` main at `5e73a61`.
The local merge destination is `my-cubrid` main. Existing CUBRID source-worktree
submodule changes are outside this task.
