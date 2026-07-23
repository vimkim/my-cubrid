set minimum-version := "1.55.0"
set no-cd
set shell := ["sh", "-cu"]

# Debug csql connected to testdb.
[working-directory(justfile_directory())]
csql-cs:
    cgdb --args csql -udba testdb

# Debug standalone csql connected to testdb.
[working-directory(justfile_directory())]
csql-sa:
    cgdb --args csql -udba testdb -S

# Attach to a selected cub_server process.
[working-directory(justfile_directory())]
server-interactive: print-current-server
    cgdb -p "$(ps aux | rg vimkim | rg cub_server | fzf | awk '{print $2}')" "$CUBRID_BUILD_DIR/bin/cub_server"

# Attach to the current worktree's testdb server.
[working-directory(justfile_directory())]
server: print-current-server
    #!/bin/sh
    set -eu

    pid=
    for process in /proc/[0-9]*; do
        [ "$(basename "$(readlink -f "$process/exe")")" = cub_server ] || continue
        [ "$(readlink -f "$process/cwd")" = "$PWD" ] || continue
        tr '\0' '\n' <"$process/cmdline" | grep -Fxq testdb || continue
        pid="${process##*/}"
        break
    done

    if [ -z "$pid" ]; then
        printf '%s\n' "No testdb cub_server is running from $PWD" >&2
        exit 1
    fi

    exec cgdb -p "$pid" "$CUBRID_BUILD_DIR/bin/cub_server"

# Debug client-server unloaddb.
[working-directory(justfile_directory())]
unloaddb-cs:
    cgdb --args cubrid unloaddb testdb -C -t 0 -v

# Debug standalone unloaddb.
[working-directory(justfile_directory())]
unloaddb-sa:
    cgdb --args cubrid unloaddb testdb -S -t 0 -v

# Debug client-server loaddb.
[working-directory(justfile_directory())]
loaddb-cs:
    cgdb --args cubrid loaddb -udba -C -v testdb -d ./testdb_objects

# Open a csql core with cgdb.
[working-directory(justfile_directory())]
core-csql CORE:
    cgdb csql core {{ CORE }}

# Attach to a selected cubrid utility process.
[working-directory(justfile_directory())]
attach-unloaddb: print-current-server
    cgdb -p "$(ps aux | rg vimkim | rg cubrid | fzf | awk '{print $2}')" "$CUBRID_BUILD_DIR/bin/cubrid"

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

[private]
[working-directory(justfile_directory())]
print-current-server:
    #!/bin/sh
    set -eu

    for process in /proc/[0-9]*; do
        [ "$(basename "$(readlink -f "$process/exe")")" = cub_server ] || continue
        cwd="$(readlink -f "$process/cwd")"
        case "$cwd" in
            *vimkim*)
                ps -p "${process##*/}" -o pid=,ppid=,stat=,args=
                printf '  cwd=%s\n' "$cwd"
                ;;
        esac
    done
