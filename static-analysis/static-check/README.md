# cubrid-static-check

`cubrid-static-check` reports only the static-analysis findings that a CUBRID change adds. A full-tree run is mostly noise (831 cppcheck hits, 2,443 CPD groups at e64a04a79a), so the command compares each tool's output on the base and on the head and prints the difference.

## Run it

Install it with `just sync` in this repository. Then run it from a CUBRID worktree:

```bash
cubrid-static-check develop          # merge base of develop and HEAD, against HEAD
cubrid-static-check A B              # merge base of A and B, against B
cubrid-static-check --keep develop   # keep the work directory for inspection
```

It analyzes commits, not the working copy, so commit the change first. Markdown goes to stdout and progress to stderr. `--help` lists the options.

| Exit | Meaning |
| --- | --- |
| 0 | Nothing new, and every changed file was fully analyzed |
| 1 | New findings, new clones, or flagged functions |
| 2 | Usage or setup error, such as a bad ref, no compile database, or an internal failure |
| 3 | Nothing new, but some file was not fully analyzed, or an analyzer is missing. The report lists each case with the reason |

Tools: cppcheck 2.22, lizard 1.26, PMD 7.29 (`pmd cpd`), and clang-tidy (Homebrew LLVM 23), all on `PATH`. `lizard` is required. A missing cppcheck, clang-tidy or pmd skips its section and makes the run incomplete. `--no-clang-tidy` and `--no-cpd` skip a section on purpose.

## What it checks

The changed files are the C and C++ files under `src/` in `git diff -M <merge-base> <head>`. A renamed file is compared with its old path, so only its edited lines count as added.

cppcheck and clang-tidy analyze the changed `.c` and `.cpp` files and keep findings located in them. A changed header is analyzed only through those files, and the report says how many changed headers there are.

- **cppcheck** runs once per changed `.c`/`.cpp` file and side, with `--language=c++`, because CUBRID compiles its `.c` files as C++. It keeps `nullPointer`, `ctunullpointer`, `uninitvar`, `nullPointerRedundantCheck`, `invalidPrintfArgType_*`, and also these:
  - `nullPointerArithmeticRedundantCheck`, `nullPointerOutOfMemory`, `nullPointerOutOfResources`, `invalidScanfArgType_*` and `negativeIndex`. Each has 1 to 4 hits on the full tree. The ones checked are real: an unchecked `malloc` in `broker/cas_cgw_odbc.c:2853`, and `%lu` into a `long` in `cm_common/cm_mem_cpu_stat.c:827`.
  - Every `error`-severity id except configuration errors. On the full tree these are mostly `memleakOnRealloc` (7 hits, all the real unchecked-`realloc` pattern, such as `broker/broker_access_list.c:90`). The two false positives there (`invalidLifetime` in `parser/name_resolution.c`, `memsetClass` on an atomic) are in unchanged code, so the diff drops them.
