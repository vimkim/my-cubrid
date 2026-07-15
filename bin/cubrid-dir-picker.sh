#!/usr/bin/env bash

readonly repos=(
  "$HOME/my-cubrid"
  "$HOME/gh/my-cubrid-docs"
  "$HOME/gh/my-cubrid-jira"
  "$HOME/gh/my-cubrid-skills"
  "$HOME/gh/cubrid-oos-context"
)

if ! command -v fzf >/dev/null 2>&1; then
  printf '%s\n' 'cubrid-dir-picker: fzf is required' >&2
  exit 127
fi

if ! selected=$(printf '%s\n' "${repos[@]}" | fzf \
  --height=40% \
  --reverse \
  --prompt='CUBRID dir> '); then
  printf '%s\n' 'cubrid-dir-picker: no directory selected' >&2
  exit 1
fi

if [[ -z "$selected" ]]; then
  printf '%s\n' 'cubrid-dir-picker: no directory selected' >&2
  exit 1
fi

if [[ ! -d "$selected" ]]; then
  printf 'cubrid-dir-picker: directory does not exist: %s\n' "$selected" >&2
  exit 1
fi

printf '%s\n' "$selected"
