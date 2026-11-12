set no-cd
set shell := ["sh", "-cu"]

# Running the module name alone lists its recipes instead of running the first one.
[private]
[working-directory(justfile_directory())]
default:
    @just --list github

# Request reviews for the PR associated with the current worktree.
add-reviewers:
    cubrid-dev2-add-reviewers.py
