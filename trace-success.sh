csql -u dba demodb -S -i $ISSUE_DIR/prepare.sql
uftrace record csql -u dba demodb -S -i $ISSUE_DIR/run-success.sql
