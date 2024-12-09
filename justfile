default:
    @just --choose

alias b := build
alias c := configure
alias bd := build-debug
alias bp := build-profile
alias cc := csql-cs
alias cs := csql-sa
alias br := build-and-run
alias r := run

# Echo
echo-hello:
    @echo "Hello, World!"

# CMake

configure:
    cmake --preset $PRESET_MODE

build:
    cmake --build --preset $PRESET_MODE --target install

build-debug:
    cmake --build --preset mydebug --target install

build-profile:
    cmake --build --preset myprofile --target install

# CSQL

csql-cs:
    csql -u dba demodb

csql-sa:
    csql -u dba demodb -S

cgdb-csql-cs:
    cgdb --args csql -u dba demodb

cgdb-csql-sa:
    cgdb --args csql -u dba demodb -S

core csql CORE:
    cgdb csql core {{ CORE }}

# gdbserver

gdbserver:
    gdbserver :9999 csql -u dba demodb -S

gdbserver-i:
    gdbserver :9999 csql -u dba demodb -S -i run.sql

# utils

list-dbtype-function:
    fd -H -I dbtype_function build_preset_"$PRESET_MODE"

# createdb

db-create-testdb:
    mkdir -p testdb
    cubrid createdb --db-volume-size=100M --log-volume-size=100M testdb en_US.utf8 -F testdb

db-delete-testdb:
    cubrid deletedb testdb

# csql
create-vector:
    csql -u dba testdb -S -c 'create table vt (vec vector);'

create-vector-with-args:
    csql -u dba testdb -S -c 'create table vta (vec vector(3));'
    csql -u dba testdb -S -c 'create table vta2 (vec vector(3, FLOAT));'

insert-vector:
    csql -u dba testdb -S -c "insert into vt values( '[1, 2, 3]' );"
    @# csql -u dba testdb -S -c "insert into vt values( {1, 2, 3} );"

select-vector:
    csql -u dba testdb -S -c "select * from vt;"

run: db-delete-testdb db-create-testdb create-vector create-vector-with-args insert-vector select-vector
    echo "run!"

build-and-run: build run
