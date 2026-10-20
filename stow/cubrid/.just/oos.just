set minimum-version := "1.55.0"
set no-cd
set shell := ["sh", "-cu"]

# Apply the shared OOS server configuration.
[working-directory(justfile_directory())]
prepare-server:
    just db set-port

# Build, install, and apply the shared OOS server configuration.
[working-directory(justfile_directory())]
build-and-install-prepare:
    just build-and-install
    just oos prepare-server

# Configure, build, install, and apply the shared OOS server configuration.
[working-directory(justfile_directory())]
configure-build-and-install-prepare:
    just configure
    just oos build-and-install-prepare

# Run one OOS isolation test or the default OOS isolation suite.
[working-directory(justfile_directory())]
test-isolation TARGET='':
    "${MY_CUBRID:-$HOME/my-cubrid}/bin/cubrid-build-coordinator.sh" runtime 300 -- cubrid-oos-isolation-test.sh {{ TARGET }}
