# Personal CUBRID tooling vocabulary

## Language

**pwddb**:
The database selected by the current worktree runtime's ready manifest. Its name and private storage remain independent of the invocation directory and branch.

**Database adoption**:
The explicit association of an existing private database with a worktree runtime after exclusive registry and storage ownership has been proven. Adoption preserves its name and locations.

**demodb template**:
The sample dataset explicitly selected to populate the manifest-selected database. Selecting the template does not change the database name.
