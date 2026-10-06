# Host work environments

`cub-workenv` is the sole authority for host preparation, resource allocation,
installation/preset selection and database registration. The old runtime engine
is retired; its metadata and existing data are preserved. Containers keep their
independent environment and storage.

## Prepare, build, initialize

Discover recipes with `just --list` and `just --show build`. For missing shared
files, run `just -f ~/my-cubrid/cubrid-justfiles/justfile -d . prepare-build`.
`my-cubrid-init.sh` remains a **build preparation** shortcut, not host initialization.
Select the preset, configure and build through the worktree's live recipes.
Build/install and `ctest` work without host initialization. A successful build
never creates a database or switches an existing workenv.

After installation, explicitly initialize:

```sh
cub-workenv init --worktree "$PWD" --install "$CUBRID" --preset "$PRESET_MODE"
# Or defer DB creation:
cub-workenv init --worktree "$PWD" --install "$CUBRID" --preset "$PRESET_MODE" --no-db
# Load the prepared environment:
direnv reload
```

Set `MY_CUBRID` to a reviewed tooling checkout to test shared recipes without
restowing globally. `CUB_WORKENV_CLI` can select the reviewed CLI executable;
keep it together with its adjacent Python package. `CUB_WORKENV_INSTALL` chooses
an explicit build/install destination; otherwise the loader uses
`$HOME/.cub/install/<worktree-basename>/<preset>`. Same-basename source worktrees
need different dedicated installation prefixes.

Directory entry loads completed metadata and the environment artifact cheaply.
It performs no DB creation, CUBRID execution, process scan, full installation
hash or automatic migration. Build-only entry clears inherited connection
settings. Partial or mismatched selections fail with diagnostic guidance.

## Commands and database selection

Ordinary `cubrid` and `csql` commands run directly in the prepared environment.
Keep the installation, configuration, registry, master port and TMP selection
together. A→B switching selects B's entire environment even with the same DB name.
`cub-env.sh`, `cub-env.nu` and `cubrid-use` load through the public CLI rather
than constructing legacy DB paths. `cubrid-reset` clears the selected native
variables and paths. Use direnv for build-only shell preparation.

`testdb` is a conventional default, not the only allowed registration. Run from
the source root:

```sh
just db::list-all
just db::create-testdb              # initialized --no-db is valid
just db::create example             # another registered DB name
just db::start example
csql -C -u dba -c 'select 42;' example
just db::stop example
just db::create-demodb              # explicitly creates and loads sample data
just db::csql-sa                    # explicitly -S, testdb
just db::csql                       # explicitly -C, testdb
```

Creation calls `cub-workenv create-db`, refuses an existing name or location,
and preserves other registration bytes. Template failure retains the newly
created DB for inspection. `pwddb-*` recipes and `my-cubrid-pwddb` are compatibility
spellings for this same behavior; they never consult legacy manifests.
`my-cubrid-pwddb-getname` prints the conventional `testdb` default.

Configuration recipes use `CUBRID_CONF_FILE`; the companion `cubrid-ini-fzf`
revision must be applied too. `db::set-port` restores the allocated master port,
not a fixed personal port. Deliberate resource reassignment needs a separately
reviewed transition; editing the port is not allocation. PID selection compares
executable identity, DB/utility role and the full instance environment, then
rechecks process generation. `my-cubrid-process-select --database NAME` also
supports non-default DBs. Startup cwd alone is not instance identity.

## Isolation reports and numeric reset

`just workenv::status` reports the named isolation environment, saved numeric
allocations, current configuration values and DB storage/socket/info paths.
`just workenv::all-details` reports the same for all Git worktrees; `all-json`
exports the complete reports. These are expected settings, not observed process
environments. Use `doctor` for live evidence.

`just workenv::reset` previews release of this worktree's numeric assignments;
`reset-apply` applies after inactivity checks. `reset-all` and `reset-all-apply`
operate on the default host allocation namespace, across repositories. A custom
namespace can be selected through `cub-workenv reset-all --state-home PATH`.
Only ports and broker SHM assignments are released. TMP/install/configuration
paths, databases, logs, registry entries and non-resource tuning remain. Kernel
IPC is not force-removed and owners are not killed. Explicit init with the same
recorded selection is required afterward; reload old shells. See the CLI's
`docs/reset.md` for prerequisites, interruption recovery and reinitialization.

## Internal database deletion and recreation

The user chose automatic lifecycle only for known, wholly internal storage.
`just db::delete NAME`, `just db::recreate NAME`, fixed testdb/demodb recipes,
and the old pwddb aliases apply that contract. Deletion does **not** stop an
owner implicitly. A running native server or standalone opener must reject
`deletedb`, and its error is preserved. `stop-recreate-start-testdb` is the
explicit composition that requests a stop first.

