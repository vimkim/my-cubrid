set minimum-version := "1.55.0"
set no-cd
set shell := ["sh", "-cu"]

# List all registered database names, including stopped databases.
list-all:
    @~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- ~/my-cubrid/bin/my-cubrid-pwddb list

# Select a registered database with fzf and start its server.
start-interactive:
    #!/usr/bin/env bash
    set -euo pipefail
    databases=$(~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- ~/my-cubrid/bin/my-cubrid-pwddb list)
    if [[ -z $databases ]]; then
      echo 'No registered databases.'
      exit 0
    fi
    if database=$(printf '%s\n' "$databases" | fzf --height=40% --layout=reverse --border --no-multi --prompt='Start database> '); then
      [[ -n $database ]] || exit 0
    else
      status=$?
      [[ $status == 1 || $status == 130 ]] && exit 0
      exit "$status"
    fi
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 0 --database "$database" -- cubrid server start "$database"

# Select a running database server with fzf and stop it.
stop-interactive:
    #!/usr/bin/env bash
    set -euo pipefail
    server_status=$(~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 0 -- cubrid server status)
    databases=$(awk '($1 == "Server" || $1 == "HA-Server") && !seen[$2]++ {print $2}' <<<"$server_status")
    if [[ -z $databases ]]; then
      echo 'No running database servers.'
      exit 0
    fi
    if database=$(printf '%s\n' "$databases" | fzf --height=40% --layout=reverse --border --no-multi --prompt='Stop database> '); then
      [[ -n $database ]] || exit 0
    else
      status=$?
      [[ $status == 1 || $status == 130 ]] && exit 0
      exit "$status"
    fi
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 0 --database "$database" -- cubrid server stop "$database"

# Create the ready manifest's database, initially empty.
pwddb-create:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- ~/my-cubrid/bin/my-cubrid-pwddb create

# Replace only the resolved database with an empty database.
pwddb-recreate:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- ~/my-cubrid/bin/my-cubrid-pwddb recreate

# Delete only the resolved database.
pwddb-delete:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh database-delete 300

# Populate the ready manifest's database with demodb sample data.
pwddb-create-demodb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- ~/my-cubrid/bin/my-cubrid-pwddb create --load demodb

# Replace the manifest's database and load demodb sample data.
pwddb-recreate-demodb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- ~/my-cubrid/bin/my-cubrid-pwddb recreate --load demodb

# Delete the manifest's database; template selection never changes its name.
pwddb-delete-demodb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh database-delete 300

# Start testdb while holding the runtime lock.
[working-directory(justfile_directory())]
start-testdb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- cubrid server start testdb

# Restart testdb while holding the runtime lock.
[working-directory(justfile_directory())]
restart-testdb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- cubrid server restart testdb

# Stop testdb while holding the runtime lock.
[working-directory(justfile_directory())]
stop-testdb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- cubrid server stop testdb

# Best-effort stop of testdb.
[working-directory(justfile_directory())]
stop-testdb-try:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- cubrid server stop testdb || true

# Start demodb while holding the runtime lock.
[working-directory(justfile_directory())]
start-demodb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database demodb -- cubrid server start demodb

# Restart demodb while holding the runtime lock.
[working-directory(justfile_directory())]
restart-demodb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database demodb -- cubrid server restart demodb

# Stop demodb while holding the runtime lock.
[working-directory(justfile_directory())]
stop-demodb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database demodb -- cubrid server stop demodb

# Show selected effective testdb parameters.
[working-directory(justfile_directory())]
paramdump-testdb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- cub-auto paramdump testdb | rg 'buffer|string'

# Open csql against testdb.
[working-directory(justfile_directory())]
csql: paramdump-testdb
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- csql.sh

# Open csql against testdb in standalone mode.
[working-directory(justfile_directory())]
csql-sa:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- csql.sh

# Unload testdb in standalone mode.
[working-directory(justfile_directory())]
unloaddb-sa:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- cubrid unloaddb testdb -S -t 0 -v

# Unload testdb in client-server mode.
[working-directory(justfile_directory())]
unloaddb-cs:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- cubrid unloaddb testdb -C -t 0 -v

# Create testdb.
[working-directory(justfile_directory())]
create-testdb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- ~/my-cubrid/bin/my-cubrid-pwddb create

# Delete the manifest-selected testdb.
[working-directory(justfile_directory())]
delete-testdb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh database-delete 300 --database testdb

# Recreate the manifest-selected testdb.
[working-directory(justfile_directory())]
recreate-testdb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- ~/my-cubrid/bin/my-cubrid-pwddb recreate

# Stop, recreate, and start testdb.
[working-directory(justfile_directory())]
stop-recreate-start-testdb: stop-testdb recreate-testdb start-testdb

# Create and load demodb.
[working-directory(justfile_directory())]
create-demodb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database demodb -- ~/my-cubrid/bin/my-cubrid-pwddb create --load demodb

# Delete demodb.
[working-directory(justfile_directory())]
delete-demodb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh database-delete 300 --database demodb

