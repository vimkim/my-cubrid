# Personal CUBRID tooling vocabulary

Host preparation and selection follow [host work environments](docs/host-workenv.md)
and [ADR-0002](docs/adr/0002-workenv-authority.md). Legacy terms in dated evidence
refer to the retired runtime engine.

## Language

**Managed CUBRID workflow**:
The supported build, installation and native-operation paths for a source worktree.

**Work environment**:
The host databases and runtime settings associated with one source worktree and
one selected installation/preset.

**Build-only worktree**:
A worktree prepared for compilation/installation whose host database environment
has not been explicitly initialized.

**Persistent managed test harness**:
A harness that retains use of an installation after the test finishes, until
explicit owned cleanup completes.

**Creation provenance**:
Evidence that a particular physical database was newly created by the selected
work environment, rather than reused or adopted from existing storage.

**pwddb**:
A compatibility name for the conventional `testdb` default. It does not restrict
other registered database names.

**demodb template**:
The sample dataset explicitly selected for loading into a newly created database.

**Review worktree**:
A disposable local checkout dedicated to inspecting one pull request. Multiple
review worktrees may coexist for the same ticket when their PRs differ.

**Review-request picker**:
An interactive choice among pull requests directly requesting the configured
reviewer and belonging to the normal tracked pull-request population.

**PR testcase branch**:
The published `tc/pr-N` branch associated with CUBRID pull request N in each
of the public and private testcase repositories.

**PR testcase baseline**:
The current published testcase branch corresponding to an engine PR's target,
or the explicitly identified develop fallback when that counterpart is absent.
Its latest tip is the shared testcase history the PR testcase branch should
include.
_Avoid_: Original branch creation point, testcase revision tested by CI

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
