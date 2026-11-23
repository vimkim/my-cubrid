set minimum-version := "1.55.0"
set no-cd
set shell := ["sh", "-cu"]

# Running the module name alone lists its recipes instead of running the first one.
[private]
[working-directory(justfile_directory())]
default:
    @just --list workenv

# Show saved settings, allocated ports, SHM keys, and paths for this worktree.
[working-directory(justfile_directory())]
status:
    @python3 "${MY_CUBRID:-$HOME/my-cubrid}/bin/cubrid-workenv-report.py" status

# Summarize saved allocations for every Git worktree, including uninitialized ones.
[working-directory(justfile_directory())]
all:
    @python3 "${MY_CUBRID:-$HOME/my-cubrid}/bin/cubrid-workenv-report.py" all

# Export this worktree's saved state as JSON.
[working-directory(justfile_directory())]
json:
    @python3 "${MY_CUBRID:-$HOME/my-cubrid}/bin/cubrid-workenv-report.py" json

# Export all Git worktrees' saved states as JSON, including installation and paths.
[working-directory(justfile_directory())]
all-json:
    @python3 "${MY_CUBRID:-$HOME/my-cubrid}/bin/cubrid-workenv-report.py" all-json

# Inspect initialization, settings, and native resource evidence without changing them.
[working-directory(justfile_directory())]
doctor:
    @"${CUB_WORKENV_CLI:-cub-workenv}" doctor --worktree "$PWD"

# Emit schema-1 JSON diagnosis for this worktree without changing state.
[working-directory(justfile_directory())]
doctor-json:
    @"${CUB_WORKENV_CLI:-cub-workenv}" doctor --worktree "$PWD" --json

# Diagnose every Git worktree; continue after failures and return nonzero if any fail.
[working-directory(justfile_directory())]
doctor-all:
    @python3 "${MY_CUBRID:-$HOME/my-cubrid}/bin/cubrid-workenv-report.py" doctor-all

# Print the actual workenv CUBRID and broker configuration files.
[working-directory(justfile_directory())]
config:
    @python3 "${MY_CUBRID:-$HOME/my-cubrid}/bin/cubrid-workenv-report.py" config

# Print environment-loading shell code; this does not change the calling shell.
[working-directory(justfile_directory())]
env:
    @"${CUB_WORKENV_CLI:-cub-workenv}" env --worktree "$PWD"


# Show complete isolation settings and storage paths for every Git worktree.
[working-directory(justfile_directory())]
all-details:
    @python3 "${MY_CUBRID:-$HOME/my-cubrid}/bin/cubrid-workenv-report.py" all-details

# Preview release of the current worktree's numeric allocations; preserve paths/data.
[working-directory(justfile_directory())]
reset:
    @"${CUB_WORKENV_CLI:-cub-workenv}" reset --worktree "$PWD"

# Release the current worktree's idle ports/SHM assignments; explicit init required.
[working-directory(justfile_directory())]
reset-apply:
    @"${CUB_WORKENV_CLI:-cub-workenv}" reset --worktree "$PWD" --apply

# Preview release of all numeric allocations in the default host namespace.
[working-directory(justfile_directory())]
reset-all:
    @"${CUB_WORKENV_CLI:-cub-workenv}" reset-all

# Release all idle numeric allocations in the default host namespace; preserve paths/data.
[working-directory(justfile_directory())]
reset-all-apply:
    @"${CUB_WORKENV_CLI:-cub-workenv}" reset-all --apply

# Preview pruning missing Git worktree registrations and their idle allocations.
[working-directory(justfile_directory())]
prune:
    @"${CUB_WORKENV_CLI:-cub-workenv}" prune --worktree "$PWD"

# Prune eligible missing worktrees and release allocations; preserve branches and paths.
[working-directory(justfile_directory())]
prune-apply:
    @"${CUB_WORKENV_CLI:-cub-workenv}" prune --worktree "$PWD" --apply

# Preview reclamation of deleted or orphaned allocations across the allocation registry.
[working-directory(justfile_directory())]
gc:
    @"${CUB_WORKENV_CLI:-cub-workenv}" gc

# Reclaim eligible deleted or orphaned allocations and clean unbound TMP sockets/dirs.
[working-directory(justfile_directory())]
gc-apply:
    @"${CUB_WORKENV_CLI:-cub-workenv}" gc --apply --clean-tmp

# Preview removal of unbound stale Unix sockets in this worktree's TMP directory.
[working-directory(justfile_directory())]
clean-sockets:
    @"${CUB_WORKENV_CLI:-cub-workenv}" clean-sockets --worktree "$PWD"

# Remove verified unbound stale Unix sockets in this worktree's TMP directory.
[working-directory(justfile_directory())]
clean-sockets-apply:
    @"${CUB_WORKENV_CLI:-cub-workenv}" clean-sockets --worktree "$PWD" --apply

# Switch an idle ready worktree to another dedicated installation and preset.
[working-directory(justfile_directory())]
switch-preset preset="" install="":
    #!/usr/bin/env sh
    set -eu
    p="{{preset}}"
    i="{{install}}"
    if [ -z "$p" ]; then p="${PRESET_MODE:-}"; fi
    if [ -z "$i" ]; then i="${CUBRID:-}"; fi
    if [ -z "$p" ] || [ -z "$i" ]; then
        printf 'Usage: just workenv::switch-preset <preset> <install> (or load PRESET_MODE and CUBRID via direnv)\n' >&2
        exit 2
    fi
    exec "${CUB_WORKENV_CLI:-cub-workenv}" switch-preset --worktree "$PWD" --preset "$p" --install "$i"

# Preview safe teardown of this worktree's allocation before removal or re-init.
[working-directory(justfile_directory())]
deinit:
    @"${CUB_WORKENV_CLI:-cub-workenv}" deinit --worktree "$PWD"

# Preview unregistration of a DB (or --prune-missing when name="--prune-missing").
[working-directory(justfile_directory())]
unregister-db target="":
    #!/usr/bin/env sh
    set -eu
    if [ -z "{{target}}" ]; then
        printf 'Usage: just workenv::unregister-db <db-name|--prune-missing>\n' >&2
        exit 2
    fi
    exec "${CUB_WORKENV_CLI:-cub-workenv}" unregister-db --worktree "$PWD" "{{target}}"
