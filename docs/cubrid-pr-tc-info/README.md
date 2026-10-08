# cubrid-pr-tc-info

Inspect the public and private testcase branches associated with a CUBRID engine
pull request. Requires Python 3.9+, authenticated `gh`, and `gh-pr-info` from
`my-git-utils`. No local testcase clones are required.

```sh
# Resolve the engine PR from the current CUBRID checkout or worktree:
cubrid-pr-tc-info

# Inspect an explicit PR from any directory:
cubrid-pr-tc-info https://github.com/CUBRID/cubrid/pull/7927

# Agents and scripts:
cubrid-pr-tc-info --json https://github.com/CUBRID/cubrid/pull/7927
```

When the command is not on PATH, use `~/my-cubrid/bin/cubrid-pr-tc-info`.
The no-argument form uses the existing [PR context](../pr-context.md) interface,
including recorded PR associations and fork publishing/tracking identities.
Ambiguous or unavailable PR context is an error. Explicit and implicit lookup
are constrained to `CUBRID/cubrid`; closed or merged engine PRs can also be
inspected, with their state displayed.

## Human output

The default view has a heading for the engine PR and a block for each testcase
repository. It displays repository visibility/name, `tc/pr-N`, the branch tip,
TC PR URL and state, baseline branch/tip, and baseline ancestry status.
Human-readable SHAs use 12 characters; JSON retains all 40 characters.

```text
PUBLIC  CUBRID/cubrid-testcases
  TC branch  tc/pr-7927
  TC tip     0d9f5b448c36
  TC PR      https://github.com/CUBRID/cubrid-testcases/pull/3664  OPEN (draft)
  Baseline   feature/oos-merge @ bdba62aee0fa
  Status     CURRENT: includes latest baseline; TC-only=2, baseline-only=0
```

Terminal headings and branch/tip labels are cyan. Current ancestry is green;
missing information, stale ancestry, drafts and fallback notices are yellow;
lookup errors are red; historical PR states are gray. Redirected output remains
human-readable and has no ANSI escapes. Nonempty `NO_COLOR` or `TERM=dumb`
disables colors. `--human` explicitly selects this default; it cannot be combined
with `--json`.

## Baseline and TC PR selection

Each repository's baseline is the published testcase branch matching the engine
PR's target branch. If that ref is absent, use `develop` and explicitly label the
fallback. This follows the TC sync automation's baseline-selection rule. A TC
PR's actual target is displayed when it differs from the current baseline.

Comparisons use the observed full baseline and TC commit hashes. `CURRENT`
means that the TC history contains the latest observed baseline tip, including
any extra TC commits. `OUTDATED` means baseline updates are missing; the output
shows TC-only and baseline-only commit counts. This ancestry check does not
infer the original named branch used to create the TC branch.

The TC PR list is paginated. Show all matching open PRs, newest first. When
none are open, show the newest matching historical PR (highest PR number),
distinguishing `CLOSED` from `MERGED`. A missing TC branch can still have a
historical TC PR. No matching PR is `NONE`; a failed PR-list lookup is
`UNAVAILABLE` with an error.

Repository access is checked before ref lookup. A repository-level 404 is an
access/lookup error. A ref-level 404 after successful repository access means
that ref is absent. Missing `tc/pr-N` never falls back to another TC branch.

The command performs read-only requests and does not fetch local Git refs,
change branches, publish comments, trigger CI or merge anything. Baseline
freshness does not establish CI success or the testcase revision used by a past
run. Each repository is observed separately; the remote branches are not an
atomic snapshot. A change in the engine PR's target, head or state during
collection produces an incomplete snapshot that should be retried.

## Agent JSON contract, version 1

Always use `--json` for programmatic consumption. It emits exactly one JSON
object on stdout, including on exit 2. JSON never contains terminal escapes or
human prose. `--help` remains ordinary help text.

Exit 0 means the lookup completed, including deliberately absent refs/PRs or
outdated ancestry. Exit 2 means invalid arguments or incomplete lookup. API
failures retain successfully collected fields and the other repository's
result. Unknown/unavailable values must not be interpreted as absent or current.

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer 1; check before consuming the fields |
| `repository` | Engine repository, `CUBRID/cubrid` |
| `fetched_at` | UTC snapshot timestamp |
| `complete` | Requested lookup succeeded; not a CI or ancestry verdict |
| `pr` | Engine PR metadata, or null when resolution fails |
| `repositories` | Public then private; empty when PR resolution fails |
| `errors` | Structured collection errors, including repository-specific errors |

`pr` contains `number`, `title`, `url`, `state`, `head_branch`, `head_sha` and
`base_branch`. All SHAs are full-length.

Each repository entry contains:

- `visibility`, `repository`, and `complete`.
- `branch`: `name`, `url`, `sha` (nullable), and `status` (`present`, `missing`,
  or `unknown`).
- `baseline`: `requested_branch`, resolved `name`/`url`, nullable `sha`,
  `status` (`present`, `missing`, or `unknown`), `fallback`, and nullable
  `comparison`.
- `tc_prs`: selected PR records with `number`, `url`, `state`, `is_draft`,
  `base_branch`, and `head_sha`.
- `errors`: objects with `stage` and `message`; top-level errors additionally
  include `repository` (nullable for engine/argument errors).

`baseline.comparison` contains GitHub's `status` (`identical`, `ahead`,
`behind`, or `diverged`), `contains_baseline`, `tc_only`, `baseline_only`, and
`merge_base_sha`. A null comparison means ancestry is unavailable; check ref
states and errors. The failure stages are `arguments`, `pr`, `repository`,
`branch`, `baseline`, `tc_prs`, `comparison`, and `pr_check`.

```sh
tc_info_exit=0
cubrid-pr-tc-info --json > /tmp/cubrid-pr-tc-info.json || tc_info_exit=$?
printf 'Lookup exit: %s\n' "$tc_info_exit"

# Guard before relying on the snapshot:
jq -e '.schema_version == 1 and .complete and .errors == [] and .pr != null' \
  /tmp/cubrid-pr-tc-info.json

# Compact repository/branch/baseline/PR view:
jq '.repositories[] | {visibility, repository, branch, baseline, tc_prs, errors}' \
  /tmp/cubrid-pr-tc-info.json
```

## Verification

```sh
python3 tests/cubrid-pr-tc-info-test.py
uvx mypy --check-untyped-defs bin/cubrid-pr-tc-info tests/cubrid-pr-tc-info-test.py
```

Tests exercise the public executable with controlled external `gh` and
`gh-pr-info` responses, including terminal output through a pseudo-terminal.
The agreed design is in [PLAN.md](PLAN.md); domain vocabulary is in the root
[CONTEXT.md](../../CONTEXT.md).
