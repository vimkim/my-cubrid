# Personal CUBRID just modules

## Ownership

`stow/cubrid` is the worktree-local interface for CUBRID server development and
maintenance. Its recipes may depend on an initialized worktree and environment,
including `$CUBRID`, `$CUBRID_BUILD_DIR`, `$CUBRID_DATABASES`, and the current
source-tree layout.

Globally accessible launchers used across CUBRID work contexts belong in
`cubrid-justfiles`. Put a recipe here when it operates on the active worktree or
runtime; put it in `cubrid-justfiles` when it helps select, initialize, or
coordinate work contexts without depending on the stowed worktree interface.

The root `justfile` intentionally exposes only the stable build contract:

- `prepare`, `prepare-debug-gcc`, `configure`, `compile`, `install`
- `build`, `ctest`, `test`, `build-test`
- `build-wait`, `install-wait`, `stop-and-build`

Running `just` lists these commands and the available namespaces. `test` is
currently an honest alias for the configured ctest suite; it does not claim to
run CTP SQL regression tests.

Shared recipes live in these namespaces:

- `core`: preset-aware build, install, ctest, cache, target, and stow workflows
- `db`: local database lifecycle, server control, csql, and configuration
- `workenv`: saved settings, ports/SHM keys, all-worktree reports, and diagnostics
- `ctp`: focused CTP shell-test debugging
- `debug`: cgdb, core, and rr helpers
- `github`: pull-request helpers, including dev2 review requests
- `maint`: formatting and build-tree maintenance
- `profile`: perf and uftrace helpers
- `oos`: shared OOS preparation and isolation testing

`compat.just` contains private compatibility aliases for former flat recipe
names. New callers should use namespaced commands. Remove compatibility entries
only after confirming their old names are no longer used.

Each worktree may provide an optional `local.just` directory managed by
`stow-create.sh`. Ticket-specific scripts and SQL belong there instead of in
the shared modules.

`just prepare` also stows `AGENTS.override.md`, which replaces the stale root
`AGENTS.md` for Codex and loads `/home/vimkim/my-cubrid/CUBRID.md`. Maintain the
override in `my-cubrid/stow/cubrid/AGENTS.override.md`; edits reach every linked
worktree. Optional `AGENTS.user.md` files belong in individual worktree roots.
Preparation adds both root filenames to Git's local `info/exclude`, shared by
linked worktrees, without modifying the upstream `.gitignore` or `AGENTS.md`.
Nested instruction files remain applicable. Start a new Codex session after
preparation or instruction edits so discovery runs again.

Every module recipe explicitly uses the root `justfile` directory as its
working directory. This preserves behavior when `just` is invoked below the
worktree root even though the module sources are stowed symlinks.


## Work environment reports

Run these from a prepared CUBRID worktree (or any directory below it):

| Command | Output |
| --- | --- |
| `just workenv::status` | Complete expected isolation environment, saved allocations, disk settings, socket/info paths, and database storage registrations |
| `just workenv::all-details` | The same complete isolation reports for every Git worktree |
| `just workenv::all` | Allocation table for all Git worktrees of the current repository |
| `just workenv::json` | Current worktree's full saved state in a JSON report |
| `just workenv::all-json` | Full JSON reports for all Git worktrees, suitable for saving or processing with `jq` |
| `just workenv::config` | Actual workenv `cubrid.conf` and `cubrid_broker.conf` contents |
| `just workenv::doctor` | Public CLI's read-only diagnostics for this worktree |
| `just workenv::doctor-all` | Read-only diagnostics for every Git worktree, continuing after failures |
| `just workenv::env` | Public CLI's environment-loading shell code, printed without executing it |

`status` and `all` read schema-1 `.cub-workenv/state.json` snapshots. Saved
`ready` means initialization completed, not that servers are running or settings
remain healthy. SHM values are allocated keys, not kernel segment IDs or memory
sizes. Use `config` to inspect edited settings and `doctor` for live resource
evidence. Reports never initialize environments, allocate resources, start/stop
servers, or source generated shell code. Isolation details cover the managed
host master/server/broker/PL setup, including the explicit `CUBRID_TMP`,
`CUBRID_DATABASES`, configuration variables and binary/library prefixes. They
are expected values, not measurements of a running process. Disk settings are
reported separately; HA, Manager and containers require their own configuration.

All-worktree commands include uninitialized worktrees and registered paths that
are now missing; they cover the current Git repository, not unrelated clones.
Malformed/unsupported state or missing worktrees produce error entries and a
nonzero exit after reporting the remaining rows. An ordinary uninitialized
worktree is not a reporting error. `doctor-all` returns nonzero if any doctor
invocation fails. JSON reports contain `worktree`, `state` (or null), and `error`
(or null). Initialized worktrees also include `isolation`: expected environment,
current disk settings, database registrations, socket/info paths and inspection
errors. Reports retain the complete saved state.

Helpers honor `MY_CUBRID` for candidate tooling; CLI wrappers honor
`CUB_WORKENV_CLI`. After adding this module, run `just core::stow-shared` in
existing worktrees whose `.just` directory was individually stowed, so the new
module link exists. New worktrees receive it through `just prepare`.


## Release numeric allocations

| Command | Action |
| --- | --- |
| `just workenv::reset` | Preview release for this worktree, using its recorded namespace |
| `just workenv::reset-apply` | Release this idle worktree's ports and SHM assignments |
| `just workenv::reset-all` | Preview release for the default host allocation namespace |
| `just workenv::reset-all-apply` | Release all idle numeric assignments in that namespace |

These delegate to `cub-workenv reset` / `cub-workenv reset-all` and require the companion CLI's
reset support. For a custom namespace use the CLI's `--state-home PATH`.
Unlike `all` reports, `reset-all` follows the allocation registry across Git
repositories. Stop affected instances first. Occupied ports, existing SHM
segments, live sockets, uncertain processes, or a cooperating init/create-db
operation block reset. The commands never kill processes or remove kernel IPC.

Only numeric assignments are released. Unique TMP/install/configuration/storage
paths, databases, logs, registry contents and non-resource tuning remain.
Environment loading is disabled until explicit `cub-workenv init` with the same
recorded install/preset/state-home. Reinitialization reuses unique paths and
allocates the lowest available numeric values in the requested pool; its order
determines assignments after a full reset. Reload old shells after the operation.
See the CLI repository's `docs/reset.md` for the lifecycle and failure contract.

## Prune missing worktrees

```sh
just workenv::prune        # Preview
just workenv::prune-apply  # Apply eligible entries
just workenv::all          # Check remaining worktrees
```

Prune inspects the current Git repository's registered linked worktrees. Missing
entries without an allocation in the selected namespace need only Git metadata
cleanup. Matching allocations are released only after the allocator's deleted,
inactive-worktree checks pass. Existing and locked worktrees, symlink/uncertain
paths, occupied ports/SHM, remaining TMP entries and live/uninspectable owners
are retained with a `KEEP` reason. Safe entries can be processed even when others
are blocked; retained missing entries make the command exit nonzero.

The namespace defaults to this worktree's recorded state-home, otherwise the
host default. Use `cub-workenv prune --worktree "$PWD" --state-home PATH` for an
explicit namespace (add `--apply` to act). Prune does not search unrelated state
homes or allocation-only records whose Git registration was already removed.
It preserves branches, installations, TMP directories, external databases and
all existing worktrees. It does not kill processes, remove kernel IPC or delete
physical data. See `cubrid-workenv/docs/prune.md` for scope and recovery details.
