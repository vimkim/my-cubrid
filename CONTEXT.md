# Personal CUBRID tooling vocabulary

## Language

**Managed CUBRID workflow**:
The supported path for building or operating a CUBRID worktree, in which runtime readiness is mandatory. Deliberate direct invocation outside this workflow is unmanaged.
_Avoid_: Fully enforced runtime, impossible-to-bypass runtime

**Managed runtime action**:
An action in the Managed CUBRID workflow that uses an installed CUBRID runtime,
its selected database registry or storage, a live CUBRID process, or a test
harness against that installation. Managed runtime actions pass through the
runtime coordinator. Work on offline artifacts such as core files and traces is
not a Managed runtime action.

**Persistent managed test harness**:
A test harness that continues using the selected installation after its test
finishes, such as an inspection container. Its coordinator invocation remains
foregrounded and holds the runtime lock until the harness is stopped.

**Build-only worktree**:
A worktree that has enough environment to build and install CUBRID but exposes no runnable CUBRID environment because its worktree runtime is not ready.

**Preset takeover**:
The transition of a worktree runtime to another preset installation while retaining its stable identity and database selection. It is permitted only when the previous preset has no live or unknown runtime resources.

**Fresh runtime database**:
A newly created private database selected for a worktree runtime without adopting preexisting database storage into it.
_Avoid_: Migrated database, adopted database

**Binary-independent database deletion**:
Removal of the manifest-selected database when its selected CUBRID executable
is unavailable. It applies only to fresh guard-created storage, is permitted
only when ownership and an idle runtime are proven, and never substitutes for
a CUBRID utility that was available but failed.

**Stale runtime socket**:
An owner-controlled Unix socket pathname inside a private runtime directory with no live kernel endpoint. Complete observation treats it as idle retained filesystem state, not as live ownership.

**pwddb**:
The database selected by the current worktree runtime's ready manifest. Its name and private storage remain independent of the invocation directory and branch.

**Database adoption**:
The explicit association of an existing private database with a worktree runtime after exclusive registry and storage ownership has been proven. Adoption preserves its name and locations.

**demodb template**:
The sample dataset explicitly selected to populate the manifest-selected database. Selecting the template does not change the database name.
