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
| `just workenv::status` | Saved state/stage, preset, installation, allocated ports, SHM keys in hex and decimal, and configuration/registry/socket paths |
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
servers, or source generated shell code.

All-worktree commands include uninitialized worktrees and registered paths that
are now missing; they cover the current Git repository, not unrelated clones.
Malformed/unsupported state or missing worktrees produce error entries and a
nonzero exit after reporting the remaining rows. An ordinary uninitialized
worktree is not a reporting error. `doctor-all` returns nonzero if any doctor
invocation fails. JSON reports contain `worktree`, `state` (or null), and `error`
(or null), and retain the complete saved state for initialized worktrees.

Helpers honor `MY_CUBRID` for candidate tooling; CLI wrappers honor
`CUB_WORKENV_CLI`. After adding this module, run `just core::stow-shared` in
existing worktrees whose `.just` directory was individually stowed, so the new
module link exists. New worktrees receive it through `just prepare`.