# Recreate demodb.
[working-directory(justfile_directory())]
recreate-demodb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database demodb -- ~/my-cubrid/bin/my-cubrid-pwddb recreate --load demodb

# Interactively update a CUBRID system parameter in the active runtime.
[working-directory(justfile_directory())]
ini database='testdb' section='common':
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database "{{ database }}" -- cubrid-ini-fzf --database "{{ database }}" --section "{{ section }}"

# Show enable_string_compression from the installed config and effective testdb parameters.
[working-directory(justfile_directory())]
get-string-compression:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --get "$CUBRID/conf/cubrid.conf" common enable_string_compression || true
    just db paramdump-string-compression

# Enable string compression.
[working-directory(justfile_directory())]
enable-string-compression: get-string-compression
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --set "$CUBRID/conf/cubrid.conf" common enable_string_compression yes
    printf '%s\n' "string compression enabled:"
    just db get-string-compression

# Disable string compression.
[working-directory(justfile_directory())]
disable-string-compression: get-string-compression
    printf '%s\n' "string compression disabled:"
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --set "$CUBRID/conf/cubrid.conf" common enable_string_compression no
    just db get-string-compression

# Show effective string-compression configuration for testdb.
[working-directory(justfile_directory())]
paramdump-string-compression:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database testdb -- cub-auto paramdump testdb | rg enable_string_compression

# Show enable_pgbuf_inspector from the installed config (default: no).
[working-directory(justfile_directory())]
get-pgbuf-inspector:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --get "$CUBRID/conf/cubrid.conf" common enable_pgbuf_inspector

# Enable the page-buffer inspector at the next database server startup.
[working-directory(justfile_directory())]
enable-pgbuf-inspector:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --set "$CUBRID/conf/cubrid.conf" common enable_pgbuf_inspector yes
    just db get-pgbuf-inspector
    printf '%s\n' "Restart the database server to apply enable_pgbuf_inspector."

# Disable the page-buffer inspector at the next database server startup.
[working-directory(justfile_directory())]
disable-pgbuf-inspector:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --set "$CUBRID/conf/cubrid.conf" common enable_pgbuf_inspector no
    just db get-pgbuf-inspector
    printf '%s\n' "Restart the database server to apply enable_pgbuf_inspector."

# Show the effective hidden inspector parameter for a running database.
[working-directory(justfile_directory())]
paramdump-pgbuf-inspector database='testdb':
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 --database "{{ database }}" -- cubrid paramdump -C --dump-flag=0x8 "{{ database }}" | rg enable_pgbuf_inspector

# Show use_system_malloc.
[working-directory(justfile_directory())]
get-use-system-malloc:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --get "$CUBRID/conf/cubrid.conf" common use_system_malloc || true

# Enable system malloc.
[working-directory(justfile_directory())]
enable-use-system-malloc: get-use-system-malloc
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --set "$CUBRID/conf/cubrid.conf" common use_system_malloc yes
    just db get-use-system-malloc

# Disable system malloc.
[working-directory(justfile_directory())]
disable-use-system-malloc: get-use-system-malloc
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --set "$CUBRID/conf/cubrid.conf" common use_system_malloc no
    just db get-use-system-malloc

# Show unfill_factor.
[working-directory(justfile_directory())]
get-unfill-factor:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --get "$CUBRID/conf/cubrid.conf" common unfill_factor || true

# Set unfill_factor to zero.
[working-directory(justfile_directory())]
set-unfill-factor:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --set "$CUBRID/conf/cubrid.conf" common unfill_factor 0.0

# Show cubrid_port_id.
[working-directory(justfile_directory())]
get-port:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --get "$CUBRID/conf/cubrid.conf" common cubrid_port_id

# Set cubrid_port_id to the personal test port.
[working-directory(justfile_directory())]
set-port: get-port
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --set "$CUBRID/conf/cubrid.conf" common cubrid_port_id 12345

# Show data_buffer_size.
[working-directory(justfile_directory())]
get-data-buffer-size:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --get "$CUBRID/conf/cubrid.conf" common data_buffer_size

# Set data_buffer_size to 20G.
[working-directory(justfile_directory())]
set-data-buffer-20g: get-data-buffer-size
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --set "$CUBRID/conf/cubrid.conf" common data_buffer_size 20G
    just db get-data-buffer-size

# Set data_buffer_size to 50G.
[working-directory(justfile_directory())]
set-data-buffer-50g: get-data-buffer-size
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --set "$CUBRID/conf/cubrid.conf" common data_buffer_size 50G
    just db get-data-buffer-size

# Set data_buffer_size to 512M.
[working-directory(justfile_directory())]
set-data-buffer-512m: get-data-buffer-size
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- crudini --set "$CUBRID/conf/cubrid.conf" common data_buffer_size 512m
    just db get-data-buffer-size

# Edit the installed cubrid.conf.
[working-directory(justfile_directory())]
edit-config:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- nvim "$CUBRID/conf/cubrid.conf"
