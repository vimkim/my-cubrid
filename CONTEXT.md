# Personal CUBRID tooling vocabulary

See [ADR-0001](docs/adr/0001-enforce-runtime-guard-in-managed-workflow.md) for the
explicit-initialization scope revision. Manifest-specific terms below describe
the retained legacy guard; [host work environments](docs/host-workenv.md) describes
the new selection and execution boundary.

## Language

**Managed CUBRID workflow**:
The supported paths for building, installing, and operating a CUBRID worktree.
Host database use follows explicit environment initialization; build/install and
container preparation have independent readiness boundaries. Ordinary native
commands in a selected prepared host environment are supported.
_Avoid_: Fully enforced runtime, impossible-to-bypass runtime

**Managed runtime action**:
A coordinated host action that uses the selected database environment, storage,
or live CUBRID processes. Its environment selection is checked before execution.
Container use of an installation is coordinated independently of host database
readiness. Work on offline artifacts such as core files and traces is outside
this runtime boundary.

**Persistent managed test harness**:
A test harness that continues using the selected installation after its test
finishes, such as an inspection container. Its coordinator invocation remains
foregrounded and holds the runtime lock until the harness is stopped.

**Build-only worktree**:
A worktree with the environment needed to build and install CUBRID, but without
a prepared host database connection environment. Installing binaries alone does
not initialize that host environment. A container may use the installation with
its own independently prepared database environment.

**Review worktree**:
A disposable local checkout dedicated to inspecting one pull request. Multiple review worktrees may coexist for the same ticket when they belong to different pull requests.

**Review-request picker**:
An interactive choice among pull requests that directly request review from the configured reviewer and belong to the normal tracked pull-request population.

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

**PR testcase branch**:
The published `tc/pr-N` branch associated with CUBRID pull request N in each
of the public and private testcase repositories.

**Feature-current PR testcase branch**:
For a CUBRID pull request targeting `feature/<name>`, a PR testcase branch
whose history includes the latest published `feature/<name>` tip in the same
testcase repository. Additional testcase commits are allowed, whether the
baseline was incorporated by merge or rebase. The OOS case uses
`feature/oos-merge`.
_Avoid_: Identical to the feature branch, proven to originate from the feature branch

**Feature merge PR testcase branch**:
The PR testcase branch of the open `develop <- feature/<name>` pull request.
It must always have the same tip as `feature/<name>` in each testcase
repository; testcase edits land on `feature/<name>` first.
_Avoid_: Contains the feature branch (that is the weaker feature-current rule)
