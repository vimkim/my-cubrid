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
testcase branches. After both merges succeed, it pushes both updated branches
to `origin`.

If a testcase branch is already checked out in a linked worktree, `tc-sync`
uses that worktree and leaves the configured checkout on its current branch.
Both selected worktrees must be clean before synchronization begins. Changes
in other worktrees do not block synchronization.

```bash
just --justfile ~/my-cubrid/cubrid-justfiles/justfile \
  tc-sync https://github.com/CUBRID/cubrid/pull/6864

# The same recipe works for another CUBRID PR when tc/pr-<number> exists in
# both testcase repositories.
just --justfile ~/my-cubrid/cubrid-justfiles/justfile \
  tc-sync https://github.com/CUBRID/cubrid/pull/7588
```

## Testcase feature-baseline check

Run `tc-base-check` from a CUBRID source worktree whose PR targets
`feature/<name>`. It checks, without changing any branch, that `tc/pr-<number>`
in both testcase repositories contains the latest `origin/feature/<name>`.
PRs targeting other bases are skipped. `tc-base-check-oos` fixes the base to
`feature/oos-merge` and fails when the current PR targets another base. Both
recipes run in the invoking directory and accept `--pr N`.

```bash
just --justfile ~/my-cubrid/cubrid-justfiles/justfile tc-base-check-oos
just --justfile ~/my-cubrid/cubrid-justfiles/justfile tc-base-check --pr 7990
```

## Feature PR testcase synchronization

A feature branch's own merge PR (`develop <- feature/<name>`) also has
`tc/pr-<number>` testcase branches, and they must always match
`feature/<name>` in both testcase repositories. `tc-feature-sync-check`
finds the open `develop <- feature/<name>` PR in `CUBRID/cubrid` with `gh`,
shows how the branches relate, and, only when `tc/pr-<number>` is strictly
behind, asks before fast-forwarding and pushing it without force. If the TC
branch is ahead or has diverged, it stops so the edits can move to the
feature branch first. `tc-feature-sync-check-oos` fixes the feature to
`feature/oos-merge`. Pass `--pr N` to skip the lookup.

```bash
just --justfile ~/my-cubrid/cubrid-justfiles/justfile tc-feature-sync-check-oos
just --justfile ~/my-cubrid/cubrid-justfiles/justfile \
  tc-feature-sync-check feature/oos-merge --pr 7990
```
