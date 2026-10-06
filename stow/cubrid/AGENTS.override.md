# Personal CUBRID instructions

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
