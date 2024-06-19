pushd "$ISSUE_DIR"

# File path
conf_file="$HOME/CUBRID/conf/cubrid.conf"

# Check if the line exists
if ! grep -q "^java_stored_procedure=yes" "$conf_file"; then
  # If not, add the line
  echo "java_stored_procedure=yes" >> "$conf_file"
fi

echo "java_stored_procedure=yes" >> $HOME/CUBRID/conf/cubrid.conf

csql -u dba demodb -S -i "$ISSUE_DIR/prepare.sql"

popd
