# Complete workenv migration (work item 262)

This follow-up addresses the 2026-10-02 handoff, not the earlier completed
implementation/adoption. Fixed bases: tooling `74a13cf`, CLI `caa0507`, selected
config editor `a7fad0c`. Work is isolated in sibling topic worktrees. No existing
user DB, allocation or shared symlink has been migrated or cleaned by this task.

## Responsibility decision

| Responsibility | New home / disposition |
| --- | --- |
| Host init, allocation, selection, registry creation | Public `cub-workenv` CLI only; no legacy fallback |
| Serialize configure/compile/build and install targets | Narrowed existing coordinator, canonical build lock |
| Refuse replacement of a busy install | Existing installation lock and native executable observation, exit 75 |
| Foreground command/harness lifetime | Supervisor owns locks, forwards signals, waits for cleanup; descendants close lock FDs |
| Persistent container ownership and cleanup | Existing `cubrid-podman-test.sh` label/immutable-ID verification, `installation-use` lock |
| Ordinary native execution | Direct `cubrid`/`csql` allowed; shared recipes retain cooperative installation-use protection |
| DB create | `cub-workenv create-db`; no precondition that output DB already exists |
| Internal delete/recreate | Personal helper consumes creation provenance, checks physical paths, native deletion, exact target registry removal |
| External/mixed/unknown DB | Preserve and direct to reviewed manual lifecycle, as explicitly chosen by the user |
| Stop-and-build | Compile → installation lock → selected host environment → stop its registered servers → idle check → install |
| Installation deletion | Build+installation locks, native-idle check, broad-path/DB-artifact refusal; host state/data are retained |
| Legacy runtime command | Actionable retirement stub, no implementation or automatic migration |

The recommendation is to retain the coordinator's familiar name for these small
build/installation responsibilities. Renaming it adds no protection, while
removing it outright would lose needed protection. The ~6,000-line legacy runtime
engine and the manifest DB helper are removed from active software, not renamed
into workenv. The CLI gains only creation provenance, not build/container ownership.

## Every shared-recipe caller

Each row below is a public or compatibility caller at the changed seam. The
module imports and flat aliases continue to resolve these same recipes; they do
not independently select storage. Native and boundary evidence are summarized
below; a listed disposition does not claim native execution of every interactive UI.

