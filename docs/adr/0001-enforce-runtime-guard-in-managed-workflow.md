---
status: accepted
---

# Enforce the runtime guard at the managed-workflow seam

Managed CUBRID worktree operations fail closed through the shared environment and runtime coordinator: an unready worktree remains build-only, full installation establishes guarded runtime state, and coordinated runtime commands revalidate it. This central seam was chosen over scattered per-recipe checks and OS-level isolation because it keeps the personal workflow simple and consistent while accepting that deliberate direct binary invocation remains unmanaged.

## Consequences

- A new runtime defaults its database name to the sanitized worktree directory name, truncated to CUBRID's 17-character limit. The stable runtime identity and private registry/storage provide isolation, so the database name needs no identity suffix.
- Runtime ownership is proven from actual CUBRID executable identity plus correlated listeners, Unix endpoints, System V resources, or private database-storage descriptors. Merely inheriting `CUBRID` environment variables does not make a build daemon a live CUBRID process.
- Multiple Unix endpoints may share one pathname only when every endpoint matches the same filesystem identity and process generation.
- Complete observation may classify an owner-controlled stale runtime socket as idle. First initialization remains strict about preexisting socket paths; retained-runtime validation, reinitialization, and deinitialization tolerate stale pathnames without deleting them.
