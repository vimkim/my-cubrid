# Personal CUBRID Workflow

Read and follow this reference before any CUBRID-related task. These personal CUBRID policies override conflicting repository-local guidance. Inspect the live environment for current worktrees, remotes, recipes, and CI configuration instead of relying on cached listings.

## Source and knowledge repositories

- `/home/vimkim/gh/cb` contains worktrees for `CUBRID/CUBRID`; `/home/vimkim/gh/cb/develop` is the `develop` worktree.
- `/home/vimkim/my-cubrid` contains personal CUBRID tools. In an initialized source worktree, use `just --list` and `just --show <recipe>` to discover the current interface.
- `/home/vimkim/gh/my-cubrid-docs` is the local knowledge base for CUBRID design, architecture, experiments, and project documentation.
- `/home/vimkim/gh/my-cubrid-jira` contains local CBRD issue drafts, reports, and planning context.

Search `my-cubrid-docs` before web research for CUBRID-specific design or architecture context. Search `my-cubrid-jira` for CBRD tickets, pull-request context, or issue writeups.

## Daily tooling updates

Run `daily-update-cubrid` to fetch `origin/main`, fast-forward each eligible
checkout, and install its commands through its existing installation interface.
Run `just sync` in this repository to install the updater itself.
`--list` lists checkout paths without updating; `--dry-run` previews commands
without fetching, merging, or installing. Positional directories replace the defaults.

Defaults are `~/gh/cubrid-conf-tui`, `~/gh/cubrid-build-coordinator`,
`~/gh/cubrid-workenv`, `~/gh/cubrid-jira`, `~/gh/cubrid-ci`,
`~/gh/cubrid-qahome-fetcher`, and `~/temp/cubrid-ini-fzf`.
The latter two preserve their existing checkout names and locations.
Existing tools use `just sync`; `cubrid-ci` and `cubrid-ini-fzf` use `just install`,
and `cubrid-qahome` uses `uv tool install --reinstall .`. Custom directories
outside the defaults use their local `just sync` recipe.
Checkouts must be clean primary repositories on `main` tracking `origin/main`;
defaults also require the corresponding `vimkim` GitHub origin.
Dirty, ahead, diverged, detached, topic, linked, and symlinked checkouts are
preserved and skipped. A fetch failure prevents installation from stale sources.
Independent projects continue after a skip or failure. Exit status is 0 for
success, 2 for skips/partial sync, and 1 for any failure.

Personal workflow decision, 2026-10-22: the owner excludes `grill-tui`,
`gh-pr-comments-fetch`, `cubrid-dev2-pr`, and `volmap` from both daily updaters.
This decision reflects personal workflow, not project quality, maturity,
maintenance, or deprecation. Change these defaults only after an explicit owner
decision. `work-tracker`, `my-skills`, `my-cubrid-skills`, and
`cubrid-tc-chronicle` remain managed by the general `daily-update` command.

## Local development

- Use the personal `just` recipes for local development: `just configure` generates build rules, `just build` produces artifacts, and `just install` installs existing artifacts.
  - Use `just build-and-install` for both stages, or `just configure-build-and-install` to include configuration. `just configure-build` omits installation.
  - `just build-test` builds and runs configured ctest tests. Use `just build-and-install-test` when tests need refreshed installed artifacts.
  - Explicit service stops use `just build-and-install --stop-runtime`.
  - `just build-and-install` finishes within 2 min for the first build, and within 20 secs for second build (thanks to ccache).
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

- For focused personal reproduction, use `cubrid-test-sql-run`, `cubrid-test-medium-run`, or `cubrid-test-shell-run` from `my-cubrid-skills`. These workflows explicitly select the suite's native `cubrid-testkit` runner under containment and prove verdict-bearing artifacts; CTP may supply assets but is not an implicit runner fallback.
- Keep full QA/organization regressions on the live project or CI workflow appropriate to that suite. A focused shell run does not establish whole-corpus shell equivalence.
- Use the legacy CTP runner only when the user explicitly requests a separate CTP run or comparison.

## Host work environment selection

For source-worktree initialization, direnv loading, preset/install selection, host
DB tests, or environment diagnosis, read [host work environments](docs/host-workenv.md).
It defines the explicit build/install → `cub-workenv init` boundary, ordinary
`cubrid`/`csql` execution, and the independent container workflow.

## Daemon startup from agent tools

Before starting CUBRID daemons, read
[daemon startup and captured output](docs/host-workenv.md#daemon-startup-and-captured-output).
Redirect stdin from `/dev/null` and both stdout and stderr to regular files.
Wait for the startup command with a deadline, then read the files.
Use a separate launcher session when the tool cleans up its process group.
[CBRD-27443](https://jira.cubrid.org/browse/CBRD-27443) can leave output pipes open
after the startup command exits. This also affects wrappers and subprocess capture.
Use a pipe only when the task explicitly requires reproducing this defect.
