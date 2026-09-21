# Personal CUBRID Workflow

Read this reference before CUBRID work involving worktrees, remotes, CI or regression suites, or testcase repositories. Inspect the live environment for current worktrees, remotes, recipes, and CI configuration instead of relying on cached listings.

## Source and knowledge repositories

- `/home/vimkim/gh/cb` contains worktrees for `CUBRID/CUBRID`; `/home/vimkim/gh/cb/develop` is the `develop` worktree.
- `/home/vimkim/my-cubrid` contains personal CUBRID tools. In an initialized source worktree, use `just --list` and `just --show <recipe>` to discover the current interface.
- `/home/vimkim/gh/my-cubrid-docs` is the local knowledge base for CUBRID design, architecture, experiments, and project documentation.
- `/home/vimkim/gh/my-cubrid-jira` contains local CBRD issue drafts, reports, and planning context.

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
