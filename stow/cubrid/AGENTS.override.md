# Personal CUBRID instruction loader

Before doing any work, load the following files from the CUBRID worktree
directory containing this symlink, in order:

1. Read `AGENTS.md`, if present, for shared project instructions.
2. Read `AGENTS.user.md`, if present, for personal worktree instructions.

Resolve these paths relative to the symlink's location in the worktree, not
its target in `my-cubrid/stow/cubrid`. Skip missing files; report unreadable
files instead of silently treating them as absent.

Apply both sets of instructions. Personal instructions take precedence over
conflicting project guidance. Continue to load applicable instructions in
subdirectories when working there.
