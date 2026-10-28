# Host work environments

`cub-workenv` is the sole authority for host preparation, resource allocation,
installation/preset selection and database registration. The old runtime engine
is retired; its metadata and existing data are preserved. Containers keep their
independent environment and storage.

## Prepare, build, initialize

Discover recipes with `just --list` and `just --show build`. For missing shared
files, run `just -f ~/my-cubrid/cubrid-justfiles/justfile -d . prepare-build`.
`my-cubrid-init.sh` remains a **build preparation** shortcut, not host initialization.
Select the preset, then run `just configure` and `just build` to produce artifacts.
Run `just install` to install existing artifacts, or `just build-and-install` to
build and install together. `just configure-build` omits installation;
`just configure-build-and-install` includes it.
Building, installation, and `ctest` work without host initialization.
A successful build or installation never creates a database or switches an existing workenv.

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

The Nushell `cs` alias calls `csql.sh`, which selects a registered database,
chooses SA/CS mode, and checks the selected client's source tree against the
running server before launching `csql-future`. Install the independent
wrapper with `just sync` in `~/gh/csql-future`; its underlying `csql` comes
from the active environment's `PATH`. Interactive sessions gain persistent
history, Up/Down recall, Ctrl+R search, and multiline editing. File, command,
pipe, and redirected invocations pass through to csql without recording history.

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

