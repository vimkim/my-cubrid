#!/bin/bash
set -euo pipefail

# Run the select command and capture output
csql -u dba testdb -S -t -c 'select * from vt' > actual_output.txt

# Read expected output from file
expected_output=$(cat expected_output.txt)
actual_output=$(cat actual_output.txt)

# Compare output (ignoring whitespace)
if diff -u <(echo "$expected_output") <(echo "$actual_output") &> output.diff; then
    echo "✅ Test passed: Output matches expected result"
    exit 0
else
    echo "❌ Test failed: Output doesn't match expected result"
    echo "Expected:"
    echo "$expected_output"
    echo "Got:"
    echo "$actual_output"
    echo "Diff:"
    cat output.diff
    exit 1
fi
