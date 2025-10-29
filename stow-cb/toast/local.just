gpt-select:
    csql -u dba testdb -i ./gpt-select.sql

gpt-insert:
    csql -u dba testdb -i ./gpt-insert.sql

rr-record-select:
    rr record csql -u dba testdb -S -i gpt-select.sql

rr-replay:
    rr replay -d cgdb

uftrace-record-insert-large:
    csql -u dba testdb -i prepare.sql -S
    uftrace record -N 'linux:schedule' -N db_restart_ex -F db_execute_statement -- csql -u dba testdb -S -i ./insert-large.sql

uftrace-dump-chrome-insert-large:
    uftrace dump --chrome o> ./uftrace/uftrace-chrome-insert-large.json

uftrace-serve-trace-insert-large:
    trace_processor --httpd ./uftrace/uftrace-chrome-insert-large.json

uftrace-record-select-large:
    csql -u dba testdb -i prepare.sql -S
    csql -u dba testdb -i insert-large.sql -S
    uftrace record -N 'linux:schedule' -N db_restart_ex -F db_execute_statement -- csql -u dba testdb -S -i ./select-large.sql

uftrace-dump-chrome-select-large:
    uftrace dump --chrome o> ./uftrace/uftrace-chrome-select-large.json

uftrace-serve-trace-select-large:
    trace_processor --httpd ./uftrace/uftrace-chrome-select-large.json

uftrace-record-update-large:
    csql -u dba testdb -i prepare.sql -S
    csql -u dba testdb -i insert-large.sql -S
    uftrace record -N 'linux:schedule' -N db_restart_ex -F db_execute_statement -- csql -u dba testdb -S -i ./update-large.sql

uftrace-dump-chrome-update-large:
    uftrace dump --chrome o> ./uftrace/uftrace-chrome-update-large.json

uftrace-serve-trace-update-large:
    trace_processor --httpd ./uftrace/uftrace-chrome-update-large.json

