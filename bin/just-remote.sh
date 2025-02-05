#!/usr/bin/env bash
set -euo pipefail

# Define your remote justfile and its directory
JUSTFILE="${MY_CUBRID:-/path/to/default/dir}/remote/justfile"
JUST_DIR="${MY_CUBRID:-/path/to/default/dir}/remote"

# Define the chooser command with a preview that uses the remote justfile.
CHOOSER=(fzf --reverse --multi --height 50% --preview "just -f '$JUSTFILE' -d '$JUST_DIR' --unstable --color always --show {}")

# List available recipes from the remote justfile.
recipes=$(just -f "$JUSTFILE" -d "$JUST_DIR" --summary | tr ' ' '\n')

# Run the chooser and capture the selected command(s).
CMD=$(printf '%s\n' "$recipes" | "${CHOOSER[@]}")

# If no selection was made, exit.
if [ -z "$CMD" ]; then
    exit 0
fi

# Run a dry-run with the selected recipes (for verification) and print the command.
dry_run_output=$(just -f "$JUSTFILE" --dry-run $CMD 2>&1 | sed '$!s/$/ \&\&/')
# Use the appropriate command to replace the current command line if needed.
# In zsh, you might use 'print -z'; in bash, you might 'echo' it for further processing.
printf '%s\n' "$dry_run_output"
