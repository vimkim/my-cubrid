# Personal CUBRID tooling vocabulary

## Language

**Managed CUBRID workflow**:
The supported path for building or operating a CUBRID worktree, in which runtime readiness is mandatory. Deliberate direct invocation outside this workflow is unmanaged.
_Avoid_: Fully enforced runtime, impossible-to-bypass runtime

**Build-only worktree**:
A worktree that has enough environment to build and install CUBRID but exposes no runnable CUBRID environment because its worktree runtime is not ready.

**Preset takeover**:
The transition of a worktree runtime to another preset installation while retaining its stable identity and database selection. It is permitted only when the previous preset has no live or unknown runtime resources.

**Fresh runtime database**:
A newly created private database selected for a worktree runtime without adopting preexisting database storage into it.
_Avoid_: Migrated database, adopted database

**pwddb**:
The database selected by the current worktree runtime's ready manifest. Its name and private storage remain independent of the invocation directory and branch.

**Database adoption**:
The explicit association of an existing private database with a worktree runtime after exclusive registry and storage ownership has been proven. Adoption preserves its name and locations.

**demodb template**:
The sample dataset explicitly selected to populate the manifest-selected database. Selecting the template does not change the database name.
