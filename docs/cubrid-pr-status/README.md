# cubrid-pr-status

A read-only terminal view of CUBRID PR status, GitHub Actions and CircleCI results.
Requires Python 3.9+ and an authenticated GitHub CLI (`gh auth login`).

```sh
# Run inside a CUBRID Git checkout/worktree:
~/my-cubrid/bin/cubrid-pr-status

# Explicit human view (the default), or AI/tool-friendly JSON:
~/my-cubrid/bin/cubrid-pr-status --human
~/my-cubrid/bin/cubrid-pr-status --json

# Inspect a PR directly, from any directory:
~/my-cubrid/bin/cubrid-pr-status https://github.com/CUBRID/cubrid/pull/7939

# Refresh every 30 seconds after each fetch; Ctrl-C exits:
~/my-cubrid/bin/cubrid-pr-status --watch

# Stream one complete JSON object per line per refresh:
~/my-cubrid/bin/cubrid-pr-status --json --watch

# Search more previous PR commits or use a different expected-check list:
~/my-cubrid/bin/cubrid-pr-status --history 20 --config /path/to/checks.json
```

Edit `bin/cubrid-pr-status.json` to change the expected checks. Its format is
`{"expected_checks": ["gha-ci: test_sql", "ci/circleci: test_sql"]}`.
Discovered checks are also shown. Expected does not mean required by branch
protection, nor does it prove someone triggered the suite.

`current` means reported for the published PR head, which can differ from local
HEAD. A missing current check is `NOT OBSERVED`; an older result appears as
`STALE previous` with its own commit, time, and link. A previous pending run does
not mean current CI is running. An Actions workflow can run from develop while
reporting test results for a separate PR commit; its workflow SHA does not override
the status's reported-for commit. This display reports GitHub's association and
does not independently audit test artifacts.

History searches the last five earlier PR commits by default (`--history 0`
disables it, maximum 250). The output states the searched range. Results on commits
removed by force-push cannot be recovered through the PR commit list. GitHub's PR
commit API has a 250-commit limit; if the selected head is outside the returned
history, the script reports incomplete history. Increase `--history` if the last
CI run predates the default window. No result anywhere in the searched range is
different from proof that a job never ran.

The display gives available report timestamps and ages, not inferred queue times
or durations. Links go to provider check/job/run pages, where individual failed
testcases can be inspected. API failures are reported as incomplete data. A PR
head change during fetching rejects that snapshot; retry, or let watch refresh.
Watch pins the initially resolved PR URL and rereads its head each cycle. `--interval`
sets the wait between fetches; very short intervals consume more API requests.

## AI agent workflow

Use this tool for a CUBRID PR status summary with GitHub Actions and CircleCI
results and links. Always select `--json` for programmatic consumption; redirected
output otherwise remains human-readable.

1. **Select the PR and fetch once.** Run
   `cubrid-pr-status --json https://github.com/CUBRID/cubrid/pull/7939`, replacing
   the example URL with the requested PR. Omit the URL only inside the checkout
   for the intended PR. Use `~/my-cubrid/bin/cubrid-pr-status` if it is not on PATH.
2. **Validate the snapshot.** Capture stdout and the exit code, then parse stdout
   even on exit 2: it contains structured errors. Require `schema_version == 1`
   before relying on this schema. Inspect `complete` and `errors`; exit 0 and
   `complete: true` describe successful collection, not passing or finished CI.
   For incomplete data, report the error stage and message. A history-only error
   preserves valid current results; fatal errors have `pr: null` and no check rows.
   Retry a `head_check` error to fetch a consistent snapshot.
3. **Interpret checks for the published head.** Use `pr.head_sha`, which can
   differ from local HEAD. Read each check's `provider`, `name`, and `current`.
   After successful current-check collection, `current: null` means not observed.
   Treat `previous` as stale evidence for its own `reported_for_sha`, including
   when it says `PENDING` or `SUCCESS`. An expected check is a configured display
   entry; it does not establish a CI trigger or branch-protection requirement.
4. **Report evidence and links.** Include `pr.url`, the head SHA, `fetched_at`, PR
   state, draft/review/mergeability fields, and current CI states by provider and
   check name. Link to each available `current.detail_url`. Clearly label stale
   results with their commit and link, and disclose incomplete data or limited
   history when relevant. Preserve state distinctions: `SUCCESS` is passing;
   `NEUTRAL` and `SKIPPED` are separate outcomes. Failure states include `FAILURE`,
   `ERROR`, `TIMED_OUT`, `CANCELLED`, `ACTION_REQUIRED`, and `STARTUP_FAILURE`.
   Report other states as returned; an unfamiliar state does not establish success.
   Follow detail links when testcase failures or root causes are requested; this
   tool reports status metadata and does not independently audit artifacts.

