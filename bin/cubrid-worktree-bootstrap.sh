#!/usr/bin/env bash

set -euo pipefail

usage()
{
  cat <<'EOF'
Usage: cubrid-worktree-bootstrap.sh [OPTIONS]

Prepare and build a newly-created CUBRID Git worktree without interactive input.

Options:
  -p, --preset PRESET      CMake configure/build preset (default: debug_gcc)
  -C, --worktree PATH      CUBRID worktree path (default: current directory)
  -h, --help               Show this help

Examples:
  cubrid-worktree-bootstrap.sh
  cubrid-worktree-bootstrap.sh --worktree ../CBRD-12345
  cubrid-worktree-bootstrap.sh --preset release_gcc --worktree ../benchmark
EOF
}

die()
{
  echo "cubrid-worktree-bootstrap: $*" >&2
  exit 1
}

preset="debug_gcc"
worktree="."

while (($# > 0)); do
  case "$1" in
    -p|--preset)
      (($# >= 2)) || die "$1 requires a value"
      preset="$2"
      shift 2
      ;;
    -C|--worktree)
      (($# >= 2)) || die "$1 requires a value"
      worktree="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1 (see --help)"
      ;;
  esac
done

for command_name in git just cmake direnv stow lefthook nu; do
  command -v "$command_name" >/dev/null 2>&1 || die "required command not found: $command_name"
done

worktree=$(git -C "$worktree" rev-parse --show-toplevel 2>/dev/null) \
  || die "not a Git worktree: $worktree"

[[ -f "$worktree/CMakeLists.txt" && -d "$worktree/src" ]] \
  || die "not a CUBRID source worktree: $worktree"

export MY_CUBRID="${MY_CUBRID:-$HOME/my-cubrid}"
shared_justfile="$MY_CUBRID/stow/cubrid/justfile"
[[ -f "$shared_justfile" ]] || die "shared CUBRID justfile not found: $shared_justfile"

required_prepared_files=(
  justfile
  local.just
  .envrc
  CMakeUserPresets.json
)

needs_prepare=false
for relative_path in "${required_prepared_files[@]}"; do
  if [[ ! -e "$worktree/$relative_path" ]]; then
    needs_prepare=true
    break
  fi
done

if [[ "$needs_prepare" == true ]]; then
  echo "[cubrid-bootstrap] Shared worktree files are missing; running just prepare"
  just --justfile "$shared_justfile" --working-directory "$worktree" prepare
else
  echo "[cubrid-bootstrap] Worktree preparation files already exist"
fi

for relative_path in "${required_prepared_files[@]}"; do
  [[ -e "$worktree/$relative_path" ]] \
    || die "just prepare did not create required file: $worktree/$relative_path"
done

available_presets=$(
  cd "$worktree"
  cmake --list-presets=configure 2>&1 \
    | sed -n 's/^[[:space:]]*"\([^"]*\)".*/\1/p'
)

if ! grep -Fxq "$preset" <<<"$available_presets"; then
  echo "cubrid-worktree-bootstrap: unknown configure preset: $preset" >&2
  echo "Available presets:" >&2
  sed 's/^/  /' <<<"$available_presets" >&2
  exit 1
fi

current_preset=""
if [[ -f "$worktree/.env" ]]; then
  current_preset=$(sed -n 's/^[[:space:]]*PRESET_MODE[[:space:]]*=[[:space:]]*//p' "$worktree/.env" | tail -n 1)
fi

if [[ "$current_preset" != "$preset" ]]; then
  printf 'PRESET_MODE=%s\n' "$preset" >"$worktree/.env"
  echo "[cubrid-bootstrap] Selected preset: $preset"
else
  echo "[cubrid-bootstrap] Preset already selected: $preset"
fi

(
  cd "$worktree"
  direnv allow
)

actual_preset=$(
  cd "$worktree"
  direnv exec . sh -c 'printf %s "$PRESET_MODE"'
)
[[ "$actual_preset" == "$preset" ]] \
  || die "direnv loaded PRESET_MODE=$actual_preset instead of $preset"

echo "[cubrid-bootstrap] Configuring preset: $preset"
(
  cd "$worktree"
  direnv exec . just configure
)

echo "[cubrid-bootstrap] Building and installing preset: $preset"
(
  cd "$worktree"
  direnv exec . just build
)

echo "[cubrid-bootstrap] Ready: $worktree ($preset)"
