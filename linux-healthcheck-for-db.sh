#!/usr/bin/env bash
# db_tune_check.sh — quick Linux settings checklist for database workloads
# Read-only. Prints PASS/WARN/FAIL and hints.

set -u

RED=$(printf '\033[31m'); YEL=$(printf '\033[33m'); GRN=$(printf '\033[32m'); BLU=$(printf '\033[34m'); DIM=$(printf '\033[2m'); CLR=$(printf '\033[0m')
PASS="${GRN}PASS${CLR}"; WARN="${YEL}WARN${CLR}"; FAIL="${RED}FAIL${CLR}"

have() { command -v "$1" >/dev/null 2>&1; }

get_sysctl() { sysctl -n "$1" 2>/dev/null || awk -F= -v k="$1" '$1==k{gsub(/[[:space:]]/,"",$2);print $2}' /etc/sysctl.conf /etc/sysctl.d/*.conf 2>/dev/null | tail -1; }

row() { printf "%-28s  %s  %s\n" "$1" "$2" "$3"; }

header() { printf "\n${BLU}%s${CLR}\n" "$1"; printf "%-28s  %-8s  %s\n" "Check" "Status" "Notes"; printf "%-28s  %-8s  %s\n" "-----" "------" "-----"; }

bool_to_status() { # 0=good -> PASS, 1=caution -> WARN, 2=bad -> FAIL
  case "$1" in 0) echo "$PASS";; 1) echo "$WARN";; *) echo "$FAIL";; esac
}

# ---------- General ----------
header "System"

KERNEL=$(uname -r)
row "Kernel version" "$PASS" "$KERNEL"

SERVICE_ACTIVE() { systemctl is-active --quiet "$1" 2>/dev/null; echo $?; }

# NTP / time sync
TSVC=""
for s in chronyd systemd-timesyncd ntpd; do
  if systemctl list-unit-files "$s.service" >/dev/null 2>&1; then TSVC="$s"; break; fi
done
if [ -n "$TSVC" ] && [ "$(SERVICE_ACTIVE "$TSVC")" -eq 0 ]; then
  row "Time sync ($TSVC)" "$PASS" "time sync active"
else
  row "Time sync" "$(bool_to_status 2)" "enable chrony or systemd-timesyncd"
fi

# CPU governor
header "CPU / Scheduler"

GOV_MIX=""
GOV_BAD=0; GOV_WARN=0
for gpath in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
  [ -f "$gpath" ] || continue
  g=$(cat "$gpath" 2>/dev/null)
  GOV_MIX="$GOV_MIX $g"
  case "$g" in
    performance) : ;;
    schedutil|ondemand) GOV_WARN=1 ;;
    powersave|conservative) GOV_BAD=1 ;;
  esac
done
if [ -z "$GOV_MIX" ]; then
  row "CPU governor" "$WARN" "cpufreq not present (VM or server firmware manages P-states)"
else
  if [ $GOV_BAD -eq 1 ]; then row "CPU governor" "$(bool_to_status 2)" "use 'performance' for stable DB latency"
  elif [ $GOV_WARN -eq 1 ]; then row "CPU governor" "$(bool_to_status 1)" "prefer 'performance' over $GOV_MIX"
  else row "CPU governor" "$PASS" "performance"
  fi
fi

# irqbalance
if pgrep -x irqbalance >/dev/null 2>&1; then
  row "irqbalance" "$PASS" "running"
else
  row "irqbalance" "$(bool_to_status 1)" "not running; consider enabling to avoid CPU hot-spots"
fi

# ---------- Memory / VM ----------
header "Memory / VM"

# Transparent Huge Pages
thp_enabled=$(cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null || echo "")
thp_defrag=$(cat /sys/kernel/mm/transparent_hugepage/defrag 2>/dev/null || echo "")
if [ -z "$thp_enabled" ]; then
  row "Transparent Huge Pages" "$WARN" "not found (older kernel or container)"
else
  case "$thp_enabled" in
    *"[never]"* ) row "THP mode" "$PASS" "never";;
    *"[madvise]"*) row "THP mode" "$PASS" "madvise (preferred for DBs)";;
    *"[always]"*) row "THP mode" "$(bool_to_status 2)" "set to madvise or never for DBs";;
    *) row "THP mode" "$WARN" "$thp_enabled";;
  esac
  case "$thp_defrag" in
    *"[never]"*|*"[defer]"*) row "THP defrag" "$PASS" "$thp_defrag";;
    *"[always]"*|*"[madvise]"*) row "THP defrag" "$(bool_to_status 1)" "avoid defrag=always";;
    *) row "THP defrag" "$WARN" "$thp_defrag";;
  esac
fi

# Swappiness
SWP=$(get_sysctl vm.swappiness)
if [ -z "$SWP" ]; then SWP="(unset)"; row "vm.swappiness" "$WARN" "unset; common DB target 1–10"; else
  if [ "$SWP" -le 10 ]; then row "vm.swappiness" "$PASS" "$SWP"
  elif [ "$SWP" -le 30 ]; then row "vm.swappiness" "$(bool_to_status 1)" "$SWP (lower is typical for DBs)"
  else row "vm.swappiness" "$(bool_to_status 2)" "$SWP (too high for latency-sensitive DBs)"; fi
fi

# vm.dirty ratios/bytes
DBR=$(get_sysctl vm.dirty_background_ratio); DB=$(get_sysctl vm.dirty_background_bytes)
DR=$(get_sysctl vm.dirty_ratio); DRB=$(get_sysctl vm.dirty_bytes)
dirty_note=""
if [ -n "$DB" ] || [ -n "$DRB" ]; then
  # bytes mode
  dirty_note="bytes mode: bg=${DB:-unset} max=${DRB:-unset}"
  row "vm.dirty_* (bytes)" "$PASS" "$dirty_note"
else
  dbr_disp="${DBR:-unset}"; dr_disp="${DR:-unset}"
  status=1
  if [ -n "$DBR" ] && [ -n "$DR" ] && [ "$DBR" -le 10 ] && [ "$DR" -le 30 ]; then status=0; fi
  row "vm.dirty_ratio(s)" "$(bool_to_status $status)" "bg=${dbr_disp}, max=${dr_disp} (bg<=10, max<=30 typical)"
fi

# Overcommit policy
OCM=$(get_sysctl vm.overcommit_memory)
OCR=$(get_sysctl vm.overcommit_ratio)
case "${OCM:-}" in
  0) row "vm.overcommit_memory" "$PASS" "heuristic (0)";;
  1) row "vm.overcommit_memory" "$WARN" "always (1) — monitor for OOM under load";;
  2) row "vm.overcommit_memory" "$PASS" "strict (2) ratio=${OCR:-50}";;
  *) row "vm.overcommit_memory" "$WARN" "unset/unknown";;
esac

# HugePages (static)
HP_TOTAL=$(awk '/HugePages_Total/ {print $2}' /proc/meminfo)
if [ -n "$HP_TOTAL" ] && [ "$HP_TOTAL" -gt 0 ]; then
  row "HugePages (static)" "$PASS" "HugePages_Total=$HP_TOTAL"
else
  row "HugePages (static)" "$WARN" "disabled — consider for large shared buffers (Oracle/PG)"
fi

# Auto NUMA balancing
NB=$(get_sysctl kernel.numa_balancing)
if [ -n "$NB" ]; then
  if [ "$NB" -eq 0 ]; then row "kernel.numa_balancing" "$PASS" "off (fine for pinned DB processes)"
  else row "kernel.numa_balancing" "$(bool_to_status 1)" "on — test with it off for large DBs"; fi
else
  row "kernel.numa_balancing" "$WARN" "unset"
fi

# NUMA presence & topology
if have numactl; then
  NODES=$(numactl -H 2>/dev/null | awk '/available:/ {print $2}')
  if [ -n "$NODES" ] && [ "$NODES" -gt 1 ]; then
    row "NUMA topology" "$PASS" "$NODES nodes — pin DB & memory per-node"
  else
    row "NUMA topology" "$PASS" "single node"
  fi
else
  row "NUMA tools" "$WARN" "numactl not installed"
fi

# Swap device
if swapon -s 2>/dev/null | awk 'NR>1{exit 0} END{exit 1}'; then
  row "Swap" "$WARN" "enabled — OK for safety; keep small and swappiness low"
else
  row "Swap" "$PASS" "no active swap"
fi

# ---------- Block I/O ----------
header "Block I/O"

# Iterate block devices and recommend scheduler/read-ahead
for dev in /sys/block/*; do
  [ -d "$dev" ] || continue
  name=$(basename "$dev")
  # skip loop/ram/zram
  case "$name" in loop*|ram*|zram*) continue;; esac

  sched_file="$dev/queue/scheduler"
  if [ -f "$sched_file" ]; then
    SCHED=$(cat "$sched_file")
    # current scheduler is in [brackets]
    CUR=$(echo "$SCHED" | sed -n 's/.*\[\(.*\)\].*/\1/p')
  else
    CUR="(unknown)"
  fi
  ROT=$(cat "$dev/queue/rotational" 2>/dev/null || echo "?")
  RA=$(cat "$dev/queue/read_ahead_kb" 2>/dev/null || echo "?")
  RQ=$(cat "$dev/queue/rq_affinity" 2>/dev/null || echo "?")
  NRQ=$(cat "$dev/queue/nr_requests" 2>/dev/null || echo "?")

  # Heuristics
  status=1; note="sched=$CUR ra_kb=$RA rq_aff=$RQ nr_req=$NRQ"
  if [ "$ROT" = "0" ]; then
    # NVMe/SSD: prefer none or mq-deadline; BFQ is usually not ideal for DB
    case "$CUR" in
      none|mq-deadline) status=0;;
      kyber) status=1;;
      bfq|cfq|deadline) status=2;;
    esac
    devtype="NVMe/SSD"
  elif [ "$ROT" = "1" ]; then
    # HDD: mq-deadline good; BFQ sometimes ok for desktops, not DB
    case "$CUR" in
      mq-deadline|deadline) status=0;;
      bfq|cfq) status=2;;
      *) status=1;;
    esac
    devtype="HDD"
  else
    devtype="?"
    status=1
  fi
  row "Device $name ($devtype)" "$(bool_to_status $status)" "$note"
