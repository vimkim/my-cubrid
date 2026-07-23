# Temporary flat-name compatibility layer. New calls should use module namespaces.

[private]
alias build-without-log := core::build-without-log

[private]
alias build-with-log := core::build

[private]
alias build-only := core::compile

[private]
alias build-for-ctp := core::build

[private]
alias cmake-preset-mode-select := core::select-preset

[private]
alias cmake-build-install-3rdparty := core::install-3rdparty

[private]
alias cmake-build-install-csql-util := core::install-csql-util

[private]
alias cmake-build-install-all := core::install

[private]
alias cmake-build-target := core::target-fuzzy

[private]
alias build-target := core::target

[private]
alias clear-cache := core::clear-cache

[private]
alias cmakecache-delete := core::clear-cache

[private]
alias build-delete := core::delete-build

[private]
alias install-dir-remove := core::delete-install

[private]
alias stow-shared := core::stow-shared

[private]
alias stow-create := core::stow-create

[private]
alias stow-delete := core::stow-delete

[private]
alias stow-cb := core::stow-cb

[private]
configure-build-for-ctp: core::configure core::build

[private]
build-restart-testdb: core::build db::restart-testdb

[private]
alias server-start-demodb := db::start-demodb

[private]
alias server-restart-demodb := db::restart-demodb

[private]
alias server-stop-demodb := db::stop-demodb

[private]
alias cubrid-server-start-testdb := db::start-testdb

[private]
alias cubrid-server-restart-testdb := db::restart-testdb

[private]
alias cubrid-server-stop-testdb := db::stop-testdb

[private]
alias cubrid-server-stop-testdb-try := db::stop-testdb-try

[private]
alias get-server-config := db::paramdump-testdb

[private]
alias paramdump-testdb := db::paramdump-testdb

[private]
alias csql := db::csql

[private]
alias csql-testdb-cs := db::csql

[private]
alias csql-testdb-sa := db::csql-sa

[private]
alias cubrid-unloaddb-sa := db::unloaddb-sa

[private]
alias cubrid-unloaddb-cs := db::unloaddb-cs

[private]
alias cubrid-createdb-testdb := db::create-testdb

[private]
alias cubrid-deletedb-testdb := db::delete-testdb

[private]
alias cubrid-deletedb-all := db::delete-all

[private]
alias cubrid-recreate-testdb := db::recreate-testdb

[private]
alias recreate-testdb := db::recreate-testdb

[private]
alias cubrid-stop-recreate-start-testdb := db::stop-recreate-start-testdb

[private]
alias cubrid-createdb-demodb := db::create-demodb

[private]
alias cubrid-deletedb-demodb := db::delete-demodb

[private]
alias cubrid-recreate-demodb := db::recreate-demodb

[private]
alias database-remove := db::remove-databases

[private]
alias cubrid-conf-enable-string-compression := db::enable-string-compression

[private]
alias cubrid-conf-disable-string-compression := db::disable-string-compression

[private]
alias cubrid-paramdump-testdb-string-compression := db::paramdump-string-compression

[private]
alias cubrid-conf-get-string-compression := db::get-string-compression

[private]
alias cubrid-conf-enable-use-system-malloc := db::enable-use-system-malloc

[private]
alias cubrid-conf-disable-use-system-malloc := db::disable-use-system-malloc

[private]
alias cubrid-conf-get-use-system-malloc := db::get-use-system-malloc

[private]
alias cubrid-conf-get-unfill-factor := db::get-unfill-factor

[private]
alias cubrid-conf-set-unfill-factor := db::set-unfill-factor

[private]
alias cubrid-conf-get-port := db::get-port

[private]
alias cubrid-conf-set-port := db::set-port

[private]
alias cubrid-conf-get-data-buffer-size := db::get-data-buffer-size

[private]
alias cubrid-conf-data-buffer-set-20gb := db::set-data-buffer-20g

[private]
alias cubrid-conf-data-buffer-set-50gb := db::set-data-buffer-50g

[private]
alias cubrid-conf-data-buffer-set-512m := db::set-data-buffer-512m

