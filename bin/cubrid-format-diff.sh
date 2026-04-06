#!/bin/bash

# Format all files changed between two git refs (branches, tags, or commits).
# Usage: cubrid-format-diff.sh [--dry-run|-d] <refA> <refB>

DRY_RUN=false
if [[ "$1" == "--dry-run" || "$1" == "-d" ]]; then
    DRY_RUN=true
    shift
fi

if [[ $# -lt 2 ]]; then
    echo "Usage: cubrid-format-diff.sh [--dry-run|-d] <refA> <refB>"
    echo "  Formats all files changed between refA and refB."
    exit 1
fi

REF_A="$1"
REF_B="$2"

FILES=$(git diff --name-only "${REF_A}...${REF_B}" | sort -u)

for f in $FILES; do
    if [[ ! -f "$f" ]]; then
        echo "skipping (deleted): $f"
        continue
    fi
    echo "for file $f"
    if [[ "$DRY_RUN" == true ]]; then
        "$MY_CUBRID/codestyle-dryrun.sh" "${f}"
    else
        cubrid-format-codestyle.sh "${f}"
    fi
done
