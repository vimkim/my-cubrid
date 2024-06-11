cd ~/issue

pushd ~/issue

loadjava demodb SpCubrid.class

echo "java_stored_procedure=yes" >> $HOME/CUBRID/conf/cubrid.conf

csql -u dba demodb -S -i ~/issue/prepare.sql
popd
