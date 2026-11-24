# cubrid-pr-flow (Phase 1)

`cubrid-pr-flow` provides the SQLite state store, idempotent Korean Discord outbox (`hermes send`), and guarded Pending Action dispatcher for CUBRID PR automation.

## State and Files

Default state directory: `${XDG_STATE_HOME:-~/.local/state}/cubrid-pr-flow` (override with `--state-dir PATH` before the subcommand).

- `config.json` (`0600`): non-secret routing and authorization config (`repo`, `discord_target`, `allowed_actors`, `hermes_bin`, `gh_bin`).
- `flow.sqlite3` (WAL mode):
  - `pr_runs`: `(pr_number, head_sha)` state tracking (`ci_state`, `review_state`, `analyze_state`).
  - `pending_actions`: single-use action records (`ACT-<N>`) with `kind` in `open_pr`, `rerun_ci`, `draft_jira_issue`, `publish_jira_issue`.
  - `notifications`: outbox queue keyed by `dedupe_key` (`pending -> claimed -> sent | unknown`).

## Quick Start

```sh
cubrid-pr-flow init --discord-target discord:#general --allowed-actor <DISCORD_USER_ID>

# Enqueue a notification + pending action and flush to Discord via `hermes send`
cubrid-pr-flow emit \
  --dedupe-key pr-8504-open-abc123 \
  --kind ask_open_pr \
  --title "PR #8504 준비 완료" \
  --summary "CI와 코드 리뷰가 모두 통과했습니다." \
  --pr 8504 \
  --head <40-char-sha> \
  --ticket CBRD-28000 \
  --question "PR을 Open 할까요?" \
  --action-kind open_pr \
  --flush \
  --json

# Validate actor + live PR freshness before running
cubrid-pr-flow dispatch ACT-1 --actor <DISCORD_USER_ID> --dry-run --json
```

## Guardrails

- **Fail-closed authorization**: `dispatch` rejects requests unless `allowed_actors` is non-empty and `--actor` is in the list.
- **No auto-retry on `unknown` delivery**: if `hermes send` fails, times out, or returns unconfirmed output, the row becomes `unknown` and is skipped by future `flush` calls until resolved via `resolve --dedupe-key ... --outcome pending|sent --reason "..."`.
- **Freshness check**: `open_pr` and `rerun_ci` actions check live GitHub PR state (`OPEN`, matching `headRefOid`, and `isDraft == true` for `open_pr`) via `gh` before claiming.
- **Single-use atomic claim**: `dispatch` uses `BEGIN IMMEDIATE` to transition `pending -> dispatched` so concurrent replies cannot execute the same action twice.

## Environment Overrides

- `CUBRID_PR_FLOW_HERMES`: executable path for `hermes`
- `CUBRID_PR_FLOW_GH`: executable path for `gh`
- `CUBRID_PR_FLOW_DISCORD_TARGET`: override target passed to `hermes send`
- `CUBRID_PR_FLOW_ACTION_RUNNER`: executable receiving action JSON on stdin and returning `{"ok": true, "summary": "..."}` on stdout (Phase 1 external runner hook)

## Exit Codes

- `0`: command succeeded (or `--dry-run` ready)
- `1`: operational rejection (`unauthorized`, `already_handled`, `expired`, `superseded`, or runner failure)
- `2`: invalid usage, missing action/state, live check error, or unconfigured action executor

## Tests

Run isolated tests (uses temporary fake `hermes`, `gh`, and runner scripts with no network calls):

```sh
python3 tests/cubrid-pr-flow-test.py -v
```
