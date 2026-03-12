#!/usr/bin/env bash

TOP_N=${1:-10}  # show top N processes per container, default 10

echo "==== SYSTEM OPEN FILES ===="
awk '{print "open=" $1-$2 " allocated=" $1 " max=" $3}' /proc/sys/fs/file-nr
echo

echo "==== HOST OPEN FILES ===="
total_host=$(ls /proc/*/fd/* 2>/dev/null | wc -l)
printf "%-20s total_open_files=%-10s\n" "$(hostname)" "$total_host"
printf "  %-8s %-25s %-10s\n" "PID" "NAME" "OPEN_FDS"
printf "  %-8s %-25s %-10s\n" "---" "----" "--------"
for fddir in /proc/[0-9]*/fd; do
    pid=$(echo "$fddir" | cut -d/ -f3)
    count=$(ls "$fddir" 2>/dev/null | wc -l)
    name=$(cat /proc/$pid/comm 2>/dev/null || echo "?")
    echo "$count $pid $name"
done | sort -rn | head -"$TOP_N" | while read count pid name; do
    printf "  %-8s %-25s %-10s\n" "$pid" "$name" "$count"
done
echo

echo "==== CONTAINER OPEN FILES ===="

sudo podman ps --format "{{.Names}}" | while read c; do
    total=$(sudo podman exec "$c" sh -c 'ls /proc/*/fd/* 2>/dev/null | wc -l')

    printf "%-20s total_open_files=%-10s\n" "$c" "$total"
    printf "  %-8s %-25s %-10s\n" "PID" "NAME" "OPEN_FDS"
    printf "  %-8s %-25s %-10s\n" "---" "----" "--------"

    sudo podman exec "$c" sh -c '
        for fddir in /proc/[0-9]*/fd; do
            pid=$(echo "$fddir" | cut -d/ -f3)
            count=$(ls "$fddir" 2>/dev/null | wc -l)
            name=$(cat /proc/$pid/comm 2>/dev/null || echo "?")
            echo "$count $pid $name"
        done
    ' 2>/dev/null | sort -rn | head -"$TOP_N" | while read count pid name; do
        printf "  %-8s %-25s %-10s\n" "$pid" "$name" "$count"
    done

    echo
done
