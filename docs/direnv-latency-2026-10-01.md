# CUBRID direnv latency investigation

Entering `feature-oos-merge` takes 7–8 seconds because the shared `.envrc`
executes `my-cubrid-runtime validate`. This is reproducible without starting or
stopping a database. The measurements below were taken on the user's existing
remote Linux host on 2026-10-01, with preset `debug_gcc`.

## Measurements

Run `direnv exec . true` from `/home/vimkim/gh/cb/feature-oos-merge`, timing each
invocation with Python's `time.monotonic()` and discarding stdout. Do not evaluate
or print the shell's complete environment.

| Invocation | Original | Indexed collision check |
| --- | ---: | ---: |
| 1 | 8.109 s | 2.357 s |
| 2 | 7.206 s | 2.351 s |
| 3 | 7.235 s | 2.308 s |

The patched measurements used `MY_CUBRID=/home/vimkim/my-cubrid-direnv-latency`
for the invocation only. The shared `.envrc` supports that override. The median
improvement is approximately 68%. It still fails an aspirational one-second
shell-load budget; this patch is a bounded optimization, not the proposed
redesign below.

Direct original runtime validation took 8.039 s. `brew --prefix ncurses` took
0.014 s; `mise where java` took 0.023 s.

A Python cProfile run of original validation recorded 118,496 `paths_overlap`
calls. `reject_managed_claim_collisions` consumed 23.196 s of 25.725 s spent in
validation. Profiling increases execution time: those numbers locate cost and
must not be compared directly with unprofiled shell timings. There were 15
retained manifests and 92 path claims for the selected runtime.

The old implementation compares every selected path with every retained path.
Each comparison walks both paths' ancestors and observes both files, including
reading regular-file contents through the generic observation adapter. Missing
paths are repeatedly checked too. The cost grows with both claim counts.

The fix indexes retained paths, their ancestors, and existing device/inode
identities once per collision check. It preserves equal-path, ancestor,
descendant, and hardlink collision detection. No cross-invocation cache exists;
subsequent validation observes filesystem changes again. Ports, IPC keys,
retained manifests, installation hashes and runtime ownership checks remain in
place. The preexisting observation/operation race remains; this optimization
does not claim atomic filesystem snapshots.

After the fix, cProfile reports 2.050 s in `file_hash` and 0.537 s in
`inspect_runtime`, out of 3.047 s in validation. Hashing installations and
observing host resources explain why fixing collision lookup alone does not
make directory entry immediate.

## Verification

`python3 tests/runtime-claims-test.py` first failed with **24,000 observations
against a maximum of 340** for 40 selected and 300 retained paths. The indexed
implementation passes. Tests also cover path ancestry, misleading string
prefixes, missing files, cross-device inode numbers, refreshed observations,
and differential comparison with the old predicate using real hardlinks.

`python3 tests/runtime-environment-test.py`: 19 tests passed.

`python3 tests/runtime-guard-test.py`: 134 tests passed in 134.531 s.

`python3 tests/runtime-claims-test.py`: all 5 tests passed.

`git diff --check`: passed.
No production runtime is created, stopped, adopted, or removed by these
measurements. Database isolation has not been requalified through a live
multi-worktree database experiment; the patch preserves the existing checks.

## Simpler design for the stated minimum workflow

The external interface should let an agent create a worktree, build it, run its
own database, run tests, and clean up that database. Existing recipes already
cover much of this (`just worktree`, `just build`, database recipes and test
runners). The expensive part is the contract imposed on environment loading.

Proposed separation:

1. **Directory entry:** load the selected installation and private runtime paths
   from worktree metadata. Check metadata identity, ownership, preset and
   transaction consistency. Do not scan host processes, hash the installation,
   or compare all other worktrees. Loaded configuration must not be presented as
   proof that a runtime is currently validated.
2. **Provisioning:** allocate distinct ports, IPC keys, socket directory and
   database registry/storage once for the worktree. Keep allocation changes
   serialized. Concurrent native instances need all of these, not merely
   distinct database names.
3. **Database/test execution:** the coordinator acquires the worktree lock and
   validates at the point of use, then executes with that worktree's environment.
   Installation or teardown requires the appropriate idle-state checks.
4. **Diagnostics:** an explicit validation command performs the full inspection
   when the user needs an explanation of resource ownership or drift.

This proposal contradicts the environment-readiness requirement of
`docs/adr/0001-enforce-runtime-guard-in-managed-workflow.md`; it is not implemented
by the performance patch. A follow-up needs to define loaded-versus-validated
state, audit consumers of `CUBRID_RUNTIME_READY`, preserve build-only and preset
mismatch behavior, and test changes between shell load and command execution.
Simply skipping validation while still exporting `CUBRID_RUNTIME_READY=1` would
leave a misleading contract.

Acceptance for that redesign: directory entry below 0.2 s on this host; two
agent worktrees can create/start/query/test their databases independently;
stopping or removing one preserves the other; a changed preset or unfinished
initialization cannot accidentally select another installation; coordinated
operations detect configuration/resource conflicts at execution time.

A wholesale runtime rewrite is not necessary to land the measured optimization.
The environment-loading separation is the next substantive simplification.
