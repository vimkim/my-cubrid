# Personal CUBRID Workflow

Read and follow this reference before any CUBRID-related task. These personal CUBRID policies override conflicting repository-local guidance. Inspect the live environment for current worktrees, remotes, recipes, and CI configuration instead of relying on cached listings.

## Source and knowledge repositories

- `/home/vimkim/gh/cb` contains worktrees for `CUBRID/CUBRID`; `/home/vimkim/gh/cb/develop` is the `develop` worktree.
- `/home/vimkim/my-cubrid` contains personal CUBRID tools. In an initialized source worktree, use `just --list` and `just --show <recipe>` to discover the current interface.
- `/home/vimkim/gh/my-cubrid-docs` is the local knowledge base for CUBRID design, architecture, experiments, and project documentation.
- `/home/vimkim/gh/my-cubrid-jira` contains local CBRD issue drafts, reports, and planning context.

Search `my-cubrid-docs` before web research for CUBRID-specific design or architecture context. Search `my-cubrid-jira` for CBRD tickets, pull-request context, or issue writeups.

## Local development

- Use the personal `just` recipes for local development, especially `just build` and `just build-test`.
  - `just build` finishes within 2 min for the first build, and within 20 secs for second build (thanks to ccache).
- In CUBRID organization-facing documentation, pull-request text, reviewer instructions, and verification steps, express the workflow with project-provided scripts, CMake, or ctest rather than personal recipes.
- Preserve existing indentation exactly and keep formatting changes semantically necessary. Report unexplained indentation-only changes as possible GNU indent issues.
- Most CUBRID `.c` sources compile as C++, while legacy `.c` and `.h` files are formatted with GNU indent. Wrap C++-specific syntax added to those legacy files exactly as follows so GNU indent preserves it:

```c
/* *INDENT-OFF* */
C++ syntax code
/* *INDENT-ON* */
```

- The repository-local blanket ban on C++ exceptions is stale for throwing STL operations. Prefer new `.cpp` files for new STL code; catch exceptions at the call site and immediately translate them into CUBRID's C-style error handling, including when STL must be used in an existing `.c` file.

## Source worktrees and remotes

- Prefer `CBRD-NNNNN-description` for ticket worktree and branch names.
- `just worktree <name>` creates a same-named sibling worktree and branch from the current HEAD. Its duplicate-ticket check rejects another sibling or registered worktree containing the same `CBRD-NNNNN`; it does not validate the complete naming form.
- `origin` is the CUBRID organization remote and `vk` is the personal fork. Use `vk` for ordinary personal branches and `origin` for `feature/*` branches.

If justfile does not exist in cubrid source worktree, run this inside worktree:

```sh
just -f ~/my-cubrid/cubrid-justfiles/justfile -d . prepare-build
```

This prepares the worktree for build-ready, and stows the personal justfile.

Remote selection is routing policy, not permission to push. Inspect the current branch and remotes before any publication action.

## Testcase repositories

| Suite | Repository root | Develop worktree |
|---|---|---|
| `test_medium`, `test_sql` | `/home/vimkim/gh/cubrid-testcases` | `/home/vimkim/gh/cubrid-testcases/develop` |
| `test_shell` | `/home/vimkim/gh/cubrid-testcases-private-ex` | `/home/vimkim/gh/cubrid-testcases-private-ex/develop` |

The private testcase repository is available locally and may be used when the task requires it. For testcase changes associated with a CUBRID pull request, use the authoritative branch name `tc/pr-<PR number>` in both testcase repositories and create corresponding worktrees as needed.

## CI and regression testing

- Pull requests targeting `develop` must pass CUBRID CI. The principal regression suites are `test_medium`, `test_sql`, and `test_shell`; inspect the live CI configuration for current jobs and timing.
- The QA team's separate regression runs may also cover replication, isolation, and other suites. Their testcases can span the public and private testcase repositories.

## Reproducing TC failure locally

- test_sql and test_medium: use `CTP.sh`.
- test_shell: `cubrid-shell-debug.sh` might help.

