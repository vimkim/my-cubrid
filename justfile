# Show the personal tooling recipes.
default:
    @just --list

# Install the daily CUBRID updater into the user command directory.
sync:
    #!/usr/bin/env bash
    set -euo pipefail
    install_dir="${DAILY_UPDATE_CUBRID_BIN_DIR:-$HOME/.local/bin}"
    install -d -- "$install_dir"
    install -m 755 -- daily-update-cubrid.py "$install_dir/daily-update-cubrid"
    "$install_dir/daily-update-cubrid" --help >/dev/null
    printf 'Installed %s/daily-update-cubrid\n' "$install_dir"
