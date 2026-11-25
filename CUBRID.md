# Personal CUBRID Workflow

Read and follow this reference before any CUBRID-related task. These personal CUBRID policies override conflicting repository-local guidance. Inspect the live environment for current worktrees, remotes, recipes, and CI configuration instead of relying on cached listings.

This reference applies to vimkim. Read [vimkim's CUBRID context](/home/vimkim/gh/my-cubrid-skills/cubrid-common/references/cubrid-vimkim.md) before interpreting issue assignments or planning work. Keep personal assignment facts in that profile.

## Source and knowledge repositories

- `/home/vimkim/gh/cb` contains worktrees for `CUBRID/CUBRID`; `/home/vimkim/gh/cb/develop` is the `develop` worktree.
- `/home/vimkim/my-cubrid` contains personal CUBRID tools. In an initialized source worktree, use `just --list` and `just --show <recipe>` to discover the current interface.
- `/home/vimkim/gh/my-cubrid-docs` is the local knowledge base for CUBRID design, architecture, experiments, and project documentation.
- `/home/vimkim/gh/my-cubrid-jira` contains local CBRD issue drafts, reports, and planning context.

Search `my-cubrid-docs` before web research for CUBRID-specific design or architecture context. Search `my-cubrid-jira` for CBRD tickets, pull-request context, or issue writeups.

## Daily tooling updates

Run `daily-update-cubrid` to first refresh and apply dotfiles through
`daily-update --dotfiles-only`, then fetch `origin/main`, fast-forward each
eligible CUBRID tool checkout, and install its commands through its existing
installation interface. The dotfiles step requires `daily-update` on PATH and
uses the configured chezmoi source: guarded fetch, `git merge --ff-only`, then
`chezmoi-apply-unmodified`. Each command is printed to stdout before it runs.
Dirty, ahead, diverged, detached and unexpected-origin dotfiles sources are
preserved; failed refreshes prevent applying stale sources. Locally edited
deployed targets are preserved by the helper. This mode does not mark the
general daily upkeep complete or load its project inventory.
Run `just sync` in this repository to install the updater itself.
The general `daily-update` refreshes the clean primary `~/my-cubrid` checkout
and runs `just daily-update` here. That recipe installs the freshly fetched
updater through `just sync`, then runs `daily-update-cubrid --skip-dotfiles`.
This avoids a second dotfiles application. Skips and failures propagate to
the general daily summary. Set `update = false` on its `my-cubrid` inventory
entry to stop this automatic integration after leaving CUBRID.
`--list` lists checkout paths without updating; `--dry-run` previews commands
without fetching, merging, or installing. Positional directories replace the defaults.
Unless `--skip-dotfiles` is passed, the dotfiles step also runs with positional
directories. `--list` and
`--dry-run` never run it; dry-run prints the delegation command and its purpose.

Defaults are `~/gh/my-cubrid-skills`, `~/gh/cubrid-tc-chronicle`,
`~/gh/cubrid-conf-tui`, `~/gh/cubrid-build-coordinator`,
`~/gh/cubrid-workenv`, `~/gh/cubrid-worktree`, `~/gh/cubrid-jira`,
`~/gh/cubrid-ci`, `~/gh/cubrid-ci-watch`, `~/gh/cubrid-pr-flow`, `~/gh/cubrid-qahome-fetcher`,
`~/gh/csql-future`, `~/gh/cubrid-dev2-pr-calendar`, `~/gh/my-cubrid-workflow`,
`~/gh/herdr-commander`, and `~/gh/cubrid-teams-dev2-vimkim-bot`.
`cubrid-qahome-fetcher` preserves its existing checkout name and location.
Existing tools use `just sync`; `cubrid-ci` uses `just install`,
and `cubrid-qahome` uses `uv tool install --reinstall .`. Custom directories
outside the defaults use their local `just sync` recipe.
`csql-future` is a standalone Python uv tool; its `just sync` runs
`uv tool install --reinstall .` and installs `csql-future` on the user PATH.
`cubrid-ci-watch` is a standalone Python uv tool; its `just sync` installs
`cubrid-ci-watch` on the user PATH, and its background poller runs as user
systemd unit `cubrid-ci-watch.service`.
`cubrid-pr-flow` is a standalone Python uv tool; its `just sync` installs
`cubrid-pr-flow` on the user PATH, and its orchestrator runs as user
systemd unit `cubrid-pr-flow.service`.
`cubrid-dev2-pr-calendar`, `my-cubrid-workflow`, and `herdr-commander`
use their `just sync` recipes.
`cubrid-worktree` uses `just sync` (aliased as `just install`) to install its Python uv tool on the user PATH.
`my-cubrid-skills` uses `just sync` to reconcile its skill collection.
`cubrid-tc-chronicle` uses `just sync` to reinstall the CLI. Its CI evidence
collection still requires an explicit `cubrid-tcc sync-data` invocation.
The Nushell `cs` alias calls `csql.sh`, which keeps database selection and SA/CS
verification before launching this wrapper with the active environment's `csql`.
Checkouts must be clean primary repositories on `main` tracking `origin/main`;
defaults also require the corresponding `vimkim` GitHub origin.
Dirty, ahead, diverged, detached, topic, linked, and symlinked checkouts are
preserved and skipped. A fetch failure prevents installation from stale sources.
Independent steps continue after a dotfiles or tool skip or failure. Exit status is 0 for
success, 2 for skips/partial sync, and 1 for any failure.

Personal workflow decision, 2026-10-22: the owner excludes `grill-tui`,
`gh-pr-comments-fetch`, `cubrid-dev2-pr`, and `volmap` from both daily updaters.
This decision reflects personal workflow, not project quality, maturity,
maintenance, or deprecation. Change these defaults only after an explicit owner
decision. `work-tracker` and `my-skills` remain managed by the general
`daily-update` command. As of 2026-11-16, `my-cubrid-skills` and
`cubrid-tc-chronicle` are managed here. The general inventory retains
`my-cubrid-skills` with `update = false` to protect its identities and skill
names from third-party maintenance and pruning.

Deprecation decision, 2026-10-22: use `cubrid-conf-tui` for interactive
configuration editing. `cubrid-ini-fzf` is deprecated and removed from
`daily-update-cubrid` and the shared `db::ini` recipe. Use
`just cubrid-conf-tui [DATABASE]` from a prepared worktree. The TUI currently
edits `[common]` only; support for `[standalone]` and `[@DATABASE]` is a required
follow-up tracked in its [README TODO](https://github.com/vimkim/cubrid-conf-tui#todo).

## Local development

For benchmark and unit-test preset selection and cache migration, see [CMake release presets](docs/cmake-presets.md).

- Before adding a function definition under `src/`, follow the [CUBRID function reuse procedure](/home/vimkim/gh/my-cubrid-skills/cubrid-common/references/function-reuse.md).
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

- Apply this naming and creation workflow to newly created worktrees; keep existing legacy worktrees and branches unchanged.
- Ticket-first naming (directory basename and matching local branch under `~/gh/cb/`):
  - `CBRD-NNNNN`: single original PR preparation, or first PR code review when `CBRD-NNNNN` is unoccupied.
  - `CBRD-NNNNN-<summary>`: derived worktrees (backports, follow-ups, experiments) and non-PR worktrees (tests, benchmarks, diagnostics, reproductions). Allowed whether or not `CBRD-NNNNN` already exists.
  - `CBRD-NNNNN-pr-<N>`: PR code review fallback when `CBRD-NNNNN` is already occupied.
  - `PR-<N>`: PR code review when the PR title contains no ticket key.
  - Keep `<summary>` in short kebab-case (`[A-Za-z0-9][A-Za-z0-9._-]*`), without `/` (which collides with `refs/heads/CBRD-NNNNN`), and without a second distinct ticket key.
- Entry is `pwd`-independent: use `cubrid-worktree` (distributed from `~/gh/cubrid-worktree` via `just sync` / `just install`) or the global recipes in `~/my-cubrid/cubrid-justfiles/justfile` (`worktree`, `worktree-open`, `worktree-list`, `pr-review`, `pr-review-all`). They resolve `~/gh/cb/develop` automatically from any starting directory, create `~/gh/cb/<name>`, run `prepare-build`, and open the target in Herdr when `HERDR_ENV=1`.
- Herdr topology follows one Space per ticket (`CBRD-NNNNN`, or `PR-<N>`): create the Space if missing (`herdr-next-to-current`, falling back to `herdr workspace create`), or open a new Tab inside that existing ticket Space for derived or additional ticket worktrees.
- `cubrid-worktree review` records both `branch.<name>.pr-url` and `branch.<name>.cubrid-role = review`. Keep review checkouts excluded from standing PR push/CI authorization.
- `origin` is the CUBRID organization remote and `vk` is the personal fork. Use `vk` for ordinary personal branches and `origin` for `feature/*` branches.

If `justfile` or environment links do not exist in a CUBRID source worktree, run this inside the worktree:

```sh
just -f ~/my-cubrid/cubrid-justfiles/justfile -d . prepare-build
```

This prepares the worktree for build-ready, and stows the personal justfile.

Remote selection is routing policy, not permission to push. Inspect the current branch and remotes before any publication action.

## Dev2 team membership

[GitHub CUBRID/dev2](https://github.com/orgs/CUBRID/teams/dev2/members) defines the current Dev2 roster. Run `cubrid-dev2-members` for one GitHub login per line or add `--json` for a JSON array. Install the command with `just sync` from this repository.

The command keeps the roster in `${XDG_CACHE_HOME:-$HOME/.cache}/my-cubrid/dev2-members.json` for 30 days. Use `--refresh` for current membership. On a failed refresh, the command exits with an error and preserves the previous cache. Use the live [PR approval gate](/home/vimkim/gh/my-cubrid-skills/cubrid-common/SKILL.md#pr-approval-gate) for merge decisions.

## Testcase repositories

| Suite | Repository root | Develop worktree |
|---|---|---|
| `test_medium`, `test_sql` | `/home/vimkim/gh/cubrid-testcases` | `/home/vimkim/gh/cubrid-testcases/develop` |
| `test_shell` | `/home/vimkim/gh/cubrid-testcases-private-ex` | `/home/vimkim/gh/cubrid-testcases-private-ex/develop` |

The private testcase repository is available locally and may be used when the task requires it. For testcase changes associated with a CUBRID pull request, use the authoritative branch name `tc/pr-<PR number>` in both testcase repositories and create corresponding worktrees as needed.

Keep TC PRs open to preserve isolation until the final engine merge handoff. Before recommending or performing TC closure, TC merging, or engine merging, follow [Testcase lifecycle](/home/vimkim/gh/my-cubrid-skills/cubrid-common/references/testcase-lifecycle.md). That reference owns the shared timing and close-versus-merge rules.

Before recommending a merge, asking for merge permission, or merging a CUBRID engine or testcase PR, apply the [PR approval gate](/home/vimkim/gh/my-cubrid-skills/cubrid-common/SKILL.md#pr-approval-gate). Show the current per-reviewer result before asking for permission and again immediately before each merge.

## CI and regression testing

- Pull requests targeting `develop` must pass CUBRID CI. The principal regression suites are `test_medium`, `test_sql`, and `test_shell`; inspect the live CI configuration for current jobs and timing. Keep the TC merge gate separate from regression results and finalize it only through the testcase lifecycle above.
- To trigger, rerun, or wait on PR `gha-ci`, follow `cubrid-ci-trigger` instead of posting `/run` ad hoc or polling with timers. It enforces testcase baseline checks, concurrency guards, `cubrid-ci-watch` registration, and event-driven waiting (`cubrid-ci-watch wait` in-session, or the host `cubrid-ci-watch.service` background poller when returning the session).
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

## Teams integration

Before working on Microsoft Teams bots, channels, PR calendar sync, or Graph API permissions, read [/home/vimkim/gh/my-cubrid-docs/cubrid-teams/README.md](/home/vimkim/gh/my-cubrid-docs/cubrid-teams/README.md) and [access-and-permissions.md](/home/vimkim/gh/my-cubrid-docs/cubrid-teams/access-and-permissions.md) for verified CUBRID tenant permissions, repository boundaries, and Playwright/RSC architecture rules.
