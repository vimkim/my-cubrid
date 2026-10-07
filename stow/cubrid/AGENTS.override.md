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

For fixes to an existing PR, use its `headRefName` in its head repository
(usually `github.com/vimkim/cubrid`) as the development branch and local
integration destination. Base any separate task worktree on the current local
`headRefName`. After completing the fixes and relevant checks, rebase the task
branch onto the current local `headRefName` and fast-forward merge into it
through the local worktree workflow. Integrating fixes into `headRefName`
requires no additional PR, team code review, or squash merge.

After implementation is complete, the usual workflow is to push the updated
`headRefName` to its head repository and trigger CI. Pushing requires explicit
user authorization.

Integrating changes into the PR's `baseRefName` in `CUBRID/cubrid` requires
creating or using the matching PR and following the repository's reviewed
squash-merge process. The user has the right to squash merge the PR after CI
is green (or after confirming that this PR introduces no significant testcase
failures) and one or two team members have approved the code review. Update
`baseRefName` through that PR process.

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
