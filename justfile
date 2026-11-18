# Show the personal tooling recipes.
default:
    @just --list

# Install the daily CUBRID updater, cubrid-static-check, and cubrid-dev2-members.
sync:
    #!/usr/bin/env bash
    set -euo pipefail
    install_dir="${DAILY_UPDATE_CUBRID_BIN_DIR:-$HOME/.local/bin}"
    install -d -- "$install_dir"
    install -m 755 -- daily-update-cubrid.py "$install_dir/daily-update-cubrid"
    "$install_dir/daily-update-cubrid" --help >/dev/null
    printf 'Installed %s/daily-update-cubrid\n' "$install_dir"
    install -m 755 -- static-analysis/static-check/cubrid-static-check "$install_dir/cubrid-static-check"
    "$install_dir/cubrid-static-check" --help >/dev/null
    printf 'Installed %s/cubrid-static-check\n' "$install_dir"
    install -m 755 -- bin/cubrid-dev2-members "$install_dir/cubrid-dev2-members"
    "$install_dir/cubrid-dev2-members" --help >/dev/null
    printf 'Installed %s/cubrid-dev2-members\n' "$install_dir"

# Refresh the installed updater, then run the CUBRID part of general daily upkeep.
daily-update: sync
    #!/usr/bin/env bash
    set -euo pipefail
    install_dir="${DAILY_UPDATE_CUBRID_BIN_DIR:-$HOME/.local/bin}"
    exec "$install_dir/daily-update-cubrid" --skip-dotfiles