New CLI creation publishes a creation receipt recording registration and primary
volume identity. Reused, migrated and older DBs have no receipt: do not invent
one retrospectively. Before deletion, the helper requires this provenance,
unchanged registration/volume identity, wholly internal data/log/LOB and volume
list paths, and no symlinks, mounts, foreign owners or hard links. Uncertain
storage is preserved for the manual procedure below. The receipt is provenance,
not another runtime authority or a DB lease.

Native deletion uses a private registry and no force/backup-delete option.
Only after success does the helper remove the target row, preserving every
other row and comment. A detected concurrent manual registry edit causes an
error and requires inspection. A native failure never triggers binary-independent
cleanup. Cooperating preparation/deletion uses the CLI's preparation lock;
ordinary runtime commands remain native.

Unknown leftover files and LOB directories survive. Recreation chooses a fresh
internal location, so it can preserve leftovers without recursively clearing
an old directory. A successful delete followed by failed create is reported as
a failed recreation, retaining its evidence; it is not an atomic DB replacement.
These checks are for ordinary local use, not concurrent adversarial filesystem
edits, arbitrary corrupt volume metadata or a guarantee across engine versions.

## Manual database lifecycle

For external, mixed, preexisting/unreceipted, or uncertain storage:

1. Save the selected state and registry. Inspect each physical volume, active/
   archive log, LOB path, backup, link and mount. Confirm the DB's future with its
   owner. An internal pathname alone is insufficient evidence of ownership.
2. Preserve external storage. To detach a registration, stop positively identified
   openers and edit only that row under a separately reviewed procedure; do not
   use native `deletedb` to remove a local reference to external data.
3. If physical destruction of that specific DB is explicitly intended and all
   affected paths are reviewed, use the selected native `cubrid deletedb NAME`
   yourself. Save/reconcile registry bytes because native utilities can rewrite
   unrelated formatting. No automatic recipe bypasses the preservation boundary.
4. To create replacement storage after the row has been deliberately removed,
   archive any matching creation receipt with the reviewed deletion evidence, then
   use `cub-workenv create-db NAME --path /new/empty/location`. Do not erase an
   existing directory to make creation succeed.

For source-worktree removal, follow cubrid-workenv's `docs/database-lifetime.md`:
preserve external targets and user files, inventory exact owned artifacts,
then remove the worktree without force. Software retirement grants no data cleanup.

## Build, installation and persistent container protection

The narrowed `cubrid-build-coordinator.sh` retains the existing lock namespace
and file name to preserve build/install and container callers. It has no legacy
manifest, allocation or DB lifecycle engine. Build operations serialize by
canonical build directory. Installation replacement/deletion takes that lock
and the installation-use lock, then checks native executables under the prefix.
Busy work returns 75 and leaves the instance running; compilation may finish
before installation is deferred. Arbitrary selected CMake targets are protected
conservatively because they may perform installation.

Coordinated host recipes hold the installation-use lock and select with
`cub-workenv env`. The lock belongs to the foreground supervisor, not daemon
descendants. Signals are forwarded while the supervisor retains its locks until
the command/harness exits. Direct native commands are supported, but do not
participate in that cooperative lock; native-process observation is not an atomic
reservation against an unrelated concurrent launcher or other namespaces.

`installation-use` and `ctest` do not require host DB initialization. Persistent
bind-mounted containers retain the supervisor and installation lock until the
owned container is removed. Container cleanup still verifies invocation label
and immutable container ID; unknown/foreign containers are never deleted.
Container startup stays independent of host initialization.

`stop-and-build` compiles, obtains the installation lock, loads the selected host
environment, explicitly stops its registered servers/service/broker, waits for
native executables to exit, then installs. Installation deletion refuses broad
paths and prefixes containing DB volume/log artifacts. It does not delete host
workenv state, external DBs or historical legacy metadata.

## Diagnose and apply

Use `cub-workenv doctor --worktree "$PWD"` for read-only diagnosis. Repeated init
preserves ready state; it is not repair or a preset takeover. Native standalone
work can leave an unbound PL socket pathname. Doctor reports it without removal;
manual cleanup requires exact operation ownership, no matching live process and
no binding. Never use global pkill or IPC cleanup.

Apply the CLI, shared-tooling and selected-config editor commits together through
the local review/rebase/fast-forward workflow. Updating their main checkouts
immediately affects existing symlink consumers; no restow is needed. Until that
approval, use explicit candidate paths. The old `my-cubrid-runtime` command exits
with replacement guidance and preserves all files.

See [migration inventory and evidence](complete-workenv-migration.md) for the
caller dispositions, protection mapping, test coverage and remaining limits.
