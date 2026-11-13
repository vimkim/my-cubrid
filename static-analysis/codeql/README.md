# CodeQL bug suite for CUBRID

`cubrid-bugs.qls` is a 59-query CodeQL suite for the CUBRID engine source. Analysis finishes in about 4 minutes on this machine (6 minutes with the database build), and most of its hits are real defects. The stock suites do not finish here. `cpp-security-and-quality` crashes in a transitive closure, and `cpp-code-scanning` ran for 3 h 17 min before it ran out of memory.

## Run the suite

You need CodeQL 2.27.4 with `codeql/cpp-queries` 1.10.0 on `PATH`. The bundle in `~/.local/opt/codeql` has both.

```bash
static-analysis/codeql/run.sh <cubrid-checkout> <work-dir>
```

`run.sh` does these steps:

1. If `<work-dir>/db` does not exist, it builds the database from `<cubrid-checkout>/src` with `--build-mode=none`. Point it at `src` only. A database of the whole checkout pulls in the `build_preset_*` trees, the TBB sources and the generated `csql_grammar.c`, and the analysis then crashes.
2. It clears the evaluation cache and deletes `db/results`, so that every run evaluates every query. Without the delete, `analyze` reuses the old `.bqrs` files and finishes in 8 seconds without doing any work.
3. It runs `codeql database analyze` under `timeout`, with a RAM cap and a per-layer timeout.
4. It prints the wall time and the peak RSS, and writes `summary.tsv`.

The two time limits behave differently:

- If an RA layer runs longer than `LAYER_TIMEOUT`, CodeQL skips only the queries that need that layer and finishes the rest. It still writes `results.sarif`, prints `ERROR: Some queries timed out`, and `run.sh` exits with 33. A shared predicate can take many queries with it. In a test with a 2-second limit, one predicate made 49 of the 59 queries time out.
- If the whole analyze step runs longer than `WALL_LIMIT`, `timeout` kills it and `run.sh` exits with 124. No `results.sarif` is written.

To analyze a new commit, use a new `<work-dir>` or delete `<work-dir>/db`. An existing database is not rebuilt.

These environment variables override the defaults:

| Variable | Default | Meaning |
| --- | --- | --- |
| `THREADS` | 40 | `--threads` for create and analyze |
| `RAM_MB` | 64000 | `--ram` for analyze |
| `LAYER_TIMEOUT` | 300 | `--timeout` in seconds. CodeQL applies it to each RA layer, not to a whole query |
| `WALL_LIMIT` | 20m | `timeout` for the whole analyze step. This is the real guard against a runaway query |
| `CODEQL` | `codeql` | The CodeQL binary |

Delete the work directory when you are done. The database is about 750 MB, and the cache grows during a run.

## Read the results

The work directory holds these files:

- `summary.tsv` has one row per query, with the id, the eval seconds, the hit count and the query path. A query with `-` in the eval column has no "Evaluation done" line. It timed out or did not run.
- `results.sarif` has the hits. To list them as `rule`, `file:line` and message, run this command:

  ```bash
  jq -r '.runs[].results[] | [.ruleId, (.locations[0].physicalLocation | "\(.artifactLocation.uri):\(.region.startLine)"), .message.text] | @tsv' results.sarif
  ```

- `analyze.log`, `analyze.time`, `create.log` and `create.time` hold the raw output and the `/usr/bin/time -v` measurements.

At e64a04a79a the suite reports 30 hits in 10 queries. Triage found 19 real defects, 2 unclear hits and 9 false positives. On a new commit, compare the hit list with the baseline below by query and file. Line numbers move between commits. New hits are the ones to read.

| Query | Hits | Real | Known false positives |
| --- | --- | --- | --- |
| `cpp/ambiguous-assignment-of-comparison` | 1 | `parser/type_checking.c:20059` (CBRD-28083) | |
| `cpp/nested-loops-with-same-variable` | 5 | `object/schema_manager.c:723` (CBRD-28084), `optimizer/query_graph.c:5294` | `object/trigger_manager.c:5579`, `broker/query_replace.c:492`, `:559` |
| `cpp/wrong-number-format-arguments` | 2 | `storage/double_write_buffer.cpp:1426`, `:3290` | |
| `cpp/wrong-type-format-argument` | 1 | `base/resources.cpp:168` | |
| `cpp/too-many-format-arguments` | 5 | `query/vacuum.c:4912`, `thread/critical_section.c:651`, `transaction/log_applier.c:5902`, `:8506`, `transaction/log_manager.c:13879`. All lose debug-log data only | |
| `cpp/overflowing-snprintf` | 3 | | `broker/broker_log_replay.c:1168`. Unclear: `base/hide_password.cpp:715`, `:716` |
| `cpp/suspicious-sizeof` | 1 | `executables/master_heartbeat.c:7146` (in a function that nothing calls) | |
| `cpp/suspicious-call-to-memset` | 2 | `base/area_alloc.c:347` | `query/query_executor.c:2046` |
| `cpp/new-array-delete-mismatch` | 4 | `win_tools/cubridtray/CUBRIDtray.cpp:187`, `:188`, `CUBRIDManage.cpp:465`, `:482` | |
| `cpp/overrunning-write` | 6 | `compat/db_macro.c:2231`, `:2240` | `compat/db_macro.c:2203`, `:2212`, `broker/broker_monitor.c:3105`, `query/crypt_opfunc.c:1627` |

The other 49 queries have no hits at e64a04a79a. They are in the suite because their precision is high and they add no noise. Whether they catch new defects is not yet shown. The database is built without the real compiler flags, so some defects may also go undetected.

