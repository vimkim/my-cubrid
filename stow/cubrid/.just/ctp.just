set minimum-version := "1.55.0"
set no-cd
set shell := ["sh", "-cu"]

# Run one CTP shell test directory against the active local build.
[working-directory(justfile_directory())]
shell-debug TEST_DIR:
    cubrid-shell-debug.sh {{ TEST_DIR }}

# Run all CTP shell tests below a subtree.
[working-directory(justfile_directory())]
shell-debug-many SUBTREE:
    cubrid-shell-debug.sh {{ SUBTREE }}

# Use CTP's built-in interactive shell-test selector.
[working-directory(justfile_directory())]
shell-debug-interactive:
    ~/CTP/bin/ctp.sh shell --interactive -c ~/CTP/conf/shell_ci.conf

# Example:
#   just ctp podman-test-new cbrd26067-force-outline c26fo16 /absolute/path/to/test_force_outline_16b.sh
# Start an isolated CUBRID server container, run one shell TC, and keep it alive.
[working-directory(justfile_directory())]
podman-test-new container db_name test_script:
    "$MY_CUBRID/bin/cubrid-podman-test.sh" run \
        --name "{{container}}" \
        --cubrid-root "$CUBRID" \
        --server \
        --db-name "{{db_name}}" \
        "{{test_script}}"
