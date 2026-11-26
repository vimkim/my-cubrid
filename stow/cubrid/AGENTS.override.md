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

This standing push and CI authorization applies **only** to `vimkim`'s own
implementation PRs (where `vimkim` is the PR author or explicitly asked to
implement and push). It never applies to PR review checkouts — check
`git config --get "branch.$(git branch --show-current).cubrid-role"` for
`review` or verify the PR author via `gh-pr-info` before pushing.

The CUBRID TC Branch Sync GHA bot creates a testcase (TC) branch and PR in
each of the two testcase repositories. TC Merge Gate blocks merging the
CUBRID PR into `baseRefName` until both TC PRs are merged or closed.

- If TC changes are required, update, check, commit, and push them to the
  corresponding TC PR head branches before triggering CUBRID CI. The human
  reviews and merges those TC PRs into their base branches.
- If no TC changes are required, report this to the human. Keep those TC PRs
  open for isolation until the final merge handoff (`/cubrid-pr-merge`), which
  closes them atomically with the engine merge. Never recommend closing them
  earlier, even after CI passes.
- Agent publication in TC repositories is limited to commits and pushes
  on the TC PR head branches. Never merge or close TC PRs or delete their
  branches.

Before recommending a merge, asking for merge permission, or merging a
CUBRID engine or testcase PR, apply the
[PR approval gate](/home/vimkim/gh/my-cubrid-skills/cubrid-common/SKILL.md#pr-approval-gate).
Show the current per-reviewer result before asking for permission and again
immediately before each merge.

Trigger CUBRID CI once after the source and any required TC pushes. Wait for
that run to finish, report its result and run URL, including any TC Merge
Gate blocker, then stop and wait for the human's direction. Do not make
follow-up fixes, push again, or rerun CI until directed.

## Shared `.envrc` re-approval

Each worktree's `.envrc` is a symlink to `my-cubrid/stow/cubrid/.envrc`. An
edit to that file revokes direnv approval in every worktree. After you
commit such an edit to `my-cubrid`, you may run `direnv allow <worktree>`
without asking, but only for worktrees whose `.envrc` resolves
(`readlink -f`) to that stow file. Never allow a worktree whose `.envrc` is
a regular file or points elsewhere; report those. Report the number of
worktrees you re-allowed and the `my-cubrid` commit they now trust.

## Instruction sources

Codex loads this file instead of the worktree's root `AGENTS.md`. Load the
following sources in this order:

1. Read the root `AGENTS.md` of this worktree. It holds the repository's
   maintained guidance, rewritten against live code in CBRD-27539.
2. Before any CUBRID work, read `/home/vimkim/my-cubrid/CUBRID.md` for personal
   CUBRID policies and pointers to task-specific guidance.
3. Read `AGENTS.user.md`, if present in this worktree, for task-specific
   instructions.

Resolve `AGENTS.md` and `AGENTS.user.md` relative to this symlink's location in
the worktree, not its target in `my-cubrid/stow/cubrid`. The root `AGENTS.md`
and the CUBRID policy file are required; report either if missing or
unreadable. Skip an absent `AGENTS.user.md`, but report an unreadable one.

Apply the personal CUBRID policies over conflicting repository guidance,
then apply worktree-specific instructions. Continue to load applicable
instructions in subdirectories when working there.