- **clang-tidy** runs `bugprone-*` per file and side, minus 8 checks. Six of them made 820 of the 830 main-file hits in `storage/btree.c` (`signed-bitwise`, `narrowing-conversions`, `implicit-widening-of-multiplication-result`, `easily-swappable-parameters`, `macro-parentheses`, `reserved-identifier`). The other two made 26 of the 31 new hits in PR 8196 (`multi-level-implicit-pointer-conversion` on `memset`/`free` of a `T **`, and `assignment-in-if-condition` on CUBRID's `if ((error = f ()) != NO_ERROR)` idiom).
- **PMD CPD** runs once on all of head `src` at 100 tokens, given as a `--file-list` without `src/base/jisx0212.h`, `ksc5601.h` and `CRC.h` (`--exclude` had no effect in 7.29). A clone is reported when at least half of the lines of one occurrence were added by the change. Identifier-blind mode is not used: on the full tree it took 54 s and 15 GB against 35 s and 2.7 GB.
- **lizard** measures the changed functions on both sides. A function is changed when an added line or a deletion point falls inside it. It is flagged when its CCN grows by 5 or more, when its length grows by 100 lines or more, or when it is new with CCN 15 or more.

### How "new" is decided

A finding is keyed by tool, rule, head path, and message with digits replaced, so a shifted line does not make it new. The head findings minus the base findings, counted as a multiset, are the new ones.

A finding on an added line is preferred over an identical one on an unchanged line, so the reported line is the new one.

A file whose base side failed alone (timeout, no compile entry, or a parse error the head did not have) would make every head finding look new. Its head findings are not compared. The report lists them under "not fully analyzed" and the exit status is 3 unless something else is new.

### Compile database

The command reads the worktree's `compile_commands.json`, or the newest `build_preset_*/compile_commands.json`, or `--compile-db`. It rewrites the `src` and `include` paths into each exported tree and keeps the build-directory paths for generated headers and third-party code.

- **Stale database.** Entries for files that do not exist at head are counted and reported. At e64a04a79a there are 6, such as `src/object/schema_information_schema_builder.cpp`. These are the `missingFile` errors of the full-tree trial. Reconfigure the build to refresh the database.
- **New and renamed files.** A file without an entry uses the entry of its path on the other side of a rename, else the flags of a file in the same directory. The report names each borrowed entry.
- **Compiler macros.** cppcheck defines no compiler macros. The command passes `__GNUC__`, `__SIZEOF_INT128__`, `__x86_64__`, `__LP64__`, `__linux__` and `__unix__`, because the `#error` guards in `query/numeric_opfunc.h`, TBB and RapidJSON otherwise abort the translation unit and the file looks clean.

## Run time

Each per-file analysis has a 180 s limit (`--file-timeout`). cppcheck and clang-tidy share `--jobs` (half the cores by default) and run at the same time as CPD. The largest files (`query/query_executor.c`, `storage/heap_file.c`, `parser/type_checking.c`) take cppcheck longer than that as C++, so a change to them reports those files as not fully analyzed.

Measured on 2026-11-13 on an 80-core machine shared with other jobs (load average 110 to 165 during these runs, up to 380 in earlier ones). Peak RSS is about 2.7 GB, almost all of it CPD's JVM.

| Change | Files (.c/.cpp) | Wall time | Exit | Report |
| --- | --- | --- | --- | --- |
| `1684945ed0` termios include | 1 (1) | 27 s | 0 | nothing new |
| `b73143944d` RENAME TRIGGER owner check | 1 (1) | 59 s | 0 | nothing new; cppcheck takes 57 s on `execute_statement.c` |
| `0b80685455` EXISTS/IN unnesting | 2 (1) | 16 s | 1 | one flagged function, `qo_rewrite_exists_semi_anti` CCN 15 → 20 |
| `1684945ed0^..e64a04a79a`, 4 commits | 4 (3) | 47 s | 1 | the same flagged function |
| `309265e6d5` page batch execution, PR 8196 | 50 (25) | 117 s | 1 | 14 new clones, 92 flagged functions, 3 clang-tidy hits (`branch-clone` ×2, `signed-char-misuse`, all deliberate code); `query_executor.c` misses `px_merge_join.hpp` in the compile database |
| Self-test, four runs | 1 | 82 s | 0 | all four verdicts as expected |

CPD sets the floor at 15 to 35 s. cppcheck sets the ceiling on large files. In earlier runs of PR 8196 under heavier load, cppcheck timed out on `query_executor.c`, `heap_file.c` and `string_opfunc.c`. Those files were reported as not fully analyzed, and the three `string_opfunc.c` printf findings from a base-only timeout were held back as not compared. When base finished, they turned out to exist in base too.

## Self-test

```bash
static-analysis/static-check/selftest.sh <cubrid-worktree>
```

It commits synthetic changes on e64a04a79a in a temporary detached worktree and removes the worktree afterwards. It checks four verdicts:

- A comment-only change exits 0.
- The same change with no cppcheck on `PATH` exits 3.
- A rename with a comment-only edit exits 0.
- A change that appends a copy of `fi_thread_init` and a function that dereferences `NULL` exits 1, with `nullPointer` and a new clone in the report.
