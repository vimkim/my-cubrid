#!/usr/bin/env bash
# jira-to-md.sh — Convert JIRA wiki markup to markdown
# Uses pandoc jira→markdown conversion.
set -euo pipefail

usage() {
  echo "Usage: $(basename "$0") <file.jira> [output.md]"
  echo "  If output is omitted, writes to <file>.md"
  exit 1
}

[[ $# -lt 1 ]] && usage

input="$1"
[[ ! -f "$input" ]] && { echo "Error: '$input' not found" >&2; exit 1; }

# Default output: same name with .md extension
output="${2:-${input%.jira}.md}"

# pandoc jira → markdown
pandoc --from jira --to markdown "$input" -o "$output"

echo "Converted: $input → $output"
