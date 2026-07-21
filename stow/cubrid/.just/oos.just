set minimum-version := "1.55.0"
set no-cd
set shell := ["nu", "-c"]

# Apply the shared OOS server configuration.
[working-directory(justfile_directory())]
prepare-server:
    just db set-port

# Build and apply the shared OOS server configuration.
[working-directory(justfile_directory())]
build-prepare:
    just build
    just oos prepare-server

# Configure, build, and apply the shared OOS server configuration.
[working-directory(justfile_directory())]
configure-build-prepare:
    just configure
    just oos build-prepare

# Run one OOS isolation test or the default OOS isolation suite.
[working-directory(justfile_directory())]
test-isolation TARGET='':
    cubrid-oos-isolation-test.sh {{ TARGET }}
