set pagination off
set breakpoint pending on

# for vector insert
# set args -u dba testdb -S -c "insert into vt values ('[1, 2, 3]')"
# start
# del br
# b csql
# continue
# b pt_compile
# continue
# b tp_value_cast_internal
# b setobj_create
# b pt_db_value_initialize
# b tp_str_to_vector
# continue

set args -u dba testdb -S -c "select L2_DISTANCE('[1, 2, 3]', '[2, 3, 4]') from dual;"
start
del br
b csql
continue
b pt_compile
so br
continue

set pagination on
