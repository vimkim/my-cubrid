# CUBRID PR status

Vocabulary for viewing CUBRID pull-request CI from a terminal.

## Language

**PR head**: The latest commit published to the pull request. It can differ from the local working directory's commit.

**Check identity**: A provider and its check context or workflow/job name. CircleCI `test_shell` and GitHub Actions `test_shell` are different checks.

**Reported-for commit**: The commit to which GitHub attaches a check or status. This determines the dashboard's freshness label; it is not independent proof of everything tested by the linked workflow.

**Current result**: A result reported for the PR head.

**Previous result**: The latest discovered result for a check on an earlier PR commit. Even a pending previous result is stale for the current head.

**Expected check**: A configured check that should retain a row even when it has no current result. Expectation does not prove a run was requested.

**Not observed**: No result was found for a check on the queried commit. It does not imply queued, running, skipped, or passed.

**Workflow revision**: The source revision running CI orchestration. An Actions issue-comment workflow may use develop while reporting test results for a separate PR head.
