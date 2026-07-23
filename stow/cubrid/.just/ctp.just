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
