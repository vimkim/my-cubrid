set minimum-version := "1.55.0"
set no-cd
set shell := ["nu", "-c"]

# Remove RapidJSON's CMake external-project state.
[working-directory(justfile_directory())]
remove-rapidjson:
    /bin/rm -rf $"($env.CUBRID_BUILD_DIR)/3rdparty/Source/rapidjson"
    /bin/rm -rf $"($env.CUBRID_BUILD_DIR)/3rdparty/Build/rapidjson"
    /bin/rm -rf $"($env.CUBRID_BUILD_DIR)/3rdparty/Install/rapidjson"
    /bin/rm -rf $"($env.CUBRID_BUILD_DIR)/3rdparty/Stamp/rapidjson"
    /bin/rm -rf $"($env.CUBRID_BUILD_DIR)/3rdparty/tmp/rapidjson"

# Find dbtype_function in the selected build tree.
[working-directory(justfile_directory())]
list-dbtype-function:
    fd -H -I dbtype_function build_preset_"$env.PRESET_MODE"

# Format the current PR diff.
[working-directory(justfile_directory())]
format-pr-diff:
    cubrid-format-pr-diff.sh

# Preview formatting for Git-changed files.
[working-directory(justfile_directory())]
format-changed-dryrun:
    cubrid-format-gitchanged.sh -d

# Format Git-changed files after explicit confirmation.
[working-directory(justfile_directory())]
format-changed:
    @gum confirm
    cubrid-format-gitchanged.sh

# Choose and format one source file.
[working-directory(justfile_directory())]
format-one:
    cubrid-format-codestyle.sh $"(fd | fzf)"

# Run clang-tidy whenever a source file changes.
[working-directory(justfile_directory())]
clang-tidy:
    fd '(\.h$)|(\.cpp$)|(\.c$)' src | entr -cr clang-tidy /_
