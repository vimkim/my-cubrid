CUBRID_PATH="$HOME/CUBRID"
# Function to log messages
log() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') - $1"
}

log "Cleaning up previous demo database files..."
rm -rf "$CUBRID_PATH/databases/demodb"

rm -f "$CUBRID_PATH/databases/databases.txt"

log "Removing demodb done!"

