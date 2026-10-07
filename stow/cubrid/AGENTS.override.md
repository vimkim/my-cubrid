# Personal CUBRID instructions

## Worktree and contributor context

You are working in a Git worktree of `github.com/CUBRID/cubrid`. The user is
a primary CUBRID Engine source code engineer and contributor, focused on
storage: log, page buffer, slotted page, heap, and related components. The
key concerns are concurrency, ACID guarantees, performance, replication,
and recovery.

Every time you read this file, run `gh-pr-info` (available in `PATH`) from
the current working directory to determine whether its branch is associated
with a PR. Collect the PR identity, head repository, `headRefName`, and
`baseRefName` from the output. Record when no PR is found; report other
lookup failures separately.

## PR workflow

The user usually implements features and bug fixes in individual worktrees.
After implementation is complete, the usual workflow is to push to the PR's
`headRefName` in its head repository (usually `github.com/vimkim/cubrid`) and
trigger CI.

The user has the right to merge the PR into its `baseRefName` after CI is
green (or after confirming that this PR introduces no significant testcase
failures) and one or two team members have approved the code review.

## Instruction sources

This file replaces the root `AGENTS.md`, whose instructions are stale. Use
the following maintained sources instead of loading that root file:

1. Before any CUBRID work, read `/home/vimkim/my-cubrid/CUBRID.md` for personal
   CUBRID policies and pointers to task-specific guidance.
2. Read `AGENTS.user.md`, if present in this worktree, for task-specific
   instructions.

Resolve `AGENTS.user.md` relative to this symlink's location in the worktree,
not its target in `my-cubrid/stow/cubrid`. The CUBRID policy file is required;
report it if missing or unreadable. Skip an absent `AGENTS.user.md`, but report
an unreadable one.

Apply the personal CUBRID policies over conflicting repository guidance,
then apply worktree-specific instructions. Continue to load applicable
instructions in subdirectories when working there; this override replaces
only the root `AGENTS.md`.
