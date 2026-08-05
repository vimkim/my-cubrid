just-install-testtools:
    ln -s ./cubrid-testtools-justfile ~/gh/ctp/cubrid-testtools/justfile

# Create NEW_BRANCH from BASE_BRANCH in both CUBRID testcase repositories.
tc-branch-create base_branch new_branch:
    "{{justfile_directory()}}/bin/cubrid-tc-branch-create.sh" "{{base_branch}}" "{{new_branch}}"
