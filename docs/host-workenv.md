# Host work environments

Use this guide when preparing a source worktree, selecting a preset or installation,
loading host test settings, or diagnosing database/resource selection. Containers
continue to use their own initialization and storage; host `init` is not a prerequisite.

## Prepare, build, initialize

Discover the live source-worktree recipes with `just --list` and `just --show build`.
Prepare missing stowed build files through the existing preparation recipe, select
`PRESET_MODE`, then configure and build through `direnv exec . just configure` and
`direnv exec . just build`. Build and install preserve databases and never initialize
or ensure one automatically.

Install the reviewed `cub-workenv` CLI on your PATH, or export `CUB_WORKENV_CLI`
with its absolute executable path. The source checkout and its Python package must
remain together. `CUB_WORKENV_INSTALL` explicitly selects a non-default install
prefix; otherwise the existing `$HOME/.cub/install/<worktree-basename>/<preset>`
selection applies. Worktrees with the same basename need distinct explicit prefixes.
Set the selection in the worktree's exported direnv configuration before loading
its shared `.envrc`; keep it consistent with the build install destination.

After building and installing, initialize deliberately:

```sh
cub-workenv init --worktree "$PWD" --install "$CUBRID" --preset "$PRESET_MODE"
direnv reload
```

The shared loader compares the worktree, preset, and installation to completed
metadata and loads the generated artifact. It does not run CUBRID, allocate
resources, scan processes, hash installations, or perform full validation. Missing
state gives a build-only environment and initialization guidance. Partial state
and changed selections fail with diagnostic guidance; they do not become an
implicit migration or preset takeover.

## Run and diagnose

In the prepared environment, ordinary `cubrid` and `csql` commands may run directly.
All child processes must retain its installation, configuration, registry, port,
and TMP selection. Existing testcase/tool PATH entries and CTP paths remain available.
`cub-workenv run` is not required. Coordinated recipes still protect an installation
against concurrent replacement and now load the new selection without requiring a
legacy runtime manifest. The container recipe uses an installation lock without
requiring a host database environment.

Use `cub-workenv doctor --worktree "$PWD"` explicitly for diagnosis. It reports
problems without repairing them. After rebuilding, run diagnosis when concerned
about the selected installation. Repeating `init` preserves existing state; it does
not switch presets or repair an environment.

The old `my-cubrid-pwddb` helper supports name/list lookup for a selected new work
environment. Its legacy create/ensure/recreate/delete operations refuse new storage
with guidance. Use `cub-workenv create-db` for new databases and explicit ordinary
CUBRID utilities after inspecting the selected registry for deletion/recreation.
Additional registry names are valid; `my-cubrid-pwddb-getname` reports the conventional
`testdb` default. Existing legacy environments retain their old helper path.

For a shared physical DB, ordinary client connections to the running server are
allowed. Native exclusion of a second server or standalone opener was verified
only for the documented normal Linux/local-filesystem path on one build. See the
cubrid-workenv repository's `experiments/native-db-exclusion/README.md` for evidence
and limits. Initialization avoids known resource conflicts; it is not a sandbox
for arbitrary test scripts. Inspect runners with broad process or IPC cleanup.
Stop only processes belonging to the selected environment; preserve native busy-DB
errors and other environments' data and resources.

## Apply the reviewed integration

The CLI and personal-tooling changes are reviewed as separate repository commits.
Merge them through the local worktree workflow before changing live shared symlinks
or PATH. This implementation does not globally install the CLI, restow existing
worktrees, migrate legacy manifests/databases, or change user installations.
For an existing worktree, inspect its legacy state and data before opting into a
new environment; ambiguous artifacts require manual review rather than automatic
adoption. Keep the selected CLI and shared tooling revisions compatible.
