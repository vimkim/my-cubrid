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
