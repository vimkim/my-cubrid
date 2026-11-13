# Format checks for CUBRID logging functions

CUBRID's printf-style logging functions have no `__attribute__ ((format (printf, F, A)))`. Because of that, GCC does not compare their format strings with their arguments. These tools add the attribute to the logging functions, then count and classify the `-Wformat` warnings that appear. The data is from CUBRID `develop` at `e64a04a79a` with GCC 11.5.0.

## Files

| File | Purpose |
| --- | --- |
| `add_format_attr.py` | Codemod. Adds the attribute to 28 logging prototypes listed in `TABLE`. It is idempotent and keeps lines within GNU indent's 120 columns |
| `fmtwarn.py` | Reads a GCC build log, maps each format diagnostic to the line that holds its format string, and classifies it |
| `warnings-debug.tsv` | Output of `fmtwarn.py` for the `debug_gcc` build: 286 diagnostics |
| `warnings-release.tsv` | The same for `release_gcc`. Its 7 extra `-Wformat-overflow` and `-Wformat-truncation` rows come from `sprintf` and `snprintf`, not from the attribute |
| `warnings-debug-by-function.tsv` | Each debug site with the logging function it reaches. The mapping is a guess from the call text around the site |

## Reproduce

```bash
python3 add_format_attr.py <cubrid-worktree>
# cubrid_log_tracelog in src/api/cubrid_log.c has no prototype, so add one with the attribute (printf, 6, 7) by hand.
cmake --build --preset debug_gcc -- -k 0 > build.log 2>&1   # -k 0: -Werror=format-security stops the build otherwise
python3 fmtwarn.py build.log <cubrid-worktree> > warnings.tsv
```

`fmtwarn.py` prints a summary by category and file on stderr.

## Categories

| Category | Meaning | Debug count |
| --- | --- | --- |
| `real` | The argument size or kind differs from the specifier, or the argument count is wrong | 125 |
| `width` | Both are integers of the same size on LP64, such as `long` for `%lld`. Prints correctly on Linux | 115 |
| `nonliteral` | A non-literal format with no arguments. It is already a hard error through `-Werror=format-security` | 41 |
| `empty` | A zero-length format string | 5 |

Release presets build with `-Werror`. Adding the attribute therefore needs every site fixed, including the `width` sites. For 64-bit typedefs, use a `(long long)` cast with `%lld`, not `%ld`, because `long` is 32 bits on Windows.

The 16 sites with a wrong argument count or kind are tracked in [CBRD-28094](https://jira.cubrid.org/browse/CBRD-28094).
