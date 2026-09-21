---
status: accepted
---

# Enforce the runtime guard at the managed-workflow seam

Managed CUBRID worktree operations fail closed through the shared environment and runtime coordinator: an unready worktree remains build-only, full installation establishes guarded runtime state, and coordinated runtime commands revalidate it. This central seam was chosen over scattered per-recipe checks and OS-level isolation because it keeps the personal workflow simple and consistent while accepting that deliberate direct binary invocation remains unmanaged.
