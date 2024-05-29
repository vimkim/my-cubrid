# Define project directory and CUBRID path
PROJECT_DIR="$HOME/github/vimkim/cubrid"
CUBRID_PATH="$HOME/CUBRID"
CUBRID="$CUBRID_PATH"

# Function to log messages
log() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') - $1"
}


log "Starting build process..."

rm -rf "$CUBRID_PATH"

pushd "$PROJECT_DIR"

# Build the project with the specified options
if ! "$PROJECT_DIR/build.sh" -m debug -p "$CUBRID_PATH" -g ninja -t 64 build; then
    log "Build failed!"
    exit 1
fi

log "Build completed successfully."

popd
