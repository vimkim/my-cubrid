# CMake release presets

| Preset | Use |
| --- | --- |
| `release_gcc` | GCC RelWithDebInfo for benchmarks. Known unit-test options are off. |
| `release_clang` | Clang RelWithDebInfo for benchmarks. Known unit-test options are off. |
| `release_gcc_unit` | GCC RelWithDebInfo with `UNIT_TESTS`, `UNIT_TEST_OOS`, `UNIT_TEST_SPAGE`, and `UNIT_TEST_PAGE_BUFFER` on. Use it for unit tests. |
| `release_gcc_nounit` | GCC RelWithDebInfo with known unit-test options off. Its existing build directory is retained. |

The `unit` suffix identifies the test-enabled build while retaining the compiler and build family in its name. Debug and sanitizer presets keep their existing unit-test settings.

## Reconfigure an existing build

Each prepared CUBRID worktree links `CMakeUserPresets.json` to the shared file in `my-cubrid`. A change to that file on `main` therefore affects every linked worktree when it configures again.

Select the preset and reconfigure before building. `just build` alone uses the existing configuration; `just configure-build` updates it first.

```sh
just preset release_gcc
just configure-build
```

The preset explicitly sets the known unit-test options to `OFF`, including values left on in an existing cache. Inspect the cache and compiler commands in the CUBRID source worktree:

```sh
grep '^UNIT_TEST[^:]*:' build_preset_release_gcc/CMakeCache.txt
grep -c 'CUBRID_UNIT_TEST_ENABLED' build_preset_release_gcc/compile_commands.json
```

Every listed test option must be `OFF`. The second command prints `0` and exits with status 1 when no compiler command has the definition.

The justfile keeps normal reconfiguration because explicit preset values replace existing cache values. It does not discard other cached settings automatically. If an unknown stale `UNIT_TEST_*` cache option remains, reset the cache and configure again. This also removes other cached settings and requires CMake 3.24 or later.

```sh
cmake --fresh --preset release_gcc
```

After configuration, run `just build` to rebuild artifacts. Run `just build-and-install` if the benchmark uses installed binaries.
