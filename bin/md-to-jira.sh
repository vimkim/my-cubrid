#!/usr/bin/env bash
# md-to-jira.sh — Convert markdown to JIRA wiki markup
# Applies korean-spacing (for inline marker rendering) then pandoc md→jira.
set -euo pipefail

usage() {
  echo "Usage: $(basename "$0") <file.md> [output.jira]"
  echo "  If output is omitted, writes to <file>.jira"
  exit 1
}

[[ $# -lt 1 ]] && usage

input="$1"
[[ ! -f "$input" ]] && { echo "Error: '$input' not found" >&2; exit 1; }

# Default output: same name with .jira extension
output="${2:-${input%.md}.jira}"

# Step 1: sanitize markdown (ensure blank lines before headings, lists, code blocks)
# mdformat breaks tables, so we do targeted fixes only.
sanitized=$(python3 -c "
import re, sys
lines = sys.stdin.read().split('\n')
out = []
for i, line in enumerate(lines):
    # Insert blank line before heading/list/fenced-code if previous line is non-empty text
    if i > 0 and out and out[-1].strip() != '':
        needs_blank = False
        if re.match(r'^#{1,6}\s', line):        # heading
            needs_blank = True
        elif re.match(r'^[-*+]\s', line):        # unordered list start
            needs_blank = not re.match(r'^[-*+]\s', out[-1])  # only if prev isn't also a list
        elif re.match(r'^\d+\.\s', line):        # ordered list start
            needs_blank = not re.match(r'^\d+\.\s', out[-1])
        elif re.match(r'^[~\`]{3}', line):       # fenced code block
            needs_blank = True
        if needs_blank:
            out.append('')
    out.append(line)
print('\n'.join(out), end='')
" < "$input")

# Step 2: korean-spacing (fix inline markers next to Korean chars)
spaced=$(echo "$sanitized" | korean-spacing -i /dev/stdin -o /dev/stdout 2>/dev/null || echo "$sanitized")

# Step 3: pandoc markdown → jira
jira=$(echo "$spaced" | pandoc --from markdown --to jira)

# Step 4: fix {{monospace}} inside *bold* (JIRA can't render nested)
# Reuse the same logic from jira_md_upload.py via python one-liner
fixed=$(python3 -c "
import re, sys

def fix_line(line):
    if re.match(r'\s*\*+\s', line):
        return line
    def split_bold(m):
        inner = m.group(1)
        if '{{' not in inner:
            return m.group(0)
        segments = re.split(r'(\{\{.*?\}\})', inner)
        parts = []
        for seg in segments:
            if seg.startswith('{{') and seg.endswith('}}'):
                parts.append(seg)
            else:
                stripped = seg.strip()
                if stripped:
                    parts.append(f'*{stripped}*')
        return ' '.join(parts)
    return re.sub(r'\*(?!\s)([^*\n]+?)(?<!\s)\*', split_bold, line)

text = sys.stdin.read()
print('\n'.join(fix_line(l) for l in text.split('\n')), end='')
" <<< "$jira")

echo "$fixed" > "$output"
echo "Converted: $input → $output"