done

# Filesystem mount flags (noatime)
MNTWARN=0
while read -r line; do
  mnt=$(echo "$line" | awk '{print $3}')
  fstype=$(echo "$line" | awk '{print $5}')
  opts=$(echo "$line" | awk '{print $6}')
  case "$fstype" in ext4|xfs|btrfs)
    echo "$opts" | grep -q noatime || { row "Mount $mnt" "$(bool_to_status 1)" "$fstype without noatime"; MNTWARN=1; }
  ;;
  esac
done < <(mount -t ext4,xfs,btrfs 2>/dev/null)
if [ $MNTWARN -eq 0 ]; then row "Filesystem atime" "$PASS" "no obvious atime hotspots"; fi

# ---------- Networking (light) ----------
header "Networking"

SOMAX=$(get_sysctl net.core.somaxconn)
if [ -n "$SOMAX" ]; then
  if [ "$SOMAX" -lt 1024 ]; then row "net.core.somaxconn" "$(bool_to_status 1)" "$SOMAX (bump to 1024+ for busy DB listeners)"
  else row "net.core.somaxconn" "$PASS" "$SOMAX"; fi
else
  row "net.core.somaxconn" "$WARN" "unset"
fi

BACKLOG=$(get_sysctl net.core.netdev_max_backlog)
if [ -n "$BACKLOG" ]; then
  if [ "$BACKLOG" -lt 16384 ]; then row "netdev_max_backlog" "$(bool_to_status 1)" "$BACKLOG (common targets 16384–65536)"
  else row "netdev_max_backlog" "$PASS" "$BACKLOG"; fi
