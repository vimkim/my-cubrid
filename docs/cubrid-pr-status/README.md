# cubrid-pr-status

A read-only terminal view of CUBRID PR status, GitHub Actions and CircleCI results.
Requires Python 3.9+ and an authenticated GitHub CLI (`gh auth login`).

```sh
# Run inside a CUBRID Git checkout/worktree:
~/my-cubrid/bin/cubrid-pr-status

# Inspect a PR directly, from any directory:
~/my-cubrid/bin/cubrid-pr-status https://github.com/CUBRID/cubrid/pull/7939

# Refresh every 30 seconds after each fetch; Ctrl-C exits:
~/my-cubrid/bin/cubrid-pr-status --watch

# Search more previous PR commits or use a different expected-check list:
~/my-cubrid/bin/cubrid-pr-status --history 20 --config /path/to/checks.json
```

Edit `bin/cubrid-pr-status.json` to change the expected checks. Its format is
`{"expected_checks": ["gha-ci: test_sql", "ci/circleci: test_sql"]}`.
Discovered checks are also shown. Expected does not mean required by branch
protection, nor does it prove someone triggered the suite.

`current` means reported for the published PR head, which can differ from local
HEAD. A missing current check is `NOT OBSERVED`; an older result appears as
`STALE previous` with its own commit, time, and link. A previous pending run does
not mean current CI is running. An Actions workflow can run from develop while
reporting test results for a separate PR commit; its workflow SHA does not override
the status's reported-for commit. This display reports GitHub's association and
does not independently audit test artifacts.

History searches the last five earlier PR commits by default (`--history 0`
disables it, maximum 250). The output states the searched range. Results on commits
removed by force-push cannot be recovered through the PR commit list. GitHub's PR
commit API has a 250-commit limit; if the selected head is outside the returned
history, the script reports incomplete history. Increase `--history` if the last
CI run predates the default window. No result anywhere in the searched range is
different from proof that a job never ran.

The display gives available report timestamps and ages, not inferred queue times
or durations. Links go to provider check/job/run pages, where individual failed
testcases can be inspected. API failures are reported as incomplete data. A PR
head change during fetching rejects that snapshot; retry, or let watch refresh.
Watch pins the initially resolved PR URL and rereads its head each cycle. `--interval`
sets the wait between fetches; very short intervals consume more API requests.

Exit status is 0 when the view was fetched (even if CI failed), 2 for invalid input
or incomplete data, and 0 on Ctrl-C. The command does not trigger CI or write to
GitHub. The source, adjacent config, tests and design docs live in `~/my-cubrid`.

## Validation

```sh
python3 tests/cubrid-pr-status-test.py
uvx mypy --check-untyped-defs bin/cubrid-pr-status tests/cubrid-pr-status-test.py
```

The tests exercise the executable with controlled responses at the external `gh`
boundary. Live checks on 2026-09-14 verified URL selection using PR7939 and current
directory selection using PR7940. See [PLAN.md](PLAN.md) for the agreed design and
[CONTEXT.md](CONTEXT.md) for vocabulary.
