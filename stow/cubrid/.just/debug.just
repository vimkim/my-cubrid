set minimum-version := "1.55.0"
set no-cd
set shell := ["sh", "-cu"]

# Debug csql connected to testdb.
[working-directory(justfile_directory())]
csql-cs:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- cgdb --args csql -udba testdb

# Debug standalone csql connected to testdb.
[working-directory(justfile_directory())]
csql-sa:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- cgdb --args csql -udba testdb -S

# Attach to a selected testdb server from this worktree and installation.
[working-directory(justfile_directory())]
server-interactive:
    #!/usr/bin/env bash
    set -euo pipefail
    exec "$HOME/my-cubrid/bin/cubrid-build-coordinator.sh" runtime 300 --database testdb -- bash -euc '
      pid="$($HOME/my-cubrid/bin/my-cubrid-process-select server --interactive)"
      exec cgdb -p "$pid" "$CUBRID_BUILD_DIR/bin/cub_server"
    '

# Attach to the current worktree's testdb server.
[working-directory(justfile_directory())]
server:
    #!/usr/bin/env bash
    set -euo pipefail
    exec "$HOME/my-cubrid/bin/cubrid-build-coordinator.sh" runtime 300 --database testdb -- bash -euc '
      pid="$($HOME/my-cubrid/bin/my-cubrid-process-select server)"
      exec cgdb -p "$pid" "$CUBRID_BUILD_DIR/bin/cub_server"
    '

# Debug client-server unloaddb.
[working-directory(justfile_directory())]
unloaddb-cs:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- \
        cgdb --args cubrid unloaddb testdb -C -t 0 -v

# Debug standalone unloaddb.
[working-directory(justfile_directory())]
unloaddb-sa:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- \
        cgdb --args cubrid unloaddb testdb -S -t 0 -v

# Debug client-server loaddb.
[working-directory(justfile_directory())]
loaddb-cs:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- \
        cgdb --args cubrid loaddb -udba -C -v testdb -d ./testdb_objects

# Open a csql core with cgdb.
[working-directory(justfile_directory())]
core-csql CORE:
    cgdb csql core {{ CORE }}

# Attach to a selected testdb unloaddb from this worktree and installation.
[working-directory(justfile_directory())]
attach-unloaddb:
    #!/usr/bin/env bash
    set -euo pipefail
    exec "$HOME/my-cubrid/bin/cubrid-build-coordinator.sh" runtime 300 --database testdb -- bash -euc '
      pid="$($HOME/my-cubrid/bin/my-cubrid-process-select unloaddb --interactive)"
      exec cgdb -p "$pid" "$CUBRID_BUILD_DIR/bin/cubrid"
    '

# Open the most recent csql coredump through coredumpctl.
[working-directory(justfile_directory())]
coredump-csql:
    coredumpctl debug --debugger=cgdb csql

# Delete local core files after explicit confirmation.
[working-directory(justfile_directory())]
delete-cores:
    @gum confirm
    /bin/rm -rf core.*

# Replay the current rr trace.
[working-directory(justfile_directory())]
rr-replay:
    rr replay
