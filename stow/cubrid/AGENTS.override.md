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

## PR implementation and CI

After implementing a CUBRID PR and passing focused checks, commit the task
changes and push to the PR's `headRefName` in its head repository. This is
standing authorization to commit, push, and trigger CUBRID CI; no separate
approval is required for these actions.

The CUBRID TC Branch Sync GHA bot creates a testcase (TC) branch and PR in
each of the two testcase repositories. TC Merge Gate blocks merging the
CUBRID PR into `baseRefName` until both TC PRs are merged or closed.

- If TC changes are required, update, check, commit, and push them to the
  corresponding TC PR head branches before triggering CUBRID CI. The human
  reviews and merges those TC PRs into their base branches.
- If no TC changes are required, report this to the human, who closes the
  TC PRs. Their branches are then deleted automatically.
- Agent publication in TC repositories is limited to commits and pushes
  on the TC PR head branches. Never merge or close TC PRs or delete their
  branches.

Trigger CUBRID CI once after the source and any required TC pushes. Wait for
that run to finish, report its result and run URL, including any TC Merge
Gate blocker, then stop and wait for the human's direction. Do not make
follow-up fixes, push again, or rerun CI until directed.

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
