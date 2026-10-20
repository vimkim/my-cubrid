#!/usr/bin/env bash
# Compatibility entrypoint. The Python supervisor owns locks and command lifetime.
set -euo pipefail

cli="${CUBRID_BUILD_COORDINATOR_CLI:-cubrid-build-coordinator}"
if ! command -v -- "$cli" >/dev/null 2>&1; then
  printf 'CUBRID build coordinator is not available: %s\n' "$cli" >&2
  printf 'Install cubrid-build-coordinator, or set CUBRID_BUILD_COORDINATOR_CLI to its reviewed executable.\n' >&2
  exit 127
fi
exec "$cli" "$@"
