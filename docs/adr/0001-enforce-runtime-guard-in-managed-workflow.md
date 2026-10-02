---
status: accepted
---

# Enforce the runtime guard at the managed-workflow seam

The original decision centralized legacy runtime validation in the shared environment and coordinator instead of scattering checks across recipes or adding OS-level isolation. The accepted scope is now narrowed: the legacy guard remains available for existing legacy environments, while the explicit host-workenv contract below supersedes automatic initialization after installation and universal runtime-readiness requirements.

## Scope revision: explicit host initialization (2026-10-02)

The [host work environment integration](../host-workenv.md) separates preparation
from loading and use so that entering a directory or finishing a build does not
create databases or migrate existing state.

- Build and installation leave initialization explicit. This supersedes the
  original rule that full installation establishes guarded runtime state,
  including the build coordinator and shared build recipe.
- A prepared host work environment loads its completed selection with cheap
  metadata checks. Full diagnosis is an explicit operation. Existing legacy
  runtime actions retain their legacy validation path; that path is not the
  readiness contract for new workenv environments.
- Ordinary `cubrid` and `csql` use in the selected host environment is supported.
  Neither a coordinator prefix nor `cub-workenv run` is mandatory for every test.
- Containers prepare their own database environment independently of host
  initialization. `installation-use` retains the installation lock for a
  bind-mounted installation without requiring a ready host runtime. Persistent
  container ownership and cleanup protections remain in force.
- Coordinated host actions retain the installation lock and check the selected
  environment before execution. `stop-and-build` checks it before stopping
  services, then installs without reinitializing. These checks do not establish
  a sandbox or continuous protection against external interference.

The legacy manifest, database-lifecycle, and ownership rules below are retained
for the legacy guard path. They do not authorize automatic migration or apply
legacy single-database assumptions to new workenv storage.

## Retained legacy guard consequences

- A new runtime defaults its database name to the sanitized worktree directory name, truncated to CUBRID's 17-character limit. The stable runtime identity and private registry/storage provide isolation, so the database name needs no identity suffix.
- Runtime ownership is proven from actual CUBRID executable identity plus correlated listeners, Unix endpoints, System V resources, or private database-storage descriptors. Merely inheriting `CUBRID` environment variables does not make a build daemon a live CUBRID process.
- Multiple Unix endpoints may share one pathname only when every endpoint matches the same filesystem identity and process generation.
- Complete observation may classify an owner-controlled stale runtime socket as idle. First initialization remains strict about preexisting socket paths; retained-runtime validation, reinitialization, and deinitialization tolerate stale pathnames without deleting them.
- Runtime-lock ownership is proven only by holding the coordinator's actual
  lock. Caller-controlled environment variables never establish ownership, and
  recursive runtime-coordinator entry is unsupported.
- Managed runtime actions include operations using the installed runtime,
  selected database registry or storage, live CUBRID processes, and test
  harnesses against the installation. Offline core-file and trace analysis is
  outside this boundary.
- Runtime actions that select a live process restrict candidates to the exact
  validated installation, worktree directory, and selected database or utility
  role. A name-only process match is not sufficient.
- A persistent managed test container that bind-mounts the selected
  installation keeps its coordinator invocation and runtime lock alive until
  explicit container cleanup. Signal-driven termination removes the container
  before releasing the lock. Cleanup requires a per-invocation ownership label;
  an unknown or foreign same-name container is never removed, and deletion
  targets the proven immutable container ID rather than its reusable name.
- Combined operations revalidate at the transition from build work to runtime
  work. In particular, `stop-and-build` validates after acquiring the runtime
  lock and before stopping services or installing.
- If the selected CUBRID executable is unavailable, selected-database deletion
  may use a binary-independent path only after manifest ownership and a
  completely observed idle runtime are proven. Failure from an available
  CUBRID deletion utility never activates this fallback. Automatic fallback is
  limited to fresh guard-created storage; adopted database storage requires the
  real utility.
- Binary-independent deletion is exposed only through a dedicated coordinator
  database-deletion action. No generic runtime command may opt into its relaxed,
  operation-specific installation validation.
- Binary-independent deletion is development-oriented and uses simple
  registry-first crash semantics: removal of the selected registry row is
  atomic, storage cleanup follows, and an interruption may leave explicitly
  reported orphaned files rather than a discoverable partially deleted
  database. No deletion journal is maintained.
- An authorized lifecycle attempt may create its canonical owner-only database
  lock before final validation. Rejection permits this inert coordination
  metadata but must not modify database registry rows, database contents, or
  storage roots.