For current-only questions, use `--history 0` to avoid history requests. If prior
CI results matter, inspect `history` and increase `--history` when the searched
window is too short (default 5, maximum 250). An absent previous result means none
was found within coverage; force-pushed-away commits remain unavailable.

For ongoing monitoring, use `--json --watch --interval 30` and parse each line as
an independent snapshot, checking its schema, completeness, errors, and head SHA.
Stop the process when the requested monitoring condition is met. For a single
status request, finish after reporting one snapshot. Fetching status is read-only;
triggering CI, posting comments, and changing the PR require separate tools.

For example, preserve error snapshots and extract PR/check links in Bash:

```sh
status_code=0
cubrid-pr-status --json https://github.com/CUBRID/cubrid/pull/7939 > /tmp/cubrid-pr-snapshot.json || status_code=$?
printf 'Fetch exit status: %s\n' "$status_code"
jq '{schema_version, complete, errors, pr, history,
     checks: [.checks[] | {provider, name, freshness, current, previous}]}' \
  /tmp/cubrid-pr-snapshot.json
```

## Output formats

`--human` is the default even when redirected. It uses an aligned ASCII layout,
summary counts, and markers: `[!]` failure, `[+]` success, `[~]` unfinished,
`[?]` not observed, and `[-]` skipped/neutral. Terminal output colors failures red,
success green, missing/unfinished/stale results yellow, and skipped results gray.
Redirection, `TERM=dumb`, and nonempty `NO_COLOR` disable ANSI colors. With color
disabled, watch appends snapshots rather than clearing the screen.

`--json` and `--human` are mutually exclusive. JSON has no terminal escapes or
human prose on stdout. One-time output is an indented object; watch is NDJSON,
with one flushed, compact object per line, including error snapshots. JSON errors
are on stdout and retain exit2. Help (`--help`) remains ordinary help text.

### JSON Schema (version 1)

The machine-readable [schema-v1.json](schema-v1.json) describes every field,
required key, nullable value, and the current/previous and history variants.
It uses JSON Schema draft 2020-12 and accepts additional fields. Provider states
remain open strings so consumers can display unfamiliar states without treating
them as success. `reported_at` and `detail_url` are nullable strings passed through
from provider metadata; `fetched_at` is a generated UTC timestamp.

The schema validates structure; consumers must also compare a current result's
`reported_for_sha` with `pr.head_sha` when enforcing commit identity. Schema
validation alone establishes neither CI success nor artifact correctness.

See [jq recipes](jq-recipes.md) for snapshot guards, summaries, failure links,
missing/stale checks, expected-check success, and watch processing.

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer1; consumers should check it before reading fields |
| `repository`, `fetched_at` | CUBRID repository and UTC snapshot timestamp |
| `complete` | Requested collection succeeded; does not mean CI passed or finished |
| `pr` | Number, title, URL, full `head_sha`, state, draft, review decision, mergeability; null for fatal errors |
| `checks` | Stable provider/name ordering, with failures and unfinished checks ahead of successes within each provider |
| `history` | Status (`disabled`, `complete`, `incomplete`), limit, searched/available counts, and truncation flag; null on fatal errors |
| `errors` | Objects containing `stage` and `message`; empty for successful collection |

Each check has `name`, `provider`, `expected`, `freshness`, `current`, and
`previous`. Freshness is `current` or `not_observed`. A result contains `state`,
full `reported_for_sha`, `detail_url`, and `reported_at`; unknown URL/time is null.
`current: null` means not observed after successful current-check collection.
`previous` is a stale result shown only when current is missing; null means no
previous result is available in the searched history. Read history coverage and
errors before interpreting that null. An older pending result remains stale.

Disabled history has searched0, with available/truncated null. Incomplete history
has unknown counts/truncation (null); valid current checks are retained. Truncated
history means the configured limit was smaller than the available earlier PR
commits, not that the fetch failed. Force-pushed-away commits are outside coverage.
Fatal collection/argument/config errors return `complete: false`, no check rows,
and a structured error, so unavailable data cannot masquerade as missing checks.
Stages are `arguments`, `configuration`, `pr`, `current_checks`, `history`, and
`head_check`. An invalid combination containing `--json` reports its error as JSON.

Exit status is 0 when the view was fetched (even if CI failed), 2 for invalid input
or incomplete data, and 0 on Ctrl-C. The command does not trigger CI or write to
GitHub. The source, adjacent config, tests and design docs live in `~/my-cubrid`.

## Validation

```sh
python3 tests/cubrid-pr-status-test.py
uvx mypy --check-untyped-defs bin/cubrid-pr-status tests/cubrid-pr-status-test.py
```

The tests exercise the executable with controlled responses at the external `gh`
boundary. Live checks on 2026-09-14 verified URL selection using PR7939 and current
directory selection using PR7940. See [PLAN.md](PLAN.md) for the agreed design and
[CONTEXT.md](CONTEXT.md) for vocabulary.
