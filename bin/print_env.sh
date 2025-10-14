#!/usr/bin/env bash
set -euo pipefail

hdr(){ printf "\n=== %s ===\n" "$*"; }

PID=${1:-$$}  # pass a PID to inspect another process; defaults to this shell
SELF="/proc/$PID"

hdr "Host & Kernel"
uname -a || true
command -v lsb_release >/dev/null && lsb_release -ds || true

hdr "CPU topology & affinity"
# Logical/physical counts
command -v lscpu >/dev/null && lscpu | grep -E 'Model name|Socket|Core\(s\) per socket|Thread|NUMA node\(s\):|CPU\(s\):' || true
echo "nproc(all)=$(nproc --all 2>/dev/null || true)  nproc(allowed)=$(nproc 2>/dev/null || true)"

# Current thread affinity
if [ -r "$SELF/status" ]; then
  awk '/Cpus_allowed_list|Mems_allowed_list/ {print}' "$SELF/status"
fi
command -v taskset >/dev/null && taskset -pc "$PID" || true

# Scheduler policy / priority
if [ -r "$SELF/sched" ]; then
  awk 'NR<=20' "$SELF/sched"
fi

hdr "NUMA policy (if libnuma present)"
command -v numactl >/dev/null && numactl --show || echo "numactl not available"
command -v numactl >/dev/null && numactl --hardware | sed 's/^/  /' || true

hdr "Per-process resource limits (ulimits)"
if [ -r "$SELF/limits" ]; then
  cat "$SELF/limits"
fi
command -v prlimit >/dev/null && prlimit --pid "$PID" || true

hdr "cgroup placement"
# Which controllers & paths
cgfile="$SELF/cgroup"
[ -r "$cgfile" ] && cat "$cgfile"
# Detect cgroup v2
if mount | grep -q 'type cgroup2'; then
  CG2=$(awk -F: '{print $NF}' "$cgfile" | tail -n1)
  [ -z "$CG2" ] && CG2="/"
  CGROOT=$(awk '$3 ~ /cgroup2/ {print $3}' /proc/self/mounts | head -n1)
  CGPATH="$CGROOT$CG2"
  echo "cgroup v2 path: $CGPATH"

  # CPU quotas / shares
  [ -f "$CGPATH/cpu.max" ]      && echo "cpu.max:      $(cat "$CGPATH/cpu.max")   (format: quota micros / period micros or 'max')"
  [ -f "$CGPATH/cpu.weight" ]   && echo "cpu.weight:   $(cat "$CGPATH/cpu.weight")  (1..10000)"

  # CPU set
  [ -f "$CGPATH/cpuset.cpus" ]  && echo "cpuset.cpus:  $(cat "$CGPATH/cpuset.cpus")"
  [ -f "$CGPATH/cpuset.mems" ]  && echo "cpuset.mems:  $(cat "$CGPATH/cpuset.mems")"

  # Memory ceilings
  [ -f "$CGPATH/memory.max" ]       && echo "memory.max:       $(cat "$CGPATH/memory.max")"
  [ -f "$CGPATH/memory.high" ]      && echo "memory.high:      $(cat "$CGPATH/memory.high")"
  [ -f "$CGPATH/memory.swap.max" ]  && echo "memory.swap.max:  $(cat "$CGPATH/memory.swap.max")"

  # I/O throttles (if any)
  for f in io.max io.weight io.latency; do
    [ -f "$CGPATH/$f" ] && { echo "$f:"; sed 's/^/  /' "$CGPATH/$f"; }
  done
else
  # cgroup v1 (common in older distros)
  CGROOT=$(awk '$3 ~ /cgroup/ {print $2}' /proc/self/mounts | head -n1)
  # Try to read from typical controllers
  for ctrl in cpu cpuacct cpuset memory blkio; do
    path=$(awk -F: -v c="$ctrl" '$2==c {print $3}' "$cgfile")
    [ -z "$path" ] && continue
    CGPATH="$CGROOT/$ctrl$path"
    echo "cgroup v1 controller: $ctrl path: $CGPATH"
    case "$ctrl" in
      cpu)
        for f in cpu.cfs_quota_us cpu.cfs_period_us cpu.shares; do [ -f "$CGPATH/$f" ] && echo "  $f: $(cat "$CGPATH/$f")"; done;;
      cpuset)
        for f in cpuset.cpus cpuset.mems; do [ -f "$CGPATH/$f" ] && echo "  $f: $(cat "$CGPATH/$f")"; done;;
      memory)
        for f in memory.limit_in_bytes memory.soft_limit_in_bytes memory.memsw.limit_in_bytes; do [ -f "$CGPATH/$f" ] && echo "  $f: $(cat "$CGPATH/$f")"; done;;
      blkio)
        for f in blkio.throttle.read_bps_device blkio.throttle.write_bps_device blkio.throttle.read_iops_device blkio.throttle.write_iops_device; do
          [ -f "$CGPATH/$f" ] && { echo "  $f:"; sed 's/^/    /' "$CGPATH/$f"; }
        done;;
    esac
  done
fi

hdr "Process accounting (current values; will start at ~0 for a fresh process)"
[ -r "$SELF/io" ] && cat "$SELF/io"

hdr "System memory snapshot"
grep -E "Mem(Total|Free|Available)|Buffers|Cached|Swap(Total|Free)" /proc/meminfo

hdr "Block devices: scheduler & read-ahead (root fs device)"
rootdev=$(findmnt -n -o SOURCE / | sed 's|^/dev/||')
rootblk=$(lsblk -no PKNAME "/dev/$rootdev" 2>/dev/null || true)
[ -z "$rootblk" ] && rootblk="$rootdev"
sched="/sys/block/$rootblk/queue/scheduler"
ra="/sys/block/$rootblk/queue/read_ahead_kb"
[ -f "$sched" ] && echo "scheduler: $(cat "$sched")" || echo "scheduler: n/a"
[ -f "$ra" ]    && echo "read_ahead_kb: $(cat "$ra")"

hdr "Quick system I/O load (best effort)"
if command -v iostat >/dev/null; then
  echo "Running: iostat -xz 1 3"
  iostat -xz 1 3
else
  echo "iostat not installed; showing /proc/diskstats deltas over 1s"
  snap1=$(mktemp) snap2=$(mktemp)
  cat /proc/diskstats > "$snap1"
  sleep 1
  cat /proc/diskstats > "$snap2"
  echo "Device  rsectors_delta  wsectors_delta"
  awk 'NR==FNR{a[$3]=$6;b[$3]=$10;next}{if(a[$3]!=""&&b[$3]!=""){print $3, $6-a[$3], $10-b[$3]}}' "$snap1" "$snap2"
  rm -f "$snap1" "$snap2"
fi

hdr "Env knobs that can affect CPU threads"
for v in OMP_NUM_THREADS GOMP_CPU_AFFINITY OPENBLAS_NUM_THREADS MKL_NUM_THREADS NUMEXPR_NUM_THREADS; do
  [ -n "${!v-}" ] && echo "$v=${!v}"
done

echo
echo "Done. Use: ./print_env.sh <pid> to inspect an existing process instead of this shell."

