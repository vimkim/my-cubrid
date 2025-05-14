#!/usr/bin/env bash
set -euo pipefail

# Ensure MY_CUBRID is defined
: "${MY_CUBRID:?MY_CUBRID is not set}"

# Stow packages safely
stow --dir="$MY_CUBRID/stow" --target="." cubrid
stow --dir="$MY_CUBRID/stow" --target="." gdb

# Create directory and justfile
proj_name="$(basename "$(pwd)")"
proj_dir="$MY_CUBRID/just-cubrid/$proj_name"

mkdir -p "$proj_dir"
touch "$proj_dir/justfile"

# Create symlink
ln -sf "$proj_dir" .just
