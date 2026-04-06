#!/bin/bash

# Format all files changed in the current PR.
# Auto-detects base and head branches via `gh pr view`.
# Usage: cubrid-format-pr-diff.sh [--dry-run|-d]

DRY_RUN=""
if [[ "$1" == "--dry-run" || "$1" == "-d" ]]; then
    DRY_RUN="--dry-run"
fi

PR_JSON=$(gh pr view --json baseRefName,headRefName,baseRefOid,headRefOid,number 2>&1)
if [[ $? -ne 0 ]]; then
    echo "Error: No PR found for the current branch."
    echo "Make sure you're on a branch with an open PR."
    echo "$PR_JSON"
    exit 1
fi

BASE_REF=$(echo "$PR_JSON" | jq -r '.baseRefName')
HEAD_REF=$(echo "$PR_JSON" | jq -r '.headRefName')
BASE_OID=$(echo "$PR_JSON" | jq -r '.baseRefOid')
HEAD_OID=$(echo "$PR_JSON" | jq -r '.headRefOid')
NUMBER=$(echo "$PR_JSON" | jq -r '.number')

echo "PR #${NUMBER}: ${HEAD_REF} -> ${BASE_REF}"
echo "  base: ${BASE_OID:0:12}"
echo "  head: ${HEAD_OID:0:12}"
echo "Formatting changed files..."
echo ""

cubrid-format-diff.sh $DRY_RUN "${BASE_OID}" "${HEAD_OID}"
