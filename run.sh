#!/bin/bash

cd $ISSUE_DIR

# Function to print the current timestamp
print_timestamp() {
    date +"%Y-%m-%d %H:%M:%S"
}

# Log the start message with timestamp
echo "Start: $(print_timestamp) - Running csql command"

# Run the csql command
csql -u dba demodb -S -i "$ISSUE_DIR/run.sql"

# Check if the csql command was successful
if [[ $? -eq 0 ]]; then
    echo "Finish: $(print_timestamp) - csql command completed successfully"
else
    echo "Finish: $(print_timestamp) - csql command failed"
fi
