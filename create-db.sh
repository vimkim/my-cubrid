# Ensure CUBRID_PATH is set to the value of CUBRID environment variable
CUBRID_PATH="${CUBRID:?CUBRID environment variable not set}"

# Create the demo database directory if it doesn't already exist
mkdir -p "$CUBRID_PATH/databases/demodb"

# Use pushd to navigate to the demo database directory
pushd "$CUBRID_PATH/databases/demodb" > /dev/null

# Check if the demo database creation script exists and is executable
DEMO_SCRIPT="$CUBRID_PATH/demo/make_cubrid_demo.sh"
if [[ -x "$DEMO_SCRIPT" ]]; then
    # Create the demo database
    "$DEMO_SCRIPT"
    echo "demodb creation done!"
else
    echo "Error: Demo database creation script not found or not executable: $DEMO_SCRIPT"
    return 1
fi

return 1

# Return to the previous directory
popd > /dev/null

# Print success message
echo "Demo database successfully created and setup completed."
