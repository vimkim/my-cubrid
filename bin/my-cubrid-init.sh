#!/usr/bin/env bash
set -euo pipefail

readonly my_cubrid_dir="${MY_CUBRID:-$HOME/my-cubrid}"

exec just \
  --justfile "$my_cubrid_dir/cubrid-justfiles/justfile" \
  --working-directory . \
  prepare-build
