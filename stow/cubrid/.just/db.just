set minimum-version := "1.55.0"
set no-cd
set shell := ["sh", "-cu"]

# Start testdb while holding the runtime lock.
[working-directory(justfile_directory())]
start-testdb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- cubrid server start testdb

# Restart testdb while holding the runtime lock.
[working-directory(justfile_directory())]
restart-testdb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- cubrid server restart testdb

# Stop testdb while holding the runtime lock.
[working-directory(justfile_directory())]
stop-testdb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- cubrid server stop testdb

# Best-effort stop of testdb.
[working-directory(justfile_directory())]
stop-testdb-try:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- cubrid server stop testdb || true

# Start demodb while holding the runtime lock.
[working-directory(justfile_directory())]
start-demodb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- cubrid server start demodb

# Restart demodb while holding the runtime lock.
[working-directory(justfile_directory())]
restart-demodb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- cubrid server restart demodb

# Stop demodb while holding the runtime lock.
[working-directory(justfile_directory())]
stop-demodb:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- cubrid server stop demodb

# Show selected effective testdb parameters.
[working-directory(justfile_directory())]
paramdump-testdb:
    cub-auto paramdump testdb | rg 'buffer|string'

# Open csql against testdb.
[working-directory(justfile_directory())]
csql: paramdump-testdb
    csql.sh

# Open csql against testdb in standalone mode.
[working-directory(justfile_directory())]
csql-sa:
    csql.sh

# Unload testdb in standalone mode.
[working-directory(justfile_directory())]
unloaddb-sa:
    cubrid unloaddb testdb -S -t 0 -v

# Unload testdb in client-server mode.
[working-directory(justfile_directory())]
unloaddb-cs:
    cubrid unloaddb testdb -C -t 0 -v

# Create testdb.
[working-directory(justfile_directory())]
create-testdb:
    mkdir -p "$CUBRID_DATABASES/testdb"
    cubrid createdb --db-volume-size=20M --log-volume-size=20M testdb en_US.utf8 -F "$CUBRID_DATABASES/testdb"

# Delete testdb through the CUBRID utility.
[working-directory(justfile_directory())]
delete-testdb:
    cubrid deletedb testdb

# Delete all local databases after explicit confirmation.
[working-directory(justfile_directory())]
delete-all:
    gum confirm "delete all db? This is dangerous"
    /bin/rm -rf "$CUBRID_DATABASES"
    /bin/rm -rf testdb*
    mkdir -p "$CUBRID_DATABASES/testdb"

# Recreate testdb from an empty local database directory.
[working-directory(justfile_directory())]
recreate-testdb: delete-all create-testdb

# Stop, recreate, and start testdb.
[working-directory(justfile_directory())]
stop-recreate-start-testdb: stop-testdb recreate-testdb start-testdb

# Create and load demodb.
[working-directory(justfile_directory())]
create-demodb:
    mkdir -p "$CUBRID_DATABASES/demodb"
    cubrid createdb --db-page-size=16K --db-volume-size=20M --log-volume-size=20M demodb en_US.utf8 -F "$CUBRID_DATABASES/demodb"
    cubrid loaddb -u dba -s "$CUBRID/demo/demodb_schema" -d "$CUBRID/demo/demodb_objects" demodb

# Delete demodb.
[working-directory(justfile_directory())]
delete-demodb:
    cubrid deletedb demodb

# Recreate demodb.
[working-directory(justfile_directory())]
recreate-demodb: delete-demodb create-demodb

# Remove all local databases after explicit confirmation.
[working-directory(justfile_directory())]
remove-databases: confirm-no
    /bin/rm -rf "$CUBRID_DATABASES"

# Show enable_string_compression from the installed config and effective testdb parameters.
[working-directory(justfile_directory())]
get-string-compression:
    crudini --get "$CUBRID/conf/cubrid.conf" common enable_string_compression || true
    just db paramdump-string-compression

# Enable string compression.
[working-directory(justfile_directory())]
enable-string-compression: get-string-compression
    crudini --set "$CUBRID/conf/cubrid.conf" common enable_string_compression yes
    printf '%s\n' "string compression enabled:"
    just db get-string-compression

# Disable string compression.
[working-directory(justfile_directory())]
disable-string-compression: get-string-compression
    printf '%s\n' "string compression disabled:"
    crudini --set "$CUBRID/conf/cubrid.conf" common enable_string_compression no
    just db get-string-compression

# Show effective string-compression configuration for testdb.
[working-directory(justfile_directory())]
paramdump-string-compression:
    cub-auto paramdump testdb | rg enable_string_compression

# Show use_system_malloc.
[working-directory(justfile_directory())]
get-use-system-malloc:
    crudini --get "$CUBRID/conf/cubrid.conf" common use_system_malloc || true

# Enable system malloc.
[working-directory(justfile_directory())]
enable-use-system-malloc: get-use-system-malloc
    crudini --set "$CUBRID/conf/cubrid.conf" common use_system_malloc yes
    just db get-use-system-malloc

# Disable system malloc.
[working-directory(justfile_directory())]
disable-use-system-malloc: get-use-system-malloc
    crudini --set "$CUBRID/conf/cubrid.conf" common use_system_malloc no
    just db get-use-system-malloc

# Show unfill_factor.
[working-directory(justfile_directory())]
get-unfill-factor:
    crudini --get "$CUBRID/conf/cubrid.conf" common unfill_factor || true

# Set unfill_factor to zero.
[working-directory(justfile_directory())]
set-unfill-factor:
    crudini --set "$CUBRID/conf/cubrid.conf" common unfill_factor 0.0

# Show cubrid_port_id.
[working-directory(justfile_directory())]
get-port:
    crudini --get "$CUBRID/conf/cubrid.conf" common cubrid_port_id

# Set cubrid_port_id to the personal test port.
[working-directory(justfile_directory())]
set-port: get-port
    crudini --set "$CUBRID/conf/cubrid.conf" common cubrid_port_id 12345

# Show data_buffer_size.
[working-directory(justfile_directory())]
get-data-buffer-size:
    crudini --get "$CUBRID/conf/cubrid.conf" common data_buffer_size

# Set data_buffer_size to 20G.
[working-directory(justfile_directory())]
set-data-buffer-20g: get-data-buffer-size
    crudini --set "$CUBRID/conf/cubrid.conf" common data_buffer_size 20G
    just db get-data-buffer-size

# Set data_buffer_size to 50G.
[working-directory(justfile_directory())]
set-data-buffer-50g: get-data-buffer-size
    crudini --set "$CUBRID/conf/cubrid.conf" common data_buffer_size 50G
    just db get-data-buffer-size

# Set data_buffer_size to 512M.
[working-directory(justfile_directory())]
set-data-buffer-512m: get-data-buffer-size
    crudini --set "$CUBRID/conf/cubrid.conf" common data_buffer_size 512m
    just db get-data-buffer-size

# Edit the installed cubrid.conf.
[working-directory(justfile_directory())]
edit-config:
    nvim "$CUBRID/conf/cubrid.conf"

# Edit databases.txt.
[working-directory(justfile_directory())]
edit-databases:
    nvim "$CUBRID_DATABASES/databases.txt"

[private]
[working-directory(justfile_directory())]
confirm-no:
    echo "dangerous"
    # @gum confirm --default=false
