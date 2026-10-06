set minimum-version := "1.55.0"
set no-cd
set shell := ["sh", "-cu"]

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
