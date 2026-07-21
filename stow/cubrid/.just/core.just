set minimum-version := "1.55.0"
set no-cd
set shell := ["nu", "-c"]

# Prepare this worktree's personal tooling.
[working-directory(justfile_directory())]
prepare: stow-create
    git submodule update --init cubrid-cci
    direnv allow
    lefthook install

# Configure the selected CMake preset.
[working-directory(justfile_directory())]
configure:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh configure

# Select a preset interactively. Autonomous workflows should use the bootstrap script instead.
[working-directory(justfile_directory())]
select-preset:
    cmake-preset-mode-select.sh

# Compile without installing.
[working-directory(justfile_directory())]
compile:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh compile

# Install an already-compiled tree when its runtime is idle.
[working-directory(justfile_directory())]
install:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh install 0

# Compile and install without build-log capture.
[working-directory(justfile_directory())]
build-without-log:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh build 0

# Compile, install, and capture the complete build log.
[working-directory(justfile_directory())]
build:
    #!/usr/bin/env bash
    set -euo pipefail
    build_dir="$(direnv exec . bash -c 'echo "${CUBRID_BUILD_DIR:?set PRESET_MODE / allow direnv first}"')"
    mkdir -p "$build_dir"
    log_file="$build_dir/build.log"
    echo "Logging build output to: $log_file"
    direnv exec . "$HOME/my-cubrid/bin/cubrid-build-coordinator.sh" build 0 2>&1 | tee "$log_file"

# Wait up to `timeout` seconds for an idle runtime, then build.
[working-directory(justfile_directory())]
build-wait timeout='300':
    ~/my-cubrid/bin/cubrid-build-coordinator.sh build {{ timeout }}

# Wait up to `timeout` seconds for an idle runtime, then install.
[working-directory(justfile_directory())]
install-wait timeout='300':
    ~/my-cubrid/bin/cubrid-build-coordinator.sh install {{ timeout }}

# Stop active CUBRID processes and build after explicit confirmation.
[working-directory(justfile_directory())]
stop-and-build: confirm-no
    ~/my-cubrid/bin/cubrid-build-coordinator.sh stop-and-build

# Run configured ctest tests while holding the runtime lock.
[working-directory(justfile_directory())]
ctest:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh runtime 300 -- ctest --test-dir $"($env.CUBRID_BUILD_DIR)" --output-on-failure --verbose

# Run the currently configured test suite. This is intentionally ctest-only.
[working-directory(justfile_directory())]
test: ctest

# Build, then run the currently configured test suite.
[working-directory(justfile_directory())]
build-test: build test

# Install the third-party target.
[working-directory(justfile_directory())]
install-3rdparty:
    ~/my-cubrid/bin/cubrid-build-coordinator.sh install-target 3rdparty/install 0

# Install third-party dependencies and csql utilities.
[working-directory(justfile_directory())]
install-csql-util: install-3rdparty
    ~/my-cubrid/bin/cubrid-build-coordinator.sh install-target util/install 0

# Choose and build one CMake target interactively.
[working-directory(justfile_directory())]
target:
    cmake --build --preset $env.PRESET_MODE --target help | awk -F': ' '{print $1}' | fzf | xargs -I {} cmake --build --preset $env.PRESET_MODE --target {}

# Choose and build one CMake target with the external fuzzy helper.
[working-directory(justfile_directory())]
target-fuzzy:
    cmake-build-target-fuzzy.sh $CUBRID_BUILD_DIR

# Remove CMake's configure cache after explicit confirmation.
[working-directory(justfile_directory())]
clear-cache: confirm-no
    /bin/rm -rf $"($env.CUBRID_BUILD_DIR)/CMakeCache.txt" $"($env.CUBRID_BUILD_DIR)/CMakeFiles"

# Remove the selected build directory after explicit confirmation.
[working-directory(justfile_directory())]
delete-build: confirm-no
    /bin/rm -rf $CUBRID_BUILD_DIR

# Remove the selected install directory after explicit confirmation.
[working-directory(justfile_directory())]
delete-install: confirm-no
    /bin/rm -rf $CUBRID

# Restow shared CUBRID and GDB files into the current worktree.
[working-directory(justfile_directory())]
stow-shared:
    stow --dir=$"($env.MY_CUBRID)/stow" --target=. cubrid
    stow --dir=$"($env.MY_CUBRID)/stow" --target=. gdb

# Restow shared files and create the worktree-local just module.
[working-directory(justfile_directory())]
stow-create: stow-shared
    CUBRID_SKIP_SHARED_STOW=1 ~/my-cubrid/stow-create.sh

# Remove shared stowed CUBRID and GDB files from the current worktree.
[working-directory(justfile_directory())]
stow-delete:
    stow -D --dir=$"($env.MY_CUBRID)/stow" --target=. cubrid
    stow -D --dir=$"($env.MY_CUBRID)/stow" --target=. gdb

# Stow the shared cb directory layout.
[working-directory(justfile_directory())]
stow-cb:
    stow -d ~/my-cubrid -t ~/gh/cb stow-cb

# Preserve the former `just core csql CORE` command shape.
[private]
[working-directory(justfile_directory())]
csql CORE:
    just debug core-csql {{ CORE }}

[private]
[working-directory(justfile_directory())]
confirm-no:
    @gum confirm --default=false
