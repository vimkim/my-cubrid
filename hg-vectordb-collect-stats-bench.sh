#!/bin/bash

REPEAT=${1:-5}
LIMIT=${2:-10000}
DBNAME=${3}
TABLENAME=${4}

select_times=()
select_fetches=()
scan_times=()
scan_fetches=()

get_median() {
    arr=($(printf '%s\n' "$@" | sort -n))
    len=${#arr[@]}
    if ((len % 2 == 1)); then
        echo "${arr[$((len / 2))]}"
    else
        echo "$(((${arr[$((len / 2 - 1))]} + ${arr[$((len / 2))]}) / 2))"
    fi
}

for i in $(seq 1 $REPEAT); do
    echo "Run $i..."

    OUTPUT=$(
        csql -u dba $DBNAME <<EOF
select vec into :tmp from nytimes_256_angular_train limit 1;
select count(*) from (select /*+ NO_MERGE */ cosine_distance (vec, :tmp) from $TABLENAME LIMIT $LIMIT);
;trace on
select count(*) from (select /*+ NO_MERGE */ cosine_distance (vec, :tmp) from $TABLENAME LIMIT $LIMIT);
EOF
    )

    SELECT_LINE=$(echo "$OUTPUT" | grep -A 1 "SUBQUERY" | grep "SELECT (time")
    SCAN_LINE=$(echo "$OUTPUT" | grep -A 2 "SUBQUERY" | grep "SCAN (table:")

    SELECT_TIME=$(echo "$SELECT_LINE" | sed -n 's/.*time: \([0-9]*\), fetch: \([0-9]*\).*/\1/p')
    SELECT_FETCH=$(echo "$SELECT_LINE" | sed -n 's/.*time: \([0-9]*\), fetch: \([0-9]*\).*/\2/p')

    SCAN_TIME=$(echo "$SCAN_LINE" | sed -n 's/.*heap time: \([0-9]*\), fetch: \([0-9]*\).*/\1/p')
    SCAN_FETCH=$(echo "$SCAN_LINE" | sed -n 's/.*heap time: \([0-9]*\), fetch: \([0-9]*\).*/\2/p')

    select_times+=("$SELECT_TIME")
    select_fetches+=("$SELECT_FETCH")
    scan_times+=("$SCAN_TIME")
    scan_fetches+=("$SCAN_FETCH")
done

summarize() {
    local label=$1
    shift
    local values=("$@")
    local sum=0 min=${values[0]} max=${values[0]}
    for val in "${values[@]}"; do
        ((sum += val))
        ((val < min)) && min=$val
        ((val > max)) && max=$val
    done
    avg=$((sum / ${#values[@]}))
    med=$(get_median "${values[@]}")
    echo "$label -> avg, min, max, median"
    echo "$avg"
    echo "$min"
    echo "$max"
    echo "$med"
}

echo ""
summarize "SELECT TIME" "${select_times[@]}"
summarize "SELECT FETCH" "${select_fetches[@]}"
summarize "SCAN TIME" "${scan_times[@]}"
summarize "SCAN FETCH" "${scan_fetches[@]}"