| Caller | Operation / current replacement |
| --- | --- |
| `stow/cubrid/justfile:dwb-off` | Selected native command under installation lock: `ini.sh -s common "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" double_write_buffer_size 0` |
| `stow/cubrid/justfile:dwb-get` | Selected native command under installation lock: `ini.sh -s common "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" double_write_buffer_size` |
| `stow/cubrid/.just/core.just:configure` | Coordinator `configure`; build/install/container boundary |
| `stow/cubrid/.just/core.just:compile` | Coordinator `compile`; build/install/container boundary |
| `stow/cubrid/.just/core.just:install` | Coordinator `install`; build/install/container boundary |
| `stow/cubrid/.just/core.just:build-without-log` | Coordinator `build`; build/install/container boundary |
| `stow/cubrid/.just/core.just:build` | Coordinator `build`; build/install/container boundary |
| `stow/cubrid/.just/core.just:build-wait` | Coordinator `build`; build/install/container boundary |
| `stow/cubrid/.just/core.just:install-wait` | Coordinator `install`; build/install/container boundary |
| `stow/cubrid/.just/core.just:stop-and-build` | Coordinator `stop-and-build`; build/install/container boundary |
| `stow/cubrid/.just/core.just:ctest` | Coordinator `installation-use`; build/install/container boundary |
| `stow/cubrid/.just/core.just:install-3rdparty` | Coordinator `install-target`; build/install/container boundary |
| `stow/cubrid/.just/core.just:install-csql-util` | Coordinator `install-target`; build/install/container boundary |
| `stow/cubrid/.just/core.just:target` | Coordinator `target`; build/install/container boundary |
| `stow/cubrid/.just/core.just:target-fuzzy` | Same protected target chooser as `core::target` |
| `stow/cubrid/.just/core.just:delete-install` | Coordinator `installation-delete`; build/install/container boundary |
| `stow/cubrid/.just/ctp.just:shell-debug` | Selected native command under installation lock: `cubrid-shell-debug.sh {{ TEST_DIR }}` |
| `stow/cubrid/.just/ctp.just:shell-debug-many` | Selected native command under installation lock: `cubrid-shell-debug.sh {{ SUBTREE }}` |
| `stow/cubrid/.just/ctp.just:shell-debug-interactive` | Selected native command under installation lock: `~/CTP/bin/ctp.sh shell --interactive -c ~/CTP/conf/shell_ci.conf` |
| `stow/cubrid/.just/ctp.just:podman-test-new` | Coordinator `installation-use`; build/install/container boundary |
| `stow/cubrid/.just/db.just:list-all` | Workenv DB helper `list` (no legacy authority) |
| `stow/cubrid/.just/db.just:start-interactive` | Workenv DB helper `list` (no legacy authority); Selected native command under installation lock: `cubrid server start "$database"` |
| `stow/cubrid/.just/db.just:stop-interactive` | Selected native command under installation lock: `cubrid server status)`; Selected native command under installation lock: `cubrid server stop "$database"` |
| `stow/cubrid/.just/db.just:pwddb-create` | Workenv DB helper `create` (no legacy authority) |
| `stow/cubrid/.just/db.just:pwddb-recreate` | Workenv DB helper `recreate` (no legacy authority) |
| `stow/cubrid/.just/db.just:pwddb-delete` | Workenv DB helper `delete` (no legacy authority) |
| `stow/cubrid/.just/db.just:pwddb-create-demodb` | Workenv DB helper `create --load demodb` (no legacy authority) |
| `stow/cubrid/.just/db.just:pwddb-recreate-demodb` | Workenv DB helper `recreate --load demodb` (no legacy authority) |
| `stow/cubrid/.just/db.just:pwddb-delete-demodb` | Workenv DB helper `delete` (no legacy authority) |
| `stow/cubrid/.just/db.just:start-testdb` | Selected native command under installation lock: `cubrid server start testdb` |
| `stow/cubrid/.just/db.just:restart-testdb` | Selected native command under installation lock: `cubrid server restart testdb` |
| `stow/cubrid/.just/db.just:stop-testdb` | Selected native command under installation lock: `cubrid server stop testdb` |
| `stow/cubrid/.just/db.just:stop-testdb-try` | Selected native command under installation lock: `cubrid server stop testdb \|\| true` |
| `stow/cubrid/.just/db.just:start-demodb` | Selected native command under installation lock: `cubrid server start demodb` |
| `stow/cubrid/.just/db.just:restart-demodb` | Selected native command under installation lock: `cubrid server restart demodb` |
| `stow/cubrid/.just/db.just:stop-demodb` | Selected native command under installation lock: `cubrid server stop demodb` |
| `stow/cubrid/.just/db.just:paramdump-testdb` | Selected native command under installation lock: `cub-auto paramdump testdb \| rg 'buffer\|string` |
| `stow/cubrid/.just/db.just:csql` | Selected native command under installation lock: `csql -C -u dba testdb` |
| `stow/cubrid/.just/db.just:csql-sa` | Selected native command under installation lock: `csql -S -u dba testdb` |
| `stow/cubrid/.just/db.just:unloaddb-sa` | Selected native command under installation lock: `cubrid unloaddb testdb -S -t 0 -v` |
| `stow/cubrid/.just/db.just:unloaddb-cs` | Selected native command under installation lock: `cubrid unloaddb testdb -C -t 0 -v` |
| `stow/cubrid/.just/db.just:create-testdb` | Workenv DB helper `create testdb` (no legacy authority) |
| `stow/cubrid/.just/db.just:delete-testdb` | Workenv DB helper `delete testdb` (no legacy authority) |
| `stow/cubrid/.just/db.just:recreate-testdb` | Workenv DB helper `recreate testdb` (no legacy authority) |
| `stow/cubrid/.just/db.just:create-demodb` | Workenv DB helper `create demodb --load demodb` (no legacy authority) |
| `stow/cubrid/.just/db.just:delete-demodb` | Workenv DB helper `delete demodb` (no legacy authority) |
| `stow/cubrid/.just/db.just:recreate-demodb` | Workenv DB helper `recreate demodb --load demodb` (no legacy authority) |
| `stow/cubrid/.just/db.just:ini` | Selected native command under installation lock: `cubrid-ini-fzf --database "{{ database }}" --section "{{ section }}"` |
| `stow/cubrid/.just/db.just:get-string-compression` | Selected native command under installation lock: `crudini --get "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common enable_string_compression \|\| true` |
| `stow/cubrid/.just/db.just:enable-string-compression` | Selected native command under installation lock: `crudini --set "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common enable_string_compression yes` |
| `stow/cubrid/.just/db.just:disable-string-compression` | Selected native command under installation lock: `crudini --set "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common enable_string_compression no` |
| `stow/cubrid/.just/db.just:paramdump-string-compression` | Selected native command under installation lock: `cub-auto paramdump testdb \| rg enable_string_compression` |
| `stow/cubrid/.just/db.just:get-pgbuf-inspector` | Selected native command under installation lock: `crudini --get "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common enable_pgbuf_inspector` |
| `stow/cubrid/.just/db.just:enable-pgbuf-inspector` | Selected native command under installation lock: `crudini --set "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common enable_pgbuf_inspector yes` |
| `stow/cubrid/.just/db.just:disable-pgbuf-inspector` | Selected native command under installation lock: `crudini --set "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common enable_pgbuf_inspector no` |
| `stow/cubrid/.just/db.just:paramdump-pgbuf-inspector` | Selected native command under installation lock: `cubrid paramdump -C --dump-flag=0x8 "{{ database }}" \| rg enable_pgbuf_inspector` |
| `stow/cubrid/.just/db.just:get-use-system-malloc` | Selected native command under installation lock: `crudini --get "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common use_system_malloc \|\| true` |
| `stow/cubrid/.just/db.just:enable-use-system-malloc` | Selected native command under installation lock: `crudini --set "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common use_system_malloc yes` |
| `stow/cubrid/.just/db.just:disable-use-system-malloc` | Selected native command under installation lock: `crudini --set "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common use_system_malloc no` |
| `stow/cubrid/.just/db.just:get-unfill-factor` | Selected native command under installation lock: `crudini --get "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common unfill_factor \|\| true` |
| `stow/cubrid/.just/db.just:set-unfill-factor` | Selected native command under installation lock: `crudini --set "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common unfill_factor 0.0` |
| `stow/cubrid/.just/db.just:get-port` | Selected native command under installation lock: `crudini --get "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common cubrid_port_id` |
| `stow/cubrid/.just/db.just:set-port` | Selected native command under installation lock: `crudini --set "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common cubrid_port_id "$CUBRID_CUBRID_PORT_ID"` |
| `stow/cubrid/.just/db.just:get-data-buffer-size` | Selected native command under installation lock: `crudini --get "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common data_buffer_size` |
| `stow/cubrid/.just/db.just:set-data-buffer-20g` | Selected native command under installation lock: `crudini --set "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common data_buffer_size 20G` |
| `stow/cubrid/.just/db.just:set-data-buffer-50g` | Selected native command under installation lock: `crudini --set "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common data_buffer_size 50G` |
| `stow/cubrid/.just/db.just:set-data-buffer-512m` | Selected native command under installation lock: `crudini --set "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}" common data_buffer_size 512m` |
| `stow/cubrid/.just/db.just:edit-config` | Selected native command under installation lock: `nvim "${CUBRID_CONF_FILE:-$CUBRID/conf/cubrid.conf}"` |
| `stow/cubrid/.just/db.just:create` | Workenv DB helper `create "$database"` (no legacy authority) |
| `stow/cubrid/.just/db.just:delete` | Workenv DB helper `delete "$database"` (no legacy authority) |
| `stow/cubrid/.just/db.just:recreate` | Workenv DB helper `recreate "$database"` (no legacy authority) |
| `stow/cubrid/.just/db.just:start` | Selected native command under installation lock: `cubrid server start "$database"` |
| `stow/cubrid/.just/db.just:stop` | Selected native command under installation lock: `cubrid server stop "$database"` |
| `stow/cubrid/.just/debug.just:csql-cs` | Selected native command under installation lock: `cgdb --args csql -udba testdb` |
| `stow/cubrid/.just/debug.just:csql-sa` | Selected native command under installation lock: `cgdb --args csql -udba testdb -S` |
| `stow/cubrid/.just/debug.just:server-interactive` | Selected native command under installation lock: `bash -euc` |
| `stow/cubrid/.just/debug.just:server` | Selected native command under installation lock: `bash -euc` |
| `stow/cubrid/.just/debug.just:unloaddb-cs` | Selected native command under installation lock: `\` |
| `stow/cubrid/.just/debug.just:unloaddb-sa` | Selected native command under installation lock: `\` |
| `stow/cubrid/.just/debug.just:loaddb-cs` | Selected native command under installation lock: `\` |
| `stow/cubrid/.just/debug.just:attach-unloaddb` | Selected native command under installation lock: `bash -euc` |
| `stow/cubrid/.just/oos.just:test-isolation` | Selected native command under installation lock: `cubrid-oos-isolation-test.sh {{ TARGET }}` |
| `stow/cubrid/.just/profile.just:perf-record-server` | Selected native command under installation lock: `bash -euc` |
| `stow/cubrid/.just/profile.just:check-simd-native` | Selected native command under installation lock: `objdump -d "$CUBRID/lib/libcubrid.so" \| rg metric_cos_gt -A 5 \| rg ymm \| wc -l` |

## Other entry points and historical material

| Caller / file group | Disposition |
| --- | --- |
| `stow/cubrid/.envrc` | Retained cheap CLI selection; build-only clears inherited runtime, mismatch fails |
| `cubrid-justfiles`, `my-cubrid-init.sh`, `stow-create.sh` | Retained build preparation/stowing only; explicitly distinct from init |
| `aliases.sh` | Retained PATH/just/worktree launchers; no legacy storage selection |
| `aliases.nu` cubrid-use/reset | Migrated from `.cub/db/.../commondb` to public CLI; clear selection on reset |
| `cub-env.sh`, `cub-env.nu`, `cub.sh`, `cubrid-start.sh` | Migrated whole-instance selection; preserve command arguments and arbitrary requested DB |
| `my-cubrid-pwddb`, `my-cubrid-pwddb-getname` | Forward only to workenv helper; conventional testdb default; optional DB name for lifecycle |
| `_cubrid_database.py` | Removed manifest authority and binary-independent cleanup; new bounded helper uses CLI/native commands |
| `my-cubrid-runtime` | Retired stub, every action refuses with explicit replacement and zero mutation |
| `my-cubrid-process-select` | Exact selected executable, complete instance environment, DB/utility role, process generation recheck |
| `csql.sh` | Retained interactive selector; explicit SA/CS options forwarded without injected conflicting mode |
| `cub-auto` | Native status/mode convenience; exact DB matching, preserves explicit SA/CS flags and status errors |
| PATH `cubrid-ini-fzf` | Separate repo topic: respect selected config, preserve installed config; 17 tests |
| PATH `cmake-build-target-fuzzy.sh` | Shared caller retired in favor of protected `core::target` |
| PATH `cubrid-binary-source-dir` | Retained native client/server build identity check |
| Focused testkit skills/common, cubrid-build skill | No legacy command/manifest consumer found; existing disposable-suite/container boundaries remain independent |
| Bash/Nushell configuration | Existing PATH/source entries retained; shell history is historical, never rewritten |
| 105 registered source worktrees' regular `.envrc`, `justfile`, `local.just` | Read-only audit found no extra direct legacy entry calls; shared links adopt only after main merge |
| `docs/pwddb-design.md`, runtime transactions, latency report, dated review | Preserved and explicitly labelled historical |
| ADR-0001 / CONTEXT | Superseded by ADR-0002 and current workenv vocabulary |
| CLI design interview, tickets and dated evidence | Historical evidence retained unchanged; it does not prove the new recipes |

## Verification migration

| Retired coverage | Preserved invariant / new evidence |
| --- | --- |
| Legacy manifest initialization/transactions | CLI `test_state.py`: explicit init, interrupted state, preservation, readiness; no manifest engine remains |
| Legacy allocation/claims (`runtime-claims-test.py`) | CLI `test_cli.py` and `test_reclamation.py`: conflicts, concurrency, namespace visibility, reclamation limits; obsolete private legacy implementation tests removed |
| Legacy owner/diagnostic inference | CLI `test_doctor.py` and native read-only doctor; new process-selector native test |
| Legacy helper lifecycle (`pwddb-test.py`) | Public recipe/CLI tests: duplicates, arbitrary names, unrelated-row preservation, failure retention, external/mixed/symlink refusal, template failures |
| Legacy guard CLI (`runtime-guard-test.py`) | Every retired action refuses without changing historical artifacts |
| Runtime locks | Existing daemon FD/non-bypass/status tests retained; new compile concurrency, native-busy replacement/deletion, signal-cleanup lifetime and stdin tests |
| Shared environment/recipes | 14 existing cases ported; container ownership/signal/foreign-name tests retained |
| Workenv integration | Public cross-repo no-db selection, config isolation, explicit stop/build and mismatch checks |

The new `tests/workenv-native-migration.py` freezes its tooling snapshot and
records file hashes, exact commands, return codes, timings and owned process
cleanup in a unique fixture evidence directory. It exercises the actual shared
recipe, native creation/deletion/loading and multi-instance use. The original
failing recipe was reproduced in `cwe-migration-n1alzfit` without creating a DB.
Intermediate attempts are retained as failed harness runs, not claimed passes.

Final evidence is recorded below. The [two-axis review](complete-workenv-review.md)
found one prerequisite-order defect, now fixed and independently rechecked; no
findings remain.

## Limits

Creation receipts apply to new CLI-created databases, including direct CLI
creation and default init. Earlier/reused DBs remain manual-review cases. A
receipt does not authorize deleting external storage. This task does not clean
old legacy metadata, user DBs, global allocations or unrelated worktrees.

Native proof uses copied Linux debug CUBRID installations, ordinary local storage
and normal shutdown. It does not establish cross-version compatibility, crash
recovery, malformed engine-volume safety or a sandbox for arbitrary tests.
Direct uncoordinated launch races and processes hidden in other namespaces are
outside the cooperative installation lock. Existing native-process observation
has that limitation; no protection was silently replaced by a DB lock.

## Candidate verification

- CLI public suite: **37 passed**. Personal tooling: **40 passed** (15 lock,
  15 environment/container regression, 8 lifecycle, 1 cross-repo, 1 retirement).
  Selected-config editor: **17 passed**. Raw outputs are in
  [unit evidence](../tests/evidence/complete-workenv/cli-tests.txt) and sibling logs.
- [Actual recipe/native flow](../tests/evidence/complete-workenv/native/results.json):
  no-db → create, duplicate preservation, direct SA SQL, additional arbitrary DB,
  external/mixed refusal, running-owner refusal and health, busy-install deferral,
  selected PID, A/B noninterference, demodb create/load/recreate, composed
  stop/recreate/start, cheap reentry/A→B, allocated-port restoration, read-only
  doctor, CLI-created internal DB deletion, explicit stop-and-build and SQL/data
  preservation after restarting. All fixture-owned processes stopped normally.
- [Final lifecycle probe](../tests/evidence/complete-workenv/native/final-lifecycle.json)
  reruns actual create/delete after adding config validation and proves unchanged
  non-target registry bytes. Final copied build is **11.5.0.2640-d0311e1**;
  [binary hashes](../tests/evidence/complete-workenv/native/provenance.json) match
  between A/B and the recorded snapshot. The source installation advanced during
  this task's earlier trials; we did not revert or modify it.
- [Real shared build/environment flow](../tests/evidence/complete-workenv/environment/results.json):
  shared just configure/build/install before init, **ctest before and after init**
  (one actual tiny C test), explicit native initialization and SQL, direnv A→B,
  repeated-entry syscall traces excluding init/doctor/native execution. This is
  a tooling boundary test, not an engine source rebuild.
- [Real persistent Podman flow](../tests/evidence/complete-workenv/container/results.json):
  build-only source, read-only bind-mounted harmless executables, completed test
  with container still alive, install/delete blocked with 75, supervisor SIGTERM,
  verified owned-container removal, then lock acquisition succeeds. This proves
  container lifetime coordination, not CUBRID SQL execution inside that container.
- Bash syntax, Python compilation, Nushell selection/reset and Git whitespace
  checks passed. Existing native/source installations and legacy metadata were
  read-only inputs. A read-only audit covered 105 source-worktree entry files.

The initial Podman harness used this host's private TMPDIR, which rootless nomap
could not traverse. Using `/tmp` and creating the fixture's ordinary log/tmp/var
mount directories resolved setup without changing global permissions. Earlier
failed harness attempts are archived separately in
[trial evidence](../tests/evidence/complete-workenv/trial-evidence.json), including corrected
INI-spacing/tab-registry assumptions and one trial that edited a running Bash
supervisor. The native harness now freezes its tooling scripts before execution.

Doctor correctly reported an owned stale `sp_demodb.sock` after standalone work.
Its read-only artifact comparison passed; exact fixture-only cleanup verified
no matching process and no binding before unlinking that socket, then doctor
passed. Production doctor remains read-only, and no user socket was removed.

The review fix is covered by eight lifecycle tests and a
[native-file preservation probe](../tests/evidence/complete-workenv/native/recreate-preflight.json):
both demodb recreation recipes refuse before deletion when either required sample
file is missing; all internal DB file hashes, receipts and registration bytes are
unchanged. Readability is also checked before deletion.

[Fixture cleanup](../tests/evidence/complete-workenv/cleanup.json) removed only this
task's nine native fixture roots, three container fixture roots and fifteen recorded
short-temp directories (about 13.3 GB of disposable copies). Their evidence was
archived first. No matching accessible native process or Unix binding remained;
all three named containers were absent. The two unreadable same-user process
environments belonged to pre-existing sd-pam/SSH processes. No global process or
IPC cleanup was used. Source/user worktrees, DBs and legacy migration artifacts
were preserved.

## Local application pending

All three changes must be applied together: `cubrid-workenv` supplies provenance,
`my-cubrid` supplies the migrated recipes/helpers, and `cubrid-ini-fzf` respects the
selected config. Candidate code: CLI `ff01097`, tooling `7e2cce4` + review fix
`fb021d4`, editor `4340da2`. A final evidence commit follows those code commits.

The three main worktrees remain clean at their original bases. Under the user's
AGENTS.md step 5, one final confirmation is required to rebase these topics onto
their current local main branches and fast-forward merge them. Shared recipe,
CLI and editor symlinks will then immediately use these changes. Remote publication
is a separate operation. Task branches/worktrees remain available until approval.
