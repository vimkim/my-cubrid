set args -u dba testdb -S -c "insert into vt values ('[1, 2, 3]')"
set pagination off
set breakpoint pending on
start
del br
b csql
continue
b pt_compile
continue
b tp_value_cast_internal
b setobj_create
b pt_db_value_initialize
continue
set pagination on
