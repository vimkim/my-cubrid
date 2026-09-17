# Runtime guard transaction recovery

`init` records an owner-only, versioned `transaction.json` beside the worktree
manifest before publishing allocation metadata or changing configuration. The
record contains the operation, generation, complete intended manifest,
predecessor metadata, and the before/after configuration hashes. It contains no
inherited environment values or configuration-file contents.

The registry lock covers selection, fresh live observation, allocation,
publication, and reconciliation. A retry uses the recorded generation and
bundle. Registry and manifest contents must belong to that generation or its
recorded predecessor; a writer also checks file identities at each publication.
A concurrent retry that observes the first retry complete validates that result
without publishing another generation.

Only the original operation and selection can continue an unfinished generation.
Use the original `init --preset PRESET`, worktree, installation, and database
selection. Changed configuration outside either recorded hash, unknown live
ownership, or conflicting live resources keeps the transaction
`recovery_required`. Correct the diagnostic's cause and repeat the same command.
Generation disagreement refuses all writes so a stale writer cannot mark newer
state as requiring recovery.

The recognized transaction states are `initializing`, `ready`, `deinitializing`,
and `recovery_required`. Adoption and deinitialization remain future commands;
their current refusal-only handlers enforce the unfinished-operation fence and
cannot release claims. A retained `deinitializing` operation blocks `init`.

Allocation considers registry claims, manifest claims, and transaction claims,
including predecessor claims while a transition is unfinished. Missing worktree
paths, absent processes, timestamps, and lease-like fields never release claims.
Recovery does not run CUBRID utilities or delete runtime data, sockets, or IPC.

State directories use `0700`; the registry, lock, manifests, transaction records,
and generated environment use `0600`. Atomic writes use a temporary file in the
destination directory, flush file content, rename, and flush that directory.
New directory entries and the initial lock creation are also flushed.

## Interruption matrix

The CLI tests abruptly exit through the fake observation adapter before and after
each publication below. Both initial initialization and reinitialization of an
already ready runtime execute the full matrix (32 interruption scenarios).

| Publication | Durable state when interrupted | Claim protection | Validation |
| --- | --- | --- | --- |
| Initial registry | Journal exists; registry absent, predecessor, or initializing | Journal and any predecessor | Non-ready |
| Initial manifest | Journal and registry; manifest absent, predecessor, or initializing | Journal, registry, and any manifest | Non-ready |
| Engine configuration | One configuration may have changed | Complete retained bundle | Non-ready |
| Broker configuration | Both configurations may have changed | Complete retained bundle | Non-ready |
| Worktree identity | Identity may be absent or installed | Journal also locates the canonical worktree | Non-ready |
| Generated environment | Environment may be absent, predecessor, or intended content | Complete retained bundle | Non-ready |
| Ready manifest | Registry remains initializing | Complete retained bundle | Non-ready |
| Ready registry | Manifest/registry may be ready; journal is unfinished | Complete retained bundle | Non-ready |

The final ready journal is the completion marker; two additional interruption
cases verify that validation changes from non-ready to ready at its publication.
Every matrix case retries to a
matching ready manifest, registry, and journal with the original generation and
claims. Test-created directories and state files are checked for private modes.

`tests/runtime-guard-test.py` also covers another worktree allocating around an
interrupted claim, concurrent recovery, generation mismatch, a writer paused
before publication while newer state appears, wrong commands and selections,
identity replacement, missing worktrees, old state, incomplete/contradictory
observations, and preservation of database-data and stale-socket stand-ins.
The recovery regression also combines interruption before registry publication
with an incomplete observation and a later healthy retry; the failure state keeps
the interrupted generation instead of relabeling the predecessor generation.
All observations and installation files are synthetic. Run it with
`python3 tests/runtime-guard-test.py`.
