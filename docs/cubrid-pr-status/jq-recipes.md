# cubrid-pr-status jq recipes

Use these recipes with [schema version 1](schema-v1.json). See the
[agent workflow](README.md#ai-agent-workflow) for interpretation and limitations.
`jq` reads the saved snapshot without additional GitHub requests.

## Capture once, including errors

Replace the example PR URL with the requested PR. Bash:

```sh
snapshot_file=$(mktemp)
status_code=0
cubrid-pr-status --json https://github.com/CUBRID/cubrid/pull/7939 > "$snapshot_file" || status_code=$?
printf 'Fetch exit status: %s\n' "$status_code"
```

Exit 2 can contain useful partial data or a fatal error snapshot. Keep the file
until extraction is finished, then run `rm -- "$snapshot_file"`.

## Validate before extracting

First check the supported version and expose collection errors:

```sh
jq 'if .schema_version != 1 then error("unsupported schema_version")
    else {complete, errors, history} end' "$snapshot_file"
```

Use this conservative guard before the extraction recipes below. In a script,
place dependent commands in the success branch of `if jq -e ...; then ...; fi`.
`jq -e` exits 0 for true and 1 for false; parse/runtime errors also fail.
This is a usability guard, not a full JSON Schema validator.

```sh
jq -e '.schema_version == 1 and .complete == true
       and .errors == [] and .pr != null' "$snapshot_file"
```

If it fails, report errors rather than interpreting an empty check list as
success. For a history-only failure, valid current results remain usable: report
the history error and use this narrower guard for current-only extraction:

```sh
jq -e '.schema_version == 1 and .pr != null
       and all(.errors[]; .stage == "history")' "$snapshot_file"
```

## PR summary and counts by current state

Missing checks receive a synthetic `NOT_OBSERVED` label. Counts include all
discovered/configured checks, with provider states preserved.

```sh
jq '{pr_url: .pr.url, title: .pr.title, head_sha: .pr.head_sha,
     fetched_at, state: .pr.state, draft: .pr.draft,
     review: .pr.review_decision, mergeability: .pr.mergeability,
     current_counts: ([.checks[] | (.current.state // "NOT_OBSERVED")]
       | group_by(.) | map({key: .[0], value: length}) | from_entries)}' "$snapshot_file"
```

## Current failures with provider links

Match all failure states recognized by the tool, including cancelled and timed-out
checks. An empty array means no matching failures were observed; missing or
unfinished checks can still exist.

```sh
jq '[.checks[]
     | select(.current != null)
     | select(.current.state as $state
         | ["FAILURE", "ERROR", "TIMED_OUT", "CANCELLED",
            "ACTION_REQUIRED", "STARTUP_FAILURE"] | index($state) != null)
     | {provider, name, state: .current.state,
        sha: .current.reported_for_sha, url: .current.detail_url,
        reported_at: .current.reported_at}]' "$snapshot_file"
```

## Current checks that need attention

Return missing checks and every state other than success/skipped/neutral. This
includes failures, unfinished checks, and unfamiliar states; preserve the state
when reporting rather than labelling every row as running.

```sh
jq '[.checks[]
     | select(.current.state as $state
         | ["SUCCESS", "SKIPPED", "NEUTRAL"] | index($state) == null)
     | {provider, name, state: (.current.state // "NOT_OBSERVED"),
        url: .current.detail_url}]' "$snapshot_file"
```

## Expected checks missing on the head

The configured expected list is independent of branch protection and CI triggers.

```sh
jq '[.checks[] | select(.expected and .current == null)
     | {provider, name, freshness}]' "$snapshot_file"
```

## Previous results, clearly labelled stale

Include history coverage with stale results. A previous pending run is evidence
for its old commit only.

```sh
jq '{history, stale: [.checks[]
     | select(.current == null and .previous != null)
     | {provider, name, freshness: "stale", state: .previous.state,
        sha: .previous.reported_for_sha, url: .previous.detail_url,
        reported_at: .previous.reported_at}]}' "$snapshot_file"
```

## Links for one provider

Change the provider to `GitHub Actions` or `Other checks` as needed. Output is
tab-separated name, current state, and URL. Null URLs are omitted.

```sh
jq -r --arg provider 'CircleCI' '.checks[]
    | select(.provider == $provider and .current.detail_url != null)
    | [.name, .current.state, .current.detail_url] | @tsv' "$snapshot_file"
```

## Did every configured expected check succeed on this head?

This predicate requires complete collection, at least one expected check, and
`SUCCESS` on the published head for every expected check. The nonempty check
prevents `all([])` from yielding a misleading success. Skipped/neutral outcomes
do not meet this predicate. It does not establish merge readiness: unconfigured
checks, review requirements, and branch protection are separate.

```sh
jq -e '. as $snapshot
    | .schema_version == 1 and .complete == true and .errors == []
      and .pr != null
      and ([.checks[] | select(.expected)]
        | length > 0 and all(.[];
            .current != null and .current.state == "SUCCESS"
            and .current.reported_for_sha == $snapshot.pr.head_sha))' "$snapshot_file"
```

## Process watch output without buffering the whole stream

Each line is a separate snapshot. Keep errors visible and include the head SHA
because the published head may change between refreshes. `--unbuffered` flushes
each result; avoid `--slurp` on an unbounded stream. Stop the process when the
requested monitoring condition is met.

```sh
cubrid-pr-status --json --watch --interval 30 https://github.com/CUBRID/cubrid/pull/7939 |
  jq --unbuffered -c 'if .schema_version != 1 then
      {error: "unsupported schema_version", schema_version}
    else {fetched_at, complete, errors, pr_url: .pr.url, head_sha: .pr.head_sha,
          checks: [.checks[] | {provider, name,
            state: (.current.state // "NOT_OBSERVED"), url: .current.detail_url}]}
    end'
```
