#!/usr/bin/env bash
# Usage: run.sh <cubrid-checkout> <work-dir> [suite.qls]
# Builds <work-dir>/db from <checkout>/src if missing, clears its cache, runs the suite cold,
# and writes results.sarif, analyze.log, *.time and summary.tsv into <work-dir>.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
src=$(cd "${1:?cubrid checkout}" && pwd)
out=${2:?work dir}
suite=${3:-$here/cubrid-bugs.qls}
threads=${THREADS:-40}
ram=${RAM_MB:-64000}
layer_timeout=${LAYER_TIMEOUT:-300}
wall_limit=${WALL_LIMIT:-20m}
codeql=${CODEQL:-codeql}
mkdir -p "$out"
db=$out/db

if [ ! -d "$db" ]; then
  /usr/bin/time -v -o "$out/create.time" \
    "$codeql" database create "$db" --language=cpp --build-mode=none \
      --source-root="$src/src" --threads="$threads" >"$out/create.log" 2>&1
fi
"$codeql" database cleanup "$db" --cache-cleanup=clear >/dev/null
rm -rf "${db:?}/results"

rc=0
/usr/bin/time -v -o "$out/analyze.time" \
  timeout "$wall_limit" "$codeql" database analyze "$db" "$suite" \
    --format=sarif-latest --output="$out/results.sarif" \
    --threads="$threads" --ram="$ram" --timeout="$layer_timeout" \
    --expect-discarded-cache >"$out/analyze.log" 2>&1 || rc=$?

grep -E 'Elapsed \(wall|Maximum resident' "$out"/*.time || true
python3 "$here/summarize.py" "$suite" "$out/analyze.log" "$out/results.sarif" | tee "$out/summary.tsv" || true
exit "$rc"
