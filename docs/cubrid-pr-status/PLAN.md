# cubrid-pr-status

## Agreed scope

Build a personal CUBRID-only command at `~/my-cubrid/bin/cubrid-pr-status`.
Without an argument, detect the current directory's PR through `gh pr view`.
Accept a CUBRID PR URL as an alternative. Display PR title, number, state,
draft/review/mergeability information, URL, and published head SHA.

Show GitHub Actions and CircleCI separately, preserving distinct check identities.
Each row includes current status, reported-for commit, an available timestamp,
and a detail URL. Put failures and unfinished/missing checks ahead of passes.
Configured expected checks retain rows when not observed. Discover other checks too.
If a current check is missing, show a clearly stale previous result and its SHA,
age and URL when available. Never substitute old green results for current success.
Use a one-time summary by default, with optional `--watch`.
Link to provider pages for individual failed testcases.

## Evidence and freshness contract

Read commit-scoped GitHub status and check-run APIs. `gh pr checks` alone does not
provide sufficient commit provenance. Legacy status timestamps are update times,
not reliable start times or job durations. Report unknown values honestly.

At inspection on 2026-09-14, PR7939 head `5e4b720b8f4d3b92409cb84cffd45b64cba7ba73`
had failed `gha-ci: test_shell` and successful `ci/circleci: test_shell`.
Actions run34825340275 ran an issue-comment workflow from develop `69168b3d`,
but its workflow resolved the PR head separately and published statuses to it.
Do not classify those statuses as stale using the workflow's `head_sha`.
CircleCI155114 reported the current PR SHA as its `vcs_revision`.
PR7940 illustrated a head with no SQL/medium/shell results. The user reported no
trigger; absence in the API alone cannot establish that fact.

## Implementation and validation

Use a standalone Python standard-library CLI calling authenticated `gh` with a
timeout. Store expected check contexts in an adjacent JSON configuration, with
an explicit override option. Keep pagination complete for each queried commit.
Bound historical lookup, disclose its limit, and inspect newest PR commits first.
Watch refreshes PR head and results each cycle; detect head changes during a fetch.
API errors must be visible as incomplete data, never displayed as missing/passed.

Tests run the executable with a fake `gh` at the external-service boundary.
Cover provider separation, missing and stale checks, old pending results,
workflow/PR revision differences, pagination, API errors, and watch refreshes.
Verify live using both PR7939 and current-directory PR detection. Run syntax/static
checks and the complete new CLI test suite, then review standards and scope
against baseline `5afd46232c0b9480b431b7dd2c0dc5279c4c60b6` and commit on main.

No CUBRID engine changes, CI triggers, or remote writes are part of this command.
