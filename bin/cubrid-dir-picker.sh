#!/usr/bin/env bash

readonly repos=(
  "$HOME/my-cubrid"
  "$HOME/gh/my-cubrid-docs"
  "$HOME/gh/my-cubrid-jira"
  "$HOME/gh/my-cubrid-skills"
  "$HOME/gh/cubrid-oos-context"
  "$HOME/gh/cb"
)

readonly preview_cmd='
dir={}

if [[ ! -d "$dir" ]]; then
  printf "missing directory: %s\n" "$dir"
  exit 0
fi

if ! git -C "$dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  printf "not a git repository: %s\n" "$dir"
  exit 0
fi

git -C "$dir" -c color.status=always status --short --branch
'

if ! command -v fzf >/dev/null 2>&1; then
  printf '%s\n' 'cubrid-dir-picker: fzf is required' >&2
  exit 127
fi

if ! selected=$(printf '%s\n' "${repos[@]}" | SHELL="$(command -v bash)" fzf \
  --height=40% \
  --reverse \
  --prompt='CUBRID dir> ' \
  --preview="$preview_cmd" \
  --preview-window='right:60%:wrap'); then
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
