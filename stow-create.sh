#!/usr/bin/env bash
set -euo pipefail

MY_CUBRID="${MY_CUBRID:-$HOME/my-cubrid}"
CUBRID_JUSTFILES_DIR="${CUBRID_JUSTFILES_DIR:-$HOME/gh/my-cubrid-justfiles}"

ticket_from()
{
    local text="${1,,}"

    if [[ "$text" =~ cbrd[-_]?([0-9]+) ]]; then
        printf 'cbrd-%s\n' "${BASH_REMATCH[1]}"
        return 0
    fi

    return 1
}

slug_from()
{
    local text="${1,,}"

    text="${text// /-}"
    text="$(printf '%s' "$text" | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//')"
    printf '%s\n' "${text:-worktree}"
}

if [ "${CUBRID_SKIP_SHARED_STOW:-0}" != "1" ]; then
    stow --dir="$MY_CUBRID/stow" --target="." cubrid
    stow --dir="$MY_CUBRID/stow" --target="." gdb
fi

worktree_dir="$(pwd -P)"
worktree_name="$(basename "$worktree_dir")"
branch_name="$(git branch --show-current 2>/dev/null || true)"

if ticket="$(ticket_from "$worktree_name")"; then
    local_dir="$CUBRID_JUSTFILES_DIR/$ticket"
elif ticket="$(ticket_from "$branch_name")"; then
    local_dir="$CUBRID_JUSTFILES_DIR/$ticket"
else
    local_dir="$CUBRID_JUSTFILES_DIR/_unticketed/$(slug_from "$worktree_name")"
fi

mkdir -p "$local_dir/scripts" "$local_dir/sql"

if [ ! -e "$local_dir/justfile" ]; then
    cat >"$local_dir/justfile" <<EOF
# Local recipes for $worktree_name.
# Put helper scripts in ./scripts and SQL snippets in ./sql.

default:
    @just --list
EOF
fi

if [ -L local.just ] || [ ! -e local.just ]; then
    ln -sfn "$local_dir" local.just
else
    resolved_existing="$(realpath local.just 2>/dev/null || true)"
    resolved_target="$(realpath "$local_dir")"
    if [ "$resolved_existing" != "$resolved_target" ]; then
        echo "stow-create: local.just exists and is not the managed link: $resolved_existing" >&2
        echo "stow-create: expected target: $resolved_target" >&2
        exit 1
    fi
fi

echo "local.just -> $local_dir"