else
  row "netdev_max_backlog" "$WARN" "unset"
fi

# ---------- Limits / Services ----------
header "Process Limits & DB"

# open files
OPENF=$(ulimit -n 2>/dev/null || echo "")
if [ -n "$OPENF" ]; then
  if [ "$OPENF" -ge 65536 ]; then row "ulimit -n (nofile)" "$PASS" "$OPENF"
  else row "ulimit -n (nofile)" "$(bool_to_status 1)" "$OPENF (raise to >= 65536 for DBs)"; fi
else
  row "ulimit -n (nofile)" "$WARN" "unknown"
fi

# detect common DB processes
DBS=""
for p in postgres postmaster mysqld mariadbd mongod clickhouse-server oracle tnslsnr cockroach etcd; do
  pkill -0 "$p" 2>/dev/null && DBS="$DBS $p"
done
if [ -n "$DBS" ]; then
  row "Detected DB processes" "$PASS" "$(echo "$DBS" | xargs)"
else
  row "Detected DB processes" "$WARN" "none detected"
fi

# tuned / profile
if have tuned-adm; then
  PROF=$(tuned-adm active 2>/dev/null | awk -F': ' '/Current active profile:/ {print $2}')
  if echo "$PROF" | grep -qi "throughput-performance\|latency-performance\|virtual-guest\|virtual-host\|sap"; then
    row "tuned profile" "$PASS" "$PROF"
  else
    row "tuned profile" "$(bool_to_status 1)" "${PROF:-none} (consider throughput-performance)"
  fi
else
  row "tuned" "$WARN" "not installed — optional"
fi

# Clocksource
CS=$(cat /sys/devices/system/clocksource/clocksource0/current_clocksource 2>/dev/null || echo "")
if [ -n "$CS" ]; then
  row "Clocksource" "$PASS" "$CS"
else
  row "Clocksource" "$WARN" "unknown"
fi

echo
echo "${DIM}Tips:"
echo "- For PostgreSQL/MySQL: prefer THP=madvise or never; set governor=performance; keep swappiness <=10."
echo "- NVMe/SSD: scheduler=none or mq-deadline; HDD: mq-deadline."
echo "- Tune vm.dirty_* for your write rate; enable irqbalance; set nofile >= 65536."
echo "- Pin DB CPU/memory per NUMA node for big boxes; consider static HugePages for large SGA/shared_buffers."
echo "- Validate with real workload: perf/bpftrace + DB-level stats (pg_stat_* / performance_schema).${CLR}"

