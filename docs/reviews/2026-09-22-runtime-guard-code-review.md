# Runtime guard code review — 2026-09-22

## Review scope

### Initial rollout review

- Fixed point: `fe44e5e4a876dce8328cb36a7568e2251c7d0f69`
- Reviewed head: `f6b61a55cdba1811bbe731e58bf9d218cbde4760`
- Diff: `git diff fe44e5e...f6b61a5`
- Specifications: GitHub issues [#2](https://github.com/vimkim/my-cubrid/issues/2) and [#6](https://github.com/vimkim/my-cubrid/issues/6)
- Review axes: repository standards and specification conformance

### Follow-up working-tree review

- Fixed point: `f6b61a55cdba1811bbe731e58bf9d218cbde4760`
- Actual current `HEAD`: `257129f` (`Clone missing repositories during pull`),
  a concurrent unrelated commit preserved by this remediation
- Reviewed changes: `git diff f6b61a5` plus this untracked review artifact
- Specifications: GitHub issues [#2](https://github.com/vimkim/my-cubrid/issues/2) and [#6](https://github.com/vimkim/my-cubrid/issues/6)
- Review axes: independent Standards and Spec reviews
- Initial follow-up Standards result: clean
- First follow-up Spec result: three findings (two high, one medium), resolved
- Later Standards/Spec rounds found additional lifecycle, ownership, and seam
  gaps; all were resolved in the working tree
- Final exact-state Standards result: clean
- Final exact-state Spec result: clean

The findings marked resolved below are historical findings from the initial
review. The follow-up findings below describe the completed remediation scope.

## Follow-up findings

### F1 — Caller-controlled environment can bypass runtime locking

Severity: high
Status: resolved in the working tree

`cubrid-build-coordinator.sh runtime` trusts
`CUBRID_RUNTIME_LOCK_HELD=1` as proof that the caller already owns the runtime
lock. A caller can set that environment variable manually, causing the command
to execute without `acquire_runtime_lock`. The existing regression covers the
ordinary acquisition path but not a spoofed inherited environment.

Required outcome: nested coordinator execution, if retained, must prove lock
ownership without trusting caller-controlled ambient state. A managed runtime
command must not execute unless the coordinator actually owns the lock.

Resolution: recursive coordinator entry is unsupported. The ambient lock marker
shortcut was removed, so every runtime invocation acquires the actual lock.
`test_runtime_lock_environment_marker_cannot_bypass_real_lock` holds the real
lock elsewhere and proves that a spoofed marker cannot run the command.

### F2 — `remove-databases` bypasses the coordinator

Severity: high
Status: resolved in the working tree

`db::remove-databases` directly removes `$CUBRID_DATABASES` rather than passing
the database lifecycle action through the coordinator. This contradicts issue
#2's single-enforcement-seam requirement and the earlier P3 resolution claim
that database lifecycle recipes now use that seam.

Required outcome: audit every runtime and database recipe, route all in-scope
actions through the coordinator, and add coverage that would detect another
direct bypass.

Resolution: broad database-root deletion recipes and their aliases were
removed. Configuration, registry reads, CTP, OOS, host-installation Podman,
live-debug process discovery, and live profiling now enter the coordinator.
`test_all_managed_runtime_recipe_classes_use_coordinator` executes every agreed
recipe class with coordinator and direct-command spies.

### F3 — Rejected fixed-name creation recipes mutate storage

Severity: medium
Status: resolved in the working tree

`create-testdb` and `create-demodb` create their database directories before
the coordinator validates the runtime and selected database. A mismatched
fixed-name recipe is rejected only after it has modified storage.

Required outcome: a rejected fixed-name recipe must produce no database
filesystem mutation. Directory creation must occur only after validation and
selected-database enforcement succeed.

Resolution: fixed-name creation recipes are thin adapters over
`my-cubrid-pwddb`, invoked only after the coordinator validates their selected
name. `test_fixed_database_recipes_refuse_non_selected_database` proves rejected
`create-testdb` and `create-demodb` calls leave no directory behind.

### F4 — `recreate-demodb` splits deletion and creation

Severity: high
Status: resolved in the working tree

The recipe previously composed `delete-demodb` and `create-demodb`. Missing
runtime or template inputs could therefore make deletion succeed before
creation failed. It now invokes one coordinated
`my-cubrid-pwddb recreate --load demodb` lifecycle operation. Regressions cover
the recipe shape and prove that a missing utility leaves registry and storage
unchanged.

### F5 — Registered-database listing reports an absent selection

Severity: medium
Status: resolved in the working tree

`list-all` and `start-interactive` used the manifest-name helper, which prints
the selection even when no registry row exists. The new guarded
`my-cubrid-pwddb list` action reads the validated registry row under the
database lock and prints nothing after deletion.

### F6 — Live process selection is not scoped to the validated runtime

Severity: high
Status: resolved in the working tree

Interactive debugger and profiler recipes selected processes by user/name
only. Candidates are now restricted to the exact selected installation,
worktree directory, database, and requested utility role while the coordinator
holds the runtime lock.

### F7 — Combined stop/build skips runtime revalidation

Severity: high
Status: resolved in the working tree

`stop-and-build` acquired the runtime lock but did not validate before running
service and broker stop commands. It now revalidates at the build-to-runtime
transition; a regression proves an invalid runtime cannot be stopped or
installed.

### F8 — Installation removal bypasses the runtime coordinator

Severity: high
Status: resolved in the working tree

`core::delete-install` now runs the confirmed removal through the coordinator,
after guard-proven idle-state validation and while holding the runtime lock.

### F9 — Persistent Podman harness outlives its runtime lock

Severity: high
Status: resolved in the working tree

The managed Podman recipe returned after its test while leaving a container
with the selected installation bind-mounted. It now requests wait-for-stop
mode: the foreground coordinator retains the runtime lock until explicit
container cleanup. Presence-observation failures retain the lock, cleanup is
armed before container creation, and signal/error cleanup retries until container
absence is proven before the lock is released. A per-invocation ownership label
and immutable container ID prevent cleanup from deleting a foreign same-name
container, including a replacement created after identity observation.

## Standards findings

### S1 — Duplicated selected-database enforcement

Severity: low; judgement call
Status: resolved in the working tree

`stow/cubrid/.just/db.just` and `stow/cubrid/.just/debug.just` independently
implement the same selected-database check and diagnostic around
`my-cubrid-pwddb-getname`. The policy can drift between recipe modules. Put the
rule behind one shared enforcement interface.

Resolution: fixed-name selection is now enforced once by
`cubrid-build-coordinator.sh runtime --database`, after runtime validation and
while the runtime lock is held. The duplicate `db.just` and `debug.just` guards
were removed.

### S2 — Unused runtime identifier parameter

Severity: low; judgement call
Status: resolved in the working tree

`default_database_name(worktree, _runtime_identifier)` retains an unused
runtime-identifier argument after the accepted naming policy removed runtime-ID
suffixes. Remove the parameter and update callers.

Resolution: `default_database_name` now accepts only the worktree, and both
callers use that interface.

## Specification findings

### P1 — Incomplete-observation precedence is partial

Severity: high
Status: resolved in the working tree

Issue #2 requires incomplete runtime observations to take precedence over
manifest-completeness errors and return `observation_incomplete`.
`load_validation_metadata` rejects an empty `resource_bundle` with
`manifest_incomplete` before capturing runtime observations. The existing
regression test uses a truthy partial bundle and does not cover this branch.

Required regression: an incomplete runtime observation plus an empty resource
bundle reports `observation_incomplete`.

Resolution: runtime observation completeness is checked before the first
`manifest_incomplete` branch. Covered by
`test_incomplete_runtime_observations_precede_empty_resource_bundle` and the
original `test_incomplete_fake_runtime_observations_fail_closed` regression.

### P2 — Preset mismatch does not load Build-only state

Severity: high
Status: resolved in the working tree

Issue #2 requires a preset mismatch to place the worktree in Build-only state
until the new installation is complete. Runtime validation reports the mismatch
as exit status 4, while `.envrc` recognizes only status 3 as Build-only and
therefore fails environment loading.

Required regression: after changing `PRESET_MODE`, the real shared environment
loader succeeds, preserves the stable worktree identity, exposes build context,
withholds runtime context, and permits a later safe Preset takeover.

Resolution: `.envrc` recognizes only a structured `manifest_inconsistent`
diagnostic whose affected object is the active preset as Build-only. Other
invalid status-4 results continue to fail closed. Covered by
`test_preset_mismatch_loads_build_only_environment`, the existing invalid-state
test, and the existing idle/live Preset takeover runtime tests.

### P3 — Runtime recipes bypass the coordinator seam

Severity: high
Status: resolved in the working tree

Issue #2 requires managed server, broker, database, SQL, and related runtime
recipes to pass through one enforcement seam. Several database and debug recipes
execute `cub-auto`, `csql.sh`, `cubrid`, or `cgdb` after a prerequisite helper
has validated and released its locks. Revalidation and the runtime lock do not
cover the actual command, leaving a time-of-check/time-of-use gap.

Required regression: representative database, SQL, and debug recipes invoke the
actual command only through the coordinator's `runtime` action, after immediate
validation and while its runtime lock is held.

Resolution: the coordinator's `runtime --database` option validates
readiness, checks the manifest-selected database, and then executes the
command. Fixed-name server/database/SQL and debug recipes use this seam; the
follow-up F1-F3 resolutions close the remaining lock, lifecycle, and
pre-validation mutation gaps. Coverage includes
`test_runtime_action_checks_selected_database_while_locked`,
`test_fixed_database_recipes_refuse_non_selected_database`, and
`test_database_sql_and_debug_recipes_use_coordinator`, plus the follow-up
regressions described above.

## Rollout evidence

The review found no state contradicting the completion comments on issues #2
and #6: the `develop` worktree uses its private runtime and fresh `develop`
database, final resources are stopped, and unrelated CUBRID worktree changes
remain present. The one-time destructive migration must not be repeated while
resolving these findings.

## Resolution evidence

| Finding | Status | Regression or verification |
| --- | --- | --- |
| S1 | Resolved in working tree | Central coordinator database assertion; recipe integration tests |
| S2 | Resolved in working tree | One-argument naming interface; runtime-guard suite |
| P1 | Resolved in working tree | Empty-bundle incomplete-observation regression |
| P2 | Resolved in working tree | Preset-mismatch Build-only loader regression plus takeover tests |
| P3 | Resolved in working tree | Coordinator lock, recipe integration, and rejected-mutation regressions |
| F1 | Resolved in working tree | Spoofed-marker contention regression |
| F2 | Resolved in working tree | Executable integration audit across every Managed runtime action class |
| F3 | Resolved in working tree | Rejected fixed-name creation leaves storage unchanged |
| F4 | Resolved in working tree | Single-operation demodb recreation and no-mutation regression |
| F5 | Resolved in working tree | Guarded registry-row list and post-delete regression |
| F6 | Resolved in working tree | Shared exact-identity/start-time live-process selector |
| F7 | Resolved in working tree | Stop/build invalid-runtime regression |
| F8 | Resolved in working tree | Idle-only installation deletion regression |
| F9 | Resolved in working tree | Podman presence, creation-signal, immutable-ID collision, and cleanup-retry regressions |

Final implementation verification completed from the remediated working tree:

- runtime guard: 134 tests passed
- runtime environment: 19 tests passed
- runtime lock: 12 tests passed
- pwddb: 25 tests passed
- `bash -n`, the shared `just` parse/list check, and `git diff --check` passed

The final independent Standards and Spec re-review passed with no findings.

## Remediation decisions

Accepted during the follow-up design interview:

1. The Managed runtime action boundary is strict. It includes actions using the
   installed runtime, selected database registry or storage, live CUBRID
   processes, and test harnesses against the installation. Offline core and
   trace work is exempt.
2. Remove the broad `delete-all` and `remove-databases` recipes and their
   compatibility aliases. Recreate operations target only the selected
   database.
3. Retain fixed-name convenience commands as thin adapters over
   `my-cubrid-pwddb`. The coordinator first checks that their name is selected,
   then one coordinated lifecycle operation performs the work.
4. `pwddb delete` may use Binary-independent database deletion only when the
   selected executable is unavailable, ownership is proven, and complete
   runtime observations prove the runtime idle. It atomically removes the
   selected registry row and then cleans only its owned storage. Failure from
   an available `cubrid deletedb` remains a hard failure and never triggers the
   fallback.
5. Recursive runtime-coordinator entry is unsupported. Remove the
   `CUBRID_RUNTIME_LOCK_HELD` shortcut; every invocation must acquire the actual
   runtime lock, which is the sole proof of lock ownership.
6. Expose binary-independent deletion through a dedicated coordinator
   `database-delete` action, not a generic validation-bypass flag. Automatic
   fallback is limited to fresh guard-created databases; adopted storage
   requires the real CUBRID utility.
7. Remove direct `edit-databases`; retain `list-all` as a guarded read of the
   manifest-selected registry row.
8. Remove the runtime-sensitive optional-`local.just` bridges
   `update-cubrid-conf`, `build-update`, and `update-restart-testdb`. Retain
   unrelated non-runtime compatibility aliases.
9. Keep binary-independent deletion development-oriented and simple: do not
   add a recovery journal. Remove the selected registry row atomically before
   storage cleanup. If interrupted, report that orphaned files may require
   manual removal rather than leaving a discoverable partially deleted row.
10. Permit first-use creation of canonical owner-only `.pwddb.lock`
    coordination metadata before final lifecycle validation. A rejected
    operation must not change registry rows, database contents, or storage
    roots, but may leave this inert lock file in place.

This follow-up stops before commit or push.
