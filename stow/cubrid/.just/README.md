# Personal CUBRID just modules

The root `justfile` intentionally exposes only the stable build contract:

- `prepare`, `configure`, `compile`, `install`
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
- `maint`: formatting and build-tree maintenance
- `profile`: perf and uftrace helpers
- `oos`: shared OOS preparation and isolation testing

`compat.just` contains private compatibility aliases for former flat recipe
names. New callers should use namespaced commands. Remove compatibility entries
only after confirming their old names are no longer used.

Each worktree may provide an optional `local.just` directory managed by
`stow-create.sh`. Ticket-specific scripts and SQL belong there instead of in
the shared modules.

Every module recipe explicitly uses the root `justfile` directory as its
working directory. This preserves behavior when `just` is invoked below the
worktree root even though the module sources are stowed symlinks.
