#!/bin/bash

# Check for --dry-run or -d argument
DRY_RUN=false
if [[ "$1" == "--dry-run" || "$1" == "-d" ]]; then
    DRY_RUN=true
    shift # Remove the argument from the list
fi

# Get changed files
FILES=$(git status --porcelain | awk '{print $2}' | sort -u)

if [[ "$DRY_RUN" == true ]]; then
    for f in $FILES; do
        echo "for file $f"
        "$MY_CUBRID/codestyle-dryrun.sh" "${f}"
    done
else
    for f in $FILES; do
        echo "for file $f"
        # .github/workflows/codestyle.sh "${f}"
        cubrid-format-codestyle.sh "${f}"
    done
fi