Configuration recipes use `CUBRID_CONF_FILE`. Use `just cubrid-conf-tui [DATABASE]`
for interactive `[common]` editing; `cubrid-ini-fzf` and its `db::ini` recipe
are retired. Broader section editing is tracked in the TUI's
[README TODO](https://github.com/vimkim/cubrid-conf-tui#todo).
`db::set-port` restores the allocated master port,
not a fixed personal port. Deliberate resource reassignment needs a separately
reviewed transition; editing the port is not allocation. PID selection compares
executable identity, DB/utility role and the full instance environment, then
rechecks process generation. `my-cubrid-process-select --database NAME` also
supports non-default DBs. Startup cwd alone is not instance identity.

## Daemon startup and captured output

[CBRD-27443](https://jira.cubrid.org/browse/CBRD-27443) can keep a caller waiting
after the startup command exits. Background master, server, or PL processes can
retain the write end of the caller's output pipe. A reader then waits for EOF.
This affects `| cat`, `| tee`, command substitution, and subprocess pipe capture.
Python `capture_output=True` can wait for EOF after its direct child exits.
A wrapper or PTY alone does not establish that every writer closed its descriptors.

### Start a server from an agent

1. Select the work environment through `cub-workenv` and load it with `direnv`.
   Use an existing registered database. Initialize a new environment explicitly
   when the task requires one.
2. Send startup stdin to `/dev/null`. Send both stdout and stderr to regular files.
   Apply redirection to the outer command when a recipe or wrapper starts CUBRID.
3. Start the launcher in a separate session when the tool cleans up its process group.
   Affected master startup can keep master in the launcher's group.
4. Wait for the startup command with a deadline. Read its exit code and log files.
   Check the selected server state separately before reporting startup success.

Run this example from a prepared source worktree with a registered `testdb`:

```bash
direnv exec . python3 - <<'PY'
from pathlib import Path
import subprocess
import tempfile

logs = Path(tempfile.mkdtemp(prefix="cubrid-start-"))
with (logs / "stdout.log").open("wb") as stdout, (logs / "stderr.log").open("wb") as stderr:
    launcher = subprocess.Popen(
        ["just", "db::start", "testdb"],
        stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
        close_fds=True, start_new_session=True,
    )
    try:
        rc = launcher.wait(timeout=30)
    except subprocess.TimeoutExpired:
        print(f"Startup command still running: PID={launcher.pid}; logs={logs}", flush=True)
        raise SystemExit(124)
print(f"Startup command exited: rc={rc}; logs={logs}")
raise SystemExit(rc)
PY
```

Read the printed log paths in a separate command. Regular files provide a current
snapshot without waiting for daemon EOF. Keep the files while the daemons use them.
The 30-second limit bounds this example's wait. It is not a CUBRID startup timeout
or proof that recovery is stuck. On expiry, the launcher can still be running.
Inspect the reported PID before retrying or stopping anything.

Python's [`start_new_session=True`](https://docs.python.org/3/library/subprocess.html#subprocess.Popen)
starts the child in a separate session on POSIX. It does not close output pipes.
Use it together with regular-file redirection for an intentionally persistent server.
Check server state again in a later tool call. A launcher exit code alone does not
show that master survived the caller's cleanup.

Use the same environment for a state check. Redirect its output too:

```bash
direnv exec . cubrid server status </dev/null >server-status.log 2>&1
```

### Recover a caller that already waits for EOF

1. Open a separate tool call or terminal in the same work environment.
2. Check whether the startup command exited. Check server state or run a small SQL
   query. A waiting reader does not prove that startup failed.
3. Inspect `/proc/<pid>/fd` for the reader and the selected instance's processes.
   Compare their `pipe:[inode]` targets. Record which processes retain write access.
4. For an isolated instance owned by this test, stop its database through the same
   selected environment. Send cleanup output to regular files as well.
5. If master still retains the pipe, stop the isolated service only when this test
   owns the whole instance. Check its database registrations and process identities first.
   Shared services require the owner's explicit approval before a service-wide stop.
6. Check that owned processes exit and the original reader completes.

Preserve the selected installation, configuration, registry, master port, and TMP
settings during recovery. Avoid global process kills, IPC cleanup, and lock-file deletion.
A process-group timeout can also signal daemons that remain in the caller's group.
It is not a general workaround for descriptor inheritance.

Regular-file capture avoids this output-pipe wait. It does not repair other inherited
descriptors or file locks. Keep the coordinator's descriptor protection for managed
recipes. Use [lock owner inspection](runtime-locks.md#find-the-owner) for a blocked lock.

### Reproduction evidence

On 2026-10-21, Linux debug build `11.5.0.2707` reproduced the exact command
`cubrid server start testdb | cat` in the `thirdparty-reuse-poc` work environment.
The startup command was gone at four seconds, but `cat` still waited at ten seconds.
A `SELECT 1` query succeeded. Master, server, and PL held FD 1 on the same pipe.
Stopping `testdb` left master holding it. Stopping that isolated service released
the pipe, and the pipeline returned 0 without a forced kill.

The regular-file example without a separate session returned 0 in 3.44 seconds.
Master was absent in a later tool call, and SQL failed. The test recorded no signal
trace, so it does not establish which cleanup action removed master.
The documented example with a separate session also returned 0 in 3.44 seconds.
Master, server, and PL survived in a later tool call, and `SELECT 1` succeeded.
Normal database and service stops then completed with no instance processes remaining.

The [captured evidence](evidence/cbrd-27443-startup-capture.json) preserves binary
hashes, pipe owners, command results, and cleanup results. This is an operational
workaround for affected builds, not an engine repair or an assertion about every release.

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

Missing Git worktree entries reported by `workenv::all` can be inspected with
`just workenv::prune` and cleaned with `just workenv::prune-apply`. Only missing,
unlocked linked worktrees are eligible; matching allocations must pass inactivity
checks. Branches, TMP/install/storage paths and existing worktrees are preserved.
Pruning uses the current repository and selected workenv allocation namespace;
blocked entries remain visible with reasons.

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

Busy reports identify accessible live lock holders. Use `just locks` for the
selected build/installation, `just locks-all` for held locks in this user's
coordinator namespace, or `just locks-json` for selected owner data. Inspection
does not acquire locks or initialize the host environment. See
[build and runtime lock architecture](runtime-locks.md) for descriptor ownership,
the build/install split, diagnostic output and visibility limits.

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

`build-and-install --stop-runtime` builds artifacts, obtains the installation
lock, loads the selected host environment, explicitly stops its registered servers/service/broker, waits for
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
