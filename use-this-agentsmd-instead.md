# CLAUDE.md — CUBRID Database Engine

CUBRID is an open-source C/C++17 RDBMS. Apache 2.0 license, version 11.5.x.

**Note:** `.c` files are compiled as C++17 (see `c_to_cpp.sh`). Large files (10K–30K+ lines) are intentional, not tech debt.

## Build

```bash
just build-test    # Build and test (preferred)
```

## Build Modes & Preprocessor Guards

Same source compiles to 3 different binaries via preprocessor flags:

| Guard | Binary | Purpose |
|-------|--------|---------|
| `SERVER_MODE` | `cub_server` | Server process |
| `SA_MODE` | `cubridsa` lib | Standalone (client+server in-process) |
| `CS_MODE` | `cubridcs` lib | Client library (connects to server) |

Parser/optimizer code is client-side: guarded with `#if !defined(SERVER_MODE)`.

## Code Style

- **Indentation**: 2 spaces, no tabs. **Line width**: 120 chars
- **Braces**: GNU style — opening brace on new line, indented to body level. Function braces at column 0
- **Naming**: C functions `module_action_object`, macros/typedefs `UPPER_SNAKE`, C++ classes `snake_case`
- **Header guards**: `_FILENAME_H_` (NOT `#pragma once`)
- **Includes**: `"quotes"` for project, `<angles>` for system. `config.h` first in `.c` files
- **`memory_wrapper.hpp` MUST be the LAST include** with comment: `// XXX: SHOULD BE THE LAST INCLUDE HEADER`
- C files: `/* ... */` comments only

## Error Handling

Error codes in `src/base/error_code.h` — always negative, `NO_ERROR = 0`. Use `er_set(ER_ERROR_SEVERITY, ARG_FILE_LINE, ER_CODE, ...)`.

Adding new error codes requires updates in 6 places:
1. `src/base/error_code.h` — Define the code
2. `src/compat/dbi_compat.h` — Client-visible copy
3. `msg/en_US.utf8/cubrid.msg` — English message
4. `msg/ko_KR.utf8/cubrid.msg` — Korean message
5. Update `ER_LAST_ERROR` constant
6. CCI's `base_error_code.h` if client-facing

## Anti-Patterns

- **Never** `free()` directly — use `free_and_init()`
- **Never** `#pragma once` — use `#ifndef _FILENAME_H_` guards
- **Never** place `memory_wrapper.hpp` before other includes
- **Never** use C++ exceptions in engine code — use `er_set` + return codes
- **Do NOT** split large files (10K+ lines)

## CI

PR title must match `^\[[A-Z]+-\d+\]\s.+` (e.g. `[CBRD-12345] Fix buffer overflow in btree`). CLA required before merge.
