cd ~/issue

<<<<<<< HEAD
pushd ~/issue

loadjava demodb SpCubrid.class

echo "java_stored_procedure=yes" >> $HOME/CUBRID/conf/cubrid.conf

csql -u dba demodb -S -i "$ISSUE_DIR/prepare.sql"

popd
