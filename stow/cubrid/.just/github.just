set no-cd
set shell := ["sh", "-cu"]

# Request reviews for the PR associated with the current worktree.
add-reviewers:
    cubrid-dev2-add-reviewers.py
