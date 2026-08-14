# Global CUBRID work-context recipes

`cubrid-justfiles` provides globally accessible launchers for working across
CUBRID repositories and worktrees. These recipes are selected from the global
shell integration and do not assume that the current worktree has already been
initialized with the stowed CUBRID development files.

Recipes coupled to an initialized CUBRID runtime or source worktree belong in
`stow/cubrid` instead. This includes recipes that operate on `$CUBRID`,
`$CUBRID_BUILD_DIR`, `$CUBRID_DATABASES`, or the current source-tree layout.

In short:

- `cubrid-justfiles`: globally accessible cross-work-context launchers
- `stow/cubrid`: worktree-local server development and maintenance recipes

Keep this distinction when adding or moving recipes. A recipe's subject being
CUBRID-related is not sufficient reason to place it here; its invocation scope
and environment coupling determine its owner.

## Testcase branch synchronization

Use `tc-sync` after refreshing a CUBRID pull-request branch from `develop`, or
before rerunning CI when its associated testcase branches need the same
baseline. The recipe derives `tc/pr-<number>` from the CUBRID PR URL, fetches
both testcase repositories, and merges `origin/develop` into both local
testcase branches. It does not push them.

```bash
just --justfile ~/my-cubrid/cubrid-justfiles/justfile \
  tc-sync https://github.com/CUBRID/cubrid/pull/6864

# The same recipe works for another CUBRID PR when tc/pr-<number> exists in
# both testcase repositories.
just --justfile ~/my-cubrid/cubrid-justfiles/justfile \
  tc-sync https://github.com/CUBRID/cubrid/pull/7588
```
