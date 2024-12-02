default:
    @just --choose

alias b := build
alias c := configure
alias bd := build-debug
alias bp := build-profile


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

run-csql:
	csql -u dba demodb

run-csql-standalone:
	csql -u dba demodb -S

cgdb-csql:
	cgdb --args csql -u dba demodb

cgdb-csql-standalone:
	cgdb --args csql -u dba demodb -S