## Measurements

These numbers come from one machine with 80 cores and 251 GB of RAM, CodeQL 2.27.4, and the source at e64a04a79a. Other jobs were also running, and the load average was 21 to 53. Two of the 59-query runs used a new database. The third reused the second one's database after its cache and results were deleted. All three runs evaluated all 59 queries and gave the same per-query hit counts. One full run, database included, takes about 6 minutes. `--timeout` and `WALL_LIMIT` never fired.

| Step | Wall time | Peak RSS | Runs |
| --- | --- | --- | --- |
| `database create`, `src` only | median 1:53, range 1:48 to 2:06 | 10.2 to 11.7 GiB | 3 |
| `analyze`, 59 queries, cold | median 3:44, range 3:20 to 4:02 | 35.4 to 35.6 GiB | 3 |
| `analyze`, 78 candidate queries, cold | 3:23 | 35.8 GiB | 1 |

The analysis used about 9 of its 40 threads on average (898% CPU). The slowest queries (`DoubleFree`, `UseAfterFree`, `CastArrayPointerArithmetic`, `IteratorToExpiredContainer`) finish at 165 to 172 s, and many others finish at the same moments. This suggests that a shared chain of predicates sets the wall time, not the number of queries or cores. This is an inference from the CPU share and the completion times. It was not profiled. The 78-query run (3:23) and the 59-query runs (3:20 to 4:02) show no measurable difference. The spread between runs is larger than any effect of the 19 removed queries.

A query's eval time in `summary.tsv` includes the shared predicates that it computed first, so it is not the cost of that query alone.

## How the queries were chosen

The candidates were the `problem` and `path-problem` queries in `Likely Bugs`, `Critical` and `Security` with precision `high` or `very-high`. A few `medium` queries from `Likely Bugs` were added as candidates on probation because they check syntax only. All 78 candidates ran on a fresh database. Their 991 hits were then triaged against the source.

A query stays in the suite if most of its hits are real, or if it has no hits. A query is dropped if its hits are mostly false positives or are about style only.

These 37 queries were excluded before the measurement because they use global data flow or remote taint sources: the queries that import `FlowSources`, `DataFlow::Global` or `TaintTracking::Global`, such as `CleartextFileWrite`, `UncontrolledFormatString`, `ExposedSystemData`, `CleartextTransmission`, `SqlTainted` and `TaintedPath`. In the earlier `cpp-code-scanning` run, the first four of these exceeded the 2 GiB result limit, and the run then ran out of memory. Two global-flow queries, `CastArrayPointerArithmetic` and `IteratorToExpiredContainer`, ran as probes. They finished in about 170 s with no hits, and they stay in the suite. They belong to the class of queries that ran out of memory before, so if a future run slows down, drop them first.

These queries were excluded because an earlier run showed them to be noise: `MistypedFunctionArguments` (97,919 hits), `LocalVariableHidesGlobalVariable` (12,305), `StackAddressEscapes` (1,760, mostly in TBB), the `Unused*` queries, the `Documentation` queries and the `jsf` queries.

These 19 candidates were dropped after triage:

| Query | Hits | Why it was dropped |
| --- | --- | --- |
| `cpp/useless-expression` | 338 | 1 real (`broker/broker_config.c:1793`). The rest are `MOP` and `bool` declarations that build-mode none misparsed |
| `cpp/ambiguously-signed-bit-field` | 153 | 0 real. Most are `std::int64_t` members and `public:` misread as bit fields |
| `cpp/inconsistent-null-check` | 136 | About 35% real in 17 sampled hits, almost all unchecked results on out-of-memory paths |
| `cpp/constant-comparison` | 122 | About 2% real. Most repeat an `assert` or come from misresolved macros |
| `cpp/dead-code-goto` | 115 | 1 real (`query/execute_statement.c:13176`). 114 flag a `break;` before a `case` label |
| `cpp/lossy-pointer-cast` | 48 | 0 real in 11 sampled hits. Types were misresolved |
| `cpp/non-member-const-no-effect` | 11 | 0 real. Style only |
| `cpp/toctou-race-condition` | 7 | 0 real. Files owned by the CUBRID user, with no privilege boundary |
| `cpp/integer-multiplication-cast-to-long` | 6 | 0 real. The operands are small |
| `cpp/redundant-null-check-simple` | 5 | 1 real (`storage/catalog_class.c:5402`). The other 4 are harmless repeated checks |
| `cpp/virtual-destructor` | 4 | 0 real. Nothing deletes through a base pointer |
| `cpp/comparison-with-wider-type` | 4 | 0 real. The loop bounds fit the counter type |
| `cpp/weak-cryptographic-algorithm` | 3 | The legacy DES password format, plus one name match on a variable called `des` |
| `cpp/unsigned-difference-expression-compared-zero` | 3 | Only inside `assert` |
| `cpp/pointer-overflow-check` | 2 | 0 real. Ordinary end-pointer loops |
| `cpp/signed-overflow-check` | 2 | 0 real. Clumsy `> 0` test on a small index |
| `cpp/suspicious-allocation-size` | 1 | 0 real. Third-party allocator in `heaplayers` |
| `cpp/unterminated-variadic-call` | 1 | 0 real. CUBRID has no sentinel-terminated variadic API |
| `cpp/member-const-no-effect` | 0 | Style only by design, dropped with its non-member twin |

The real bugs that dropped queries found are recorded above. Two of the noisy queries, `useless-expression` and `inconsistent-null-check`, may become useful on a database built from a traced real build. That is untested.