[private]
alias cubrid-conf-edit := db::edit-config

[private]
alias edit-databases-txt := db::edit-databases

[private]
shell-debug TEST_DIR: (ctp::shell-debug TEST_DIR)

[private]
shell-debug-many SUBTREE: (ctp::shell-debug-many SUBTREE)

[private]
alias shell-debug-interactive := ctp::shell-debug-interactive

[private]
alias debug-with-cgdb-csql-testdb-cs := debug::csql-cs

[private]
alias debug-with-cgdb-csql-testdb-sa := debug::csql-sa

[private]
alias debug-with-cgdb-cub-server-testdb-interactive := debug::server-interactive

[private]
alias debug-with-cgdb-cub-server-testdb := debug::server

[private]
alias debug-with-cubrid-unloaddb-cs := debug::unloaddb-cs

[private]
alias debug-with-cubrid-unloaddb-sa := debug::unloaddb-sa

[private]
alias debug-with-cubrid-loaddb-cs := debug::loaddb-cs

[private]
alias debug-with-cgdb-attach-cubrid-unloaddb := debug::attach-unloaddb

[private]
alias coredumpctl-core-csql := debug::coredump-csql

[private]
alias core-delete := debug::delete-cores

[private]
alias rr-replay := debug::rr-replay

[private]
alias remove-rapidjson := maint::remove-rapidjson

[private]
alias list-dbtype-function := maint::list-dbtype-function

[private]
alias format-pr-diff := maint::format-pr-diff

[private]
alias format-git-changed-dryrun := maint::format-changed-dryrun

[private]
alias format-git-changed := maint::format-changed

[private]
alias format-one-file := maint::format-one

[private]
alias clang-tidy := maint::clang-tidy

[private]
alias uftrace-dump-chrome := profile::uftrace-dump-chrome

[private]
alias uftrace-dump-flamegraph := profile::uftrace-dump-flamegraph

[private]
alias uftrace-preview := profile::uftrace-preview

[private]
alias uftrace-serve-trace := profile::uftrace-serve

[private]
alias perf-record-cub_server := profile::perf-record-server

[private]
alias perf-report := profile::perf-report

[private]
alias perf-flamegraph := profile::perf-flamegraph

[private]
alias check-simd-native := profile::check-simd-native

[private]
alias build-prepare-oos := oos::build-prepare

[private]
alias configure-build-prepare-oos := oos::configure-build-prepare

[private]
alias oos-prepare-server := oos::prepare-server

[private]
test-isolation TARGET='': (oos::test-isolation TARGET)

# The former OOS SQL harness disappeared with cubrid-oos-test. Fail honestly instead of reporting a false pass.
[private]
test-oos-sql:
    @printf '%s\n' "test-oos-sql was retired: the cubrid-oos-test SQL harness no longer exists" >&2
    @exit 2

[private]
alias n1 := oos::build-prepare

[private]
alias n2 := db::recreate-testdb

[private]
alias n4 := db::unloaddb-sa

[private]
alias nb := oos::build-prepare

[private]
alias np := oos::prepare-server

[private]
alias nt := core::build-test

[private]
alias b := oos::build-prepare

[private]
alias c := configure

[private]
alias t := test

# These live only in develop's local module. Recursive dispatch keeps other worktrees parseable.
[private]
depthlog-pretty-print-log:
    just local depthlog-pretty-print-log

[private]
cmake-refresh-fetchcontent-depthlog:
    just local refresh-depthlog

[private]
update-cubrid-conf:
    just local update-cubrid-conf

[private]
build-update:
    just build
    just local update-cubrid-conf

[private]
update-restart-testdb:
    just local update-cubrid-conf
    just db restart-testdb

[private]
n5:
    just local depthlog-pretty-print-log

[private]
nd:
    just local depthlog-pretty-print-log

[private]
nl:
    just local depthlog-pretty-print-log

[private]
pgbuf-hit-ratio-bugfix-statdump:
    just local pgbuf-hit-ratio-statdump
