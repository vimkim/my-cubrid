# CUBRID briefing bridge

This command consumes `cubrid-ci-watch` events and delivers recorded observations to an explicit Discord destination and an existing Herdr agent. The watcher remains the only CI collector. Work-tracker remains the authority for work status. The bridge never starts agents, changes work, triggers CI, or queries GitHub.

## Setup

Choose a private state directory and a report directory served by the existing private docserve server. Verify the serving path, access control, DNS, and HTTPS from the actual scheduler environment before enabling delivery. All processes must use the same state directory and OS account. The defaults below are examples; create the JSON files privately and replace every value.

```json
{
  "watcher": "/absolute/path/cubrid-ci-watch",
  "tracker": "/absolute/path/work-tracker",
  "herdr": "/absolute/path/herdr",
  "hermes": "/absolute/path/hermes",
  "report_dir": "/absolute/path/served/reports",
  "report_base": "https://private.example/reports",
  "discord_target": "DISCORD_CHANNEL_ID",
  "brief_work_ids": [123]
}
```

```sh
bin/cubrid-briefing init --config /private/config.json
```

Initialization records the current latest event ID for both sinks and does not send historical events. It cannot be repeated against an initialized state directory. The default is `~/.local/state/cubrid-briefing`; pass `--state-dir DIR` before the subcommand to override it. Protect the configuration, database and report directory. Do not put credentials in these files.

Bind one existing watcher request to a specific work item and agent. Obtain the full SHA, canonical working directory, pane ID, and agent session UUID from their authoritative sources. `herdr_session` defaults to `default`.

```json
{
  "request_id": 1,
  "work_id": 123,
  "pr": 456,
  "head": "0000000000000000000000000000000000000000",
  "pane_id": "workspace:pane",
  "agent_session": "agent-session-uuid",
  "cwd": "/absolute/canonical/worktree",
  "herdr_session": "default"
}
```

```sh
bin/cubrid-briefing bind --route /private/route.json
bin/cubrid-briefing status
bin/cubrid-briefing brief --date 2026-11-12
```

Binding checks the watcher, work item and Herdr identity. A busy agent or missing `interactive_ready` is accepted as a deferred binding. Rebinding a changed route suppresses its unsent old deliveries. A preview writes a private Markdown report and returns its path, URL and Korean summary as JSON. It does not send. The report explicitly distinguishes ledger records from live GitHub status.

## Delivery

Run the sinks as independent commands, for example from separately scheduled jobs. Each has its own lock and event cursor.

```sh
bin/cubrid-briefing tick --sink herdr
bin/cubrid-briefing tick --sink discord
bin/cubrid-briefing brief --date 2026-11-12 --send
```

Daily sends use the date and Discord target as their idempotency key. The send flag sends only that daily briefing. Event delivery writes a report first. Herdr delivery requires the same request, PR and head, an eligible work item, the exact agent UUID, pane and working directory, an idle or done status, and `interactive_ready: true`. A changed identity or superseded request is suppressed; a busy or unconfirmed agent is deferred. A Discord notice is queued when Herdr validation suppresses a delivery. Terminal CI success or failure remains eligible even when the watcher request is closed.

Before scheduling, verify a read-only `herdr --session default agent get PANE` from the scheduler's actual environment. A working interactive shell does not establish scheduler connectivity. The Hermes standalone send command needs its existing Discord credentials. This repository does not install or configure the scheduler, Hermes, Herdr, Discord, or docserve.

`status` lists cursor and delivery states. `sent` means the destination acknowledged submission, not that a person or agent acted. `unknown` means the command may have delivered before an error, timeout, malformed response or interruption. The bridge never retries it automatically. Inspect the destination manually before deciding on any further action; the first version provides no automatic unknown-resolution command. Command stderr is not stored.
