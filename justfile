default:
  @just --choose

alias b := build
alias c := configure
alias bd := build-debug
alias bp := build-profile
alias cc := csql-cs
alias cs := csql-sa

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
  cgdb csql core {{CORE}}


# gdbserver

gdbserver:
  gdbserver :9999 csql -u dba demodb -S

gdbserver-i:
  gdbserver :9999 csql -u dba demodb -S -i run.sql


