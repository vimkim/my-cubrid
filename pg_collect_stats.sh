#!/bin/bash

set -euo pipefail
IFS=$'\n\t'

# Usage: ./script.sh [REPEAT] [LIMIT]
REPEAT=${1:-10}
LIMIT=${2:-10000}
DATABASE_NAME=${3:-vimkimdb}
TABLE_NAME=${4:-vimkim}
DIMENSION=${5:-9999999}

declare -a nested_times seq_times shared_hits exec_times # ← explicit arrays

for i in $(seq 1 $REPEAT); do
	echo "Run $i..."
	RESULT=$(psql -d $DATABASE_NAME -At -c "
    CREATE TEMP TABLE query_vector(vec vector($DIMENSION)) ON COMMIT DROP;
    INSERT INTO query_vector SELECT vec FROM $TABLE_NAME LIMIT 1;

    -- warm-up (not collected)
    SELECT sum(distance) FROM (
    SELECT inner_product(b.vec, q.vec) AS distance
    FROM $TABLE_NAME b, query_vector q
    LIMIT $LIMIT);

    EXPLAIN (ANALYZE, BUFFERS)
    SELECT inner_product(b.vec, q.vec) AS distance
    FROM $TABLE_NAME b, query_vector q
    LIMIT $LIMIT;
  ")

	echo "$RESULT"

	nested=$(echo "$RESULT" | grep "Nested Loop" | grep -oP "actual time=\d+\.\d+\.\.\K\d+\.\d+")
	seq=$(echo "$RESULT" | grep "Seq Scan on $TABLE_NAME" | grep -oP "actual time=\d+\.\d+\.\.\K\d+\.\d+")
	hit=$(echo "$RESULT" | grep "Buffers: shared hit=" | grep -oP "shared hit=\K\d+" | head -1)
	exec_time=$(echo "$RESULT" | grep "Execution Time" | grep -oP "[0-9]+\.[0-9]+")

	echo "$nested"
	echo "$seq"
	echo "$hit"
	echo "$exec_time"

	nested_times+=($nested)
	seq_times+=($seq)
	shared_hits+=($hit)
	exec_times+=($exec_time)
done

summary_stats() {
	local arr=("$@")
	local sorted=($(printf '%s\n' "${arr[@]}" | sort -n))
	local count=${#sorted[@]}
	local total=0

	for val in "${sorted[@]}"; do total=$(echo "$total + $val" | bc); done

	avg=$(echo "$total / $count" | bc -l)
	median=${sorted[$((count / 2))]}

	echo "avg: $avg"
	echo "min: ${sorted[0]}"
	echo "max: ${sorted[$((count - 1))]}"
	echo "median: $median"
}

echo
echo "==== Nested Loop Time (ms) ===="
summary_stats "${nested_times[@]}"

echo
echo "==== Seq Scan Time (ms) ===="
summary_stats "${seq_times[@]}"

echo
echo "==== Shared Buffers Hit ===="
summary_stats "${shared_hits[@]}"

echo
echo "==== Total Execution Time (ms) ===="
summary_stats "${exec_times[@]}"

summary_stats_json() {
	local metric="$1"
	shift
	local arr=("$@")
	local sorted=($(printf '%s\n' "${arr[@]}" | sort -n))
	local count=${#sorted[@]}
	local total=0
	for val in "${sorted[@]}"; do total=$(echo "$total + $val" | bc); done
	avg=$(echo "$total / $count" | bc -l)
	median=${sorted[$((count / 2))]}

	# Output each stat as a separate JSON line
	echo "{\"repeat\":$REPEAT,\"limit\":$LIMIT,\"dbname\":\"$DATABASE_NAME\",\"tablename\":\"$TABLE_NAME\",\"metric\":\"$metric\",\"stat\":\"avg\",\"value\":$avg}" >>pg_results.jsonl
	echo "{\"repeat\":$REPEAT,\"limit\":$LIMIT,\"dbname\":\"$DATABASE_NAME\",\"tablename\":\"$TABLE_NAME\",\"metric\":\"$metric\",\"stat\":\"min\",\"value\":${sorted[0]}}" >>pg_results.jsonl
	echo "{\"repeat\":$REPEAT,\"limit\":$LIMIT,\"dbname\":\"$DATABASE_NAME\",\"tablename\":\"$TABLE_NAME\",\"metric\":\"$metric\",\"stat\":\"max\",\"value\":${sorted[$((count - 1))]}}" >>pg_results.jsonl
	echo "{\"repeat\":$REPEAT,\"limit\":$LIMIT,\"dbname\":\"$DATABASE_NAME\",\"tablename\":\"$TABLE_NAME\",\"metric\":\"$metric\",\"stat\":\"median\",\"value\":$median}" >>pg_results.jsonl
}

# Export each metric to JSONL in the desired format
summary_stats_json "NESTED LOOP TIME" "${nested_times[@]}"
summary_stats_json "SEQ SCAN TIME" "${seq_times[@]}"
summary_stats_json "SHARED BUFFERS HIT" "${shared_hits[@]}"
summary_stats_json "TOTAL EXECUTION TIME" "${exec_times[@]}"

echo "Results exported to pg_results.jsonl"
