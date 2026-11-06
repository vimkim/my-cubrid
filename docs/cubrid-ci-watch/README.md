# cubrid-ci-watch

Track multiple CUBRID gha-ci requests in a local ledger while you work. The watcher reads GitHub metadata and the existing `cubrid-pr-status` snapshot. It does not trigger, cancel, or rerun CI and does not send notifications. Python 3.9+, `gh`, authenticated GitHub access, and `cubrid-pr-status` beside the watcher are required.

```sh
# Record the original trigger time, exact tested PR head, suites, and receipt.
cubrid-ci-watch register 1234 --head "$HEAD_SHA" --suite shell --suite sql \
  --triggered-at "$TRIGGERED_AT" --receipt "$COMMENT_URL"

# Add the caller-verified run binding when it is known. Repeat all original facts.
cubrid-ci-watch register 1234 --head "$HEAD_SHA" --suite shell --suite sql \
  --triggered-at "$TRIGGERED_AT" --receipt "$COMMENT_URL" --run-id 123 --attempt 1

# Failed-job reruns need a distinct receipt and a known run and target attempt.
cubrid-ci-watch register 1234 --head "$HEAD_SHA" --suite sql \
  --triggered-at "$TRIGGERED_AT" --receipt "$RERUN_RECEIPT" \
  --kind rerun-failed --run-id 123 --attempt 2

cubrid-ci-watch poll                    # shared loop, 15-minute interval
cubrid-ci-watch poll --once             # poll due requests for an external scheduler
cubrid-ci-watch poll --once --force     # refresh every active request now
cubrid-ci-watch status                 # human view
cubrid-ci-watch status --json          # versioned snapshot
cubrid-ci-watch events --after 42      # replay JSONL after a saved event ID
```

Pass an ISO8601 timestamp with a timezone to `--triggered-at`, such as `2026-11-06T09:00:00Z`.

The PR argument accepts a positive number or a canonical `https://github.com/CUBRID/cubrid/pull/N` URL. The receipt is an opaque operation identifier, unique per trigger. Repeating identical registration is safe. It can add a run binding once without moving the trigger time or deadline. Conflicting facts or bindings are rejected. `test_shell`, `test_sql`, and `test_medium` are accepted suite aliases. The caller asserts the receipt-to-run link. The watcher cannot independently establish that causal link, and a `pickup_candidate` event is never a binding.

Each request requires both build contexts and its selected suites. An unbound request remains unresolved, even if matching results exist on the same commit. For a bound request, the watcher verifies the gha-ci workflow run and its attempt before and after fetching that attempt's job metadata. It attributes a context only when the current status links to the bound run and its timestamp falls within the uniquely named, successfully completed publisher job's execution interval. The interval and report must be in the past and after the trigger. A normal run must have been created after the trigger; failed-job reruns can use an older run. Missing, renamed, ambiguous, or incomplete publishers remain unresolved. Failed-job reruns may retain statuses from earlier attempts; those inherited statuses remain unresolved unless republished in the selected attempt. This intentionally favors an unresolved deadline over an unsupported result. Workflow head SHA is not evidence of the tested PR head.

A verified `FAILURE` produces one failure event per context while other contexts continue. Operational states such as `ERROR` and `CANCELLED` produce `no_verdict` events and a `no_verdict` outcome when all contexts are terminal, unless a `FAILURE` takes precedence. Missing, queued, skipped, neutral, and unknown states remain unresolved. A changed PR head, newer attempt, or a selected context linked to a verified newer gha-ci run closes the original request explicitly; older linked runs are ignored, and replacement metadata errors remain observation gaps. The last valid observation is retained on closure; the watcher does not follow it. A 24-hour delay emits once. At 48 hours, the watcher attempts a final observation before closing as deadline. A valid terminal result wins; an API error closes as deadline without a CI failure verdict. Deadlines do not affect CI.

The state directory defaults to `$XDG_STATE_HOME/cubrid-ci-watch`, or `~/.local/state/cubrid-ci-watch` when unset. Place `--state-dir PATH` before the subcommand to isolate or relocate it. SQLite transactions persist state and events. One advisory lock covers all poll modes; another poller exits 2 before making API calls. Registration and status remain usable while collection is in progress. A binding added during collection invalidates that observation. Loop mode wakes locally to discover new requests, but polls each request no more often than its configured interval unless forced. `poll --interval SECONDS` changes the interval. No process is installed or started automatically.

Events are JSON lines with `schema_version`, global monotonic `id`, `request_id`, per-request `key`, `kind`, `occurred_at`, and `payload`. Polling streams newly committed events to stdout and flushes each line. Persist the last processed ID and replay with `events --after ID`. Output loss does not remove stored events; the consumer owns delivery and deduplication. Status JSON has `schema_version: 1` and a `requests` array. It shows the last valid observation and any latest collection error. Status does not assert that a poller is running.

Exit 0 means the command operated successfully, not that CI passed. Exit 2 indicates invalid input, a competing poller, a storage error, or an observation error in one-shot polling. CI failures are reported in state and events, not process exit codes. Loop mode keeps retrying observation errors. Ctrl-C stops it cleanly.

For isolated testing or an alternate local installation, `CUBRID_CI_WATCH_SNAPSHOT` selects the snapshot executable and `CUBRID_CI_WATCH_GH` selects `gh`. Each is one executable path, not a shell command. The watcher passes the explicit PR URL, `--json`, and `--history 0` to the snapshot executable. Subprocesses have a 120-second timeout. Requests are collected serially, so a slow provider can delay later requests beyond the nominal interval; the final deadline observation can likewise occur late.

Run the isolated CLI tests with `python3 tests/cubrid-ci-watch-test.py`. They use local fake providers and make no network requests.
