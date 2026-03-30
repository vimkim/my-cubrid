#!/usr/bin/env bash
#
# check-server-for-rdbms.sh
# Linux server health check for optimal RDBMS (CUBRID) operation.
# Checks kernel parameters, resource limits, filesystem, CPU, memory, and network
# settings against recommended values for database workloads.
#
# Usage: sudo ./check-server-for-rdbms.sh
#        ./check-server-for-rdbms.sh          (some checks may be limited without root)
#
# Exit codes:
#   0 - All checks passed
#   1 - Warnings found (non-critical)
#   2 - Failures found (critical issues)

set -euo pipefail

# --- Colors and formatting ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

PASS=0
WARN=0
FAIL=0

pass()  { PASS=$(( PASS + 1 )); printf "  ${GREEN}[PASS]${NC} %s\n" "$1"; }
warn()  { WARN=$(( WARN + 1 )); printf "  ${YELLOW}[WARN]${NC} %s\n" "$1"; }
fail()  { FAIL=$(( FAIL + 1 )); printf "  ${RED}[FAIL]${NC} %s\n" "$1"; }
info()  { printf "  ${BLUE}[INFO]${NC} %s\n" "$1"; }
header(){ printf "\n${BOLD}=== %s ===${NC}\n" "$1"; }

read_sysctl() {
    local key="$1"
    local proc_path="/proc/sys/${key//./\/}"
    if [[ -f "$proc_path" ]]; then
        cat "$proc_path" 2>/dev/null
    else
        sysctl -n "$key" 2>/dev/null || echo "N/A"
    fi
}

# ============================================================
header "System Overview"
# ============================================================
info "Hostname: $(hostname)"
info "Kernel:   $(uname -r)"
info "Arch:     $(uname -m)"
info "Uptime:   $(uptime -p 2>/dev/null || uptime)"
info "Date:     $(date '+%Y-%m-%d %H:%M:%S %Z')"
if [[ -f /etc/os-release ]]; then
    info "OS:       $(. /etc/os-release && echo "${PRETTY_NAME:-$NAME}")"
fi

total_mem_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
total_mem_gb=$(awk "BEGIN {printf \"%.1f\", $total_mem_kb / 1048576}")
info "Memory:   ${total_mem_gb} GB"
info "CPUs:     $(nproc)"

# ============================================================
header "Memory & Swap"
# ============================================================

# -- vm.swappiness --
swappiness=$(read_sysctl vm.swappiness)
if [[ "$swappiness" != "N/A" ]]; then
    if (( swappiness <= 10 )); then
        pass "vm.swappiness = $swappiness (recommended: <= 10 for RDBMS)"
    elif (( swappiness <= 30 )); then
        warn "vm.swappiness = $swappiness (recommended: <= 10; current value may cause unnecessary swapping under memory pressure)"
    else
        fail "vm.swappiness = $swappiness (recommended: <= 10; high values degrade DB buffer pool performance)"
    fi
else
    warn "Could not read vm.swappiness"
fi

# -- Transparent Huge Pages --
for thp_path in /sys/kernel/mm/transparent_hugepage/enabled /sys/kernel/mm/redhat_transparent_hugepage/enabled; do
    if [[ -f "$thp_path" ]]; then
        thp_value=$(cat "$thp_path")
        # The active setting is shown in brackets: [always] madvise never
        if [[ "$thp_value" == *"[never]"* ]]; then
            pass "THP ($thp_path) = never"
        elif [[ "$thp_value" == *"[madvise]"* ]]; then
            warn "THP ($thp_path) = madvise (recommended: never for RDBMS; madvise is acceptable but 'never' avoids latency spikes)"
        else
            active_thp="${thp_value##*[}"; active_thp="${active_thp%%]*}"
            fail "THP ($thp_path) = $active_thp (recommended: never; THP causes unpredictable latency spikes in database workloads)"
        fi
        break
    fi
done

# -- THP defrag --
for defrag_path in /sys/kernel/mm/transparent_hugepage/defrag /sys/kernel/mm/redhat_transparent_hugepage/defrag; do
    if [[ -f "$defrag_path" ]]; then
        defrag_value=$(cat "$defrag_path")
        if [[ "$defrag_value" == *"[never]"* ]]; then
            pass "THP defrag = never"
        elif [[ "$defrag_value" == *"[defer+madvise]"* ]] || [[ "$defrag_value" == *"[madvise]"* ]]; then
            active_defrag="${defrag_value##*[}"; active_defrag="${active_defrag%%]*}"
            warn "THP defrag = $active_defrag (recommended: never)"
        else
            active_defrag="${defrag_value##*[}"; active_defrag="${active_defrag%%]*}"
            fail "THP defrag = $active_defrag (recommended: never; compaction stalls hurt DB latency)"
        fi
        break
    fi
done

# -- vm.overcommit_memory --
overcommit=$(read_sysctl vm.overcommit_memory)
if [[ "$overcommit" != "N/A" ]]; then
    if (( overcommit == 0 )); then
        pass "vm.overcommit_memory = $overcommit (heuristic overcommit — acceptable for most RDBMS)"
    elif (( overcommit == 2 )); then
        pass "vm.overcommit_memory = $overcommit (strict — prevents OOM, good for DB servers)"
    else
        warn "vm.overcommit_memory = $overcommit (value 1 = always overcommit; consider 0 or 2 for DB stability)"
    fi
fi

# -- vm.dirty_ratio / vm.dirty_background_ratio --
dirty_ratio=$(read_sysctl vm.dirty_ratio)
dirty_bg_ratio=$(read_sysctl vm.dirty_background_ratio)
if [[ "$dirty_ratio" != "N/A" ]]; then
    if (( dirty_ratio <= 15 )); then
        pass "vm.dirty_ratio = $dirty_ratio (recommended: <= 15 for consistent write latency)"
    elif (( dirty_ratio <= 30 )); then
        warn "vm.dirty_ratio = $dirty_ratio (recommended: <= 15; higher values can cause write stalls during flush)"
    else
        fail "vm.dirty_ratio = $dirty_ratio (too high; may cause long I/O stalls when dirty pages are flushed)"
    fi
fi
if [[ "$dirty_bg_ratio" != "N/A" ]]; then
    if (( dirty_bg_ratio <= 5 )); then
        pass "vm.dirty_background_ratio = $dirty_bg_ratio (recommended: <= 5)"
    elif (( dirty_bg_ratio <= 10 )); then
        warn "vm.dirty_background_ratio = $dirty_bg_ratio (recommended: <= 5 for smoother background writeback)"
    else
        fail "vm.dirty_background_ratio = $dirty_bg_ratio (too high; background flushing starts too late)"
    fi
fi

# -- vm.zone_reclaim_mode --
zone_reclaim=$(read_sysctl vm.zone_reclaim_mode)
if [[ "$zone_reclaim" != "N/A" ]]; then
    if (( zone_reclaim == 0 )); then
        pass "vm.zone_reclaim_mode = $zone_reclaim (recommended: 0 for NUMA systems — allows cross-node allocation)"
    else
        warn "vm.zone_reclaim_mode = $zone_reclaim (recommended: 0; non-zero may cause premature local reclaim on NUMA)"
    fi
fi

# -- Swap usage --
swap_total=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
swap_used=$(( swap_total - $(awk '/^SwapFree:/ {print $2}' /proc/meminfo) ))
if (( swap_total > 0 )); then
    swap_pct=$(( swap_used * 100 / swap_total ))
    if (( swap_pct == 0 )); then
        pass "Swap usage: 0% (no swap pressure)"
    elif (( swap_pct <= 10 )); then
        warn "Swap usage: ${swap_pct}% (some swap in use — investigate if unexpected)"
    else
        fail "Swap usage: ${swap_pct}% (significant swap activity degrades RDBMS performance)"
    fi
else
    info "No swap configured"
fi

# -- OOM score --
cubrid_pids=$(pgrep -f "cub_server" 2>/dev/null || true)
if [[ -n "${CUBRID:-}" ]] && [[ -n "$cubrid_pids" ]]; then
    for pid in $cubrid_pids; do
        oom_adj=$(cat "/proc/$pid/oom_score_adj" 2>/dev/null || echo "N/A")
        if [[ "$oom_adj" != "N/A" ]] && (( oom_adj <= -900 )); then
            pass "CUBRID server (pid $pid) oom_score_adj = $oom_adj (protected from OOM killer)"
        elif [[ "$oom_adj" != "N/A" ]]; then
            warn "CUBRID server (pid $pid) oom_score_adj = $oom_adj (consider setting to -1000 to protect from OOM killer)"
        fi
    done
else
    info "No running CUBRID server process detected (oom_score_adj check skipped)"
fi

# ============================================================
header "CPU & Scheduler"
# ============================================================

# -- CPU governor --
if [[ -d /sys/devices/system/cpu/cpu0/cpufreq ]]; then
    governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo "N/A")
    if [[ "$governor" == "performance" ]]; then
        pass "CPU governor = performance"
    else
        warn "CPU governor = $governor (recommended: performance for consistent DB throughput; 'powersave'/'ondemand' cause frequency scaling delays)"
    fi
else
    info "CPU frequency scaling not available (VM or fixed-frequency host)"
fi

# -- NUMA topology --
if command -v numactl &>/dev/null; then
    numa_nodes=$(numactl --hardware 2>/dev/null | grep "^available:" | awk '{print $2}')
    if [[ -n "$numa_nodes" ]] && (( numa_nodes > 1 )); then
        info "NUMA nodes: $numa_nodes (consider NUMA-aware CUBRID deployment: numactl --interleave=all)"
    else
        info "NUMA nodes: ${numa_nodes:-1} (single node — no special NUMA tuning needed)"
    fi
else
    info "numactl not installed (cannot check NUMA topology)"
fi

# -- kernel.sched_autogroup_enabled --
autogroup=$(read_sysctl kernel.sched_autogroup_enabled)
if [[ "$autogroup" != "N/A" ]]; then
    if (( autogroup == 0 )); then
        pass "kernel.sched_autogroup_enabled = 0 (good for server workloads)"
    else
        warn "kernel.sched_autogroup_enabled = 1 (designed for desktop; consider disabling on DB servers for fairer scheduling)"
    fi
fi

# ============================================================
header "I/O & Filesystem"
# ============================================================

# -- I/O scheduler --
checked_io=0
for bdev in /sys/block/sd* /sys/block/nvme* /sys/block/vd*; do
    [[ -d "$bdev" ]] || continue
    dev_name=$(basename "$bdev")
    sched_file="$bdev/queue/scheduler"
    if [[ -f "$sched_file" ]]; then
        sched=$(cat "$sched_file")
        active_sched="${sched##*[}"; active_sched="${active_sched%%]*}"
        rotational=$(cat "$bdev/queue/rotational" 2>/dev/null || echo "N/A")

        if [[ "$rotational" == "N/A" ]]; then
            info "$dev_name: Cannot determine disk type (rotational flag unavailable)"
        elif (( rotational == 0 )); then
            # SSD/NVMe
            if [[ "$active_sched" == "none" ]] || [[ "$active_sched" == "mq-deadline" ]] || [[ "$active_sched" == "kyber" ]]; then
                pass "$dev_name (SSD): I/O scheduler = $active_sched"
            else
                warn "$dev_name (SSD): I/O scheduler = $active_sched (recommended: none, mq-deadline, or kyber for SSD)"
            fi
        else
            # HDD
            if [[ "$active_sched" == "mq-deadline" ]] || [[ "$active_sched" == "deadline" ]] || [[ "$active_sched" == "bfq" ]]; then
                pass "$dev_name (HDD): I/O scheduler = $active_sched"
            else
                warn "$dev_name (HDD): I/O scheduler = $active_sched (recommended: mq-deadline or bfq for spinning disks)"
            fi
        fi # rotational check
        checked_io=1
    fi
done
if (( checked_io == 0 )); then
    info "No block devices with scheduler info found"
fi

# -- Mount options for CUBRID data directory --
if [[ -n "${CUBRID_DATABASES:-}" ]]; then
    cubrid_data="$CUBRID_DATABASES"
elif [[ -n "${CUBRID:-}" ]]; then
    cubrid_data="${CUBRID}/databases"
else
    cubrid_data=""
fi
if [[ -n "$cubrid_data" ]] && [[ -d "$cubrid_data" ]]; then
    mount_point=$(df "$cubrid_data" 2>/dev/null | tail -1 | awk '{print $NF}')
    mount_opts=$(findmnt -n -o OPTIONS "$mount_point" 2>/dev/null || echo "N/A")
    if [[ "$mount_opts" != "N/A" ]]; then
        info "CUBRID data mount ($mount_point): $mount_opts"
        if [[ "$mount_opts" == *"noatime"* ]] || [[ "$mount_opts" == *"relatime"* ]]; then
            pass "Mount has noatime/relatime (reduces unnecessary metadata writes)"
        else
            warn "Mount lacks noatime — consider adding 'noatime' to reduce I/O overhead"
        fi
        if [[ "$mount_opts" == *"nobarrier"* ]] || [[ "$mount_opts" == *"barrier=0"* ]]; then
            warn "Mount has barriers disabled — only safe with battery-backed write cache"
        fi
    fi

    fs_type=$(findmnt -n -o FSTYPE "$mount_point" 2>/dev/null || echo "N/A")
    if [[ "$fs_type" != "N/A" ]]; then
        if [[ "$fs_type" == "ext4" ]] || [[ "$fs_type" == "xfs" ]]; then
            pass "Filesystem type: $fs_type (recommended for RDBMS)"
        else
            warn "Filesystem type: $fs_type (ext4 or xfs recommended for RDBMS workloads)"
        fi
    fi
else
    info "CUBRID data directory not found (\$CUBRID_DATABASES / \$CUBRID not set); skipping mount checks"
fi

# -- vm.dirty_expire_centisecs --
dirty_expire=$(read_sysctl vm.dirty_expire_centisecs)
if [[ "$dirty_expire" != "N/A" ]]; then
    if (( dirty_expire <= 3000 )); then
        expire_ms=$(( dirty_expire * 10 ))
        pass "vm.dirty_expire_centisecs = $dirty_expire (pages expire within ${expire_ms} ms)"
    else
        warn "vm.dirty_expire_centisecs = $dirty_expire (recommended: <= 3000; stale dirty pages increase crash-recovery data loss window)"
    fi
fi

# -- vm.min_free_kbytes --
min_free=$(read_sysctl vm.min_free_kbytes)
if [[ "$min_free" != "N/A" ]]; then
    # For large-memory DB servers, min_free_kbytes should be at least 65536 (64 MB)
    if (( min_free >= 65536 )); then
        pass "vm.min_free_kbytes = $min_free (>= 65536; sufficient free memory watermark)"
    elif (( min_free >= 32768 )); then
        warn "vm.min_free_kbytes = $min_free (recommended: >= 65536 for large-memory DB servers to avoid allocation stalls)"
    else
        warn "vm.min_free_kbytes = $min_free (low; may cause allocation stalls under memory pressure)"
    fi
fi

# -- fs.file-max --
file_max=$(read_sysctl fs.file-max)
if [[ "$file_max" != "N/A" ]]; then
    if (( file_max >= 1000000 )); then
        pass "fs.file-max = $file_max (system-wide file descriptor limit sufficient)"
    else
        warn "fs.file-max = $file_max (recommended: >= 1000000 for production DB servers)"
    fi
fi

# ============================================================
header "Resource Limits (ulimit)"
# ============================================================

# -- Open files --
nofile_soft=$(ulimit -Sn 2>/dev/null || echo "N/A")
nofile_hard=$(ulimit -Hn 2>/dev/null || echo "N/A")
if [[ "$nofile_soft" != "N/A" ]]; then
    if [[ "$nofile_soft" == "unlimited" ]] || (( nofile_soft >= 65536 )); then
        pass "Open files (soft) = $nofile_soft (>= 65536)"
    elif (( nofile_soft >= 8192 )); then
        warn "Open files (soft) = $nofile_soft (recommended: >= 65536 for production DB)"
    else
        fail "Open files (soft) = $nofile_soft (too low for RDBMS; many connections will exhaust file descriptors)"
    fi
fi
info "Open files (hard) = $nofile_hard"

# -- Max user processes --
nproc_soft=$(ulimit -Su 2>/dev/null || echo "N/A")
if [[ "$nproc_soft" != "N/A" ]]; then
    if [[ "$nproc_soft" == "unlimited" ]] || (( nproc_soft >= 65536 )); then
        pass "Max user processes (soft) = $nproc_soft"
    elif (( nproc_soft >= 4096 )); then
        warn "Max user processes (soft) = $nproc_soft (recommended: >= 65536)"
    else
        fail "Max user processes (soft) = $nproc_soft (too low; may limit CUBRID thread/process creation)"
    fi
fi

# -- Core dump size --
core_soft=$(ulimit -Sc 2>/dev/null || echo "N/A")
if [[ "$core_soft" != "N/A" ]]; then
    if [[ "$core_soft" == "unlimited" ]]; then
        pass "Core dump size = unlimited (core files available for crash diagnosis)"
    elif (( core_soft == 0 )); then
        warn "Core dump size = 0 (core dumps disabled; consider enabling for post-mortem debugging)"
    else
        info "Core dump size = $core_soft"
    fi
fi

# ============================================================
header "Shared Memory & Semaphores (IPC)"
# ============================================================

shmmax=$(read_sysctl kernel.shmmax)
if [[ "$shmmax" != "N/A" ]]; then
    shmmax_gb=$(awk "BEGIN {printf \"%.2f\", $shmmax / 1073741824}")
    # shmmax should be at least half of total RAM
    half_mem=$(( total_mem_kb * 1024 / 2 ))
    if (( shmmax >= half_mem )); then
        pass "kernel.shmmax = $shmmax ($shmmax_gb GB) — sufficient"
    else
        warn "kernel.shmmax = $shmmax ($shmmax_gb GB) — recommended: >= half of RAM ($(awk "BEGIN {printf \"%.1f\", $half_mem / 1073741824}") GB)"
    fi
fi

shmall=$(read_sysctl kernel.shmall)
if [[ "$shmall" != "N/A" ]]; then
    page_size=$(getconf PAGE_SIZE 2>/dev/null || echo 4096)
    shmall_bytes=$(( shmall * page_size ))
    shmall_gb=$(awk "BEGIN {printf \"%.2f\", $shmall_bytes / 1073741824}")
    info "kernel.shmall = $shmall (${shmall_gb} GB in pages of $page_size bytes)"
fi

sem_values=$(read_sysctl kernel.sem)
if [[ "$sem_values" != "N/A" ]]; then
    info "kernel.sem = $sem_values (SEMMSL SEMMNS SEMOPM SEMMNI)"
fi

# ============================================================
header "Network"
# ============================================================

somaxconn=$(read_sysctl net.core.somaxconn)
if [[ "$somaxconn" != "N/A" ]]; then
    if (( somaxconn >= 4096 )); then
        pass "net.core.somaxconn = $somaxconn (>= 4096)"
    elif (( somaxconn >= 1024 )); then
        warn "net.core.somaxconn = $somaxconn (recommended: >= 4096 for high-connection DB workloads)"
    else
        fail "net.core.somaxconn = $somaxconn (too low; may cause connection refusals under load)"
    fi
fi

tcp_tw_reuse=$(read_sysctl net.ipv4.tcp_tw_reuse)
if [[ "$tcp_tw_reuse" != "N/A" ]]; then
    if (( tcp_tw_reuse == 1 )); then
        pass "net.ipv4.tcp_tw_reuse = 1 (TIME_WAIT socket reuse enabled)"
    else
        info "net.ipv4.tcp_tw_reuse = $tcp_tw_reuse (consider enabling for high connection churn)"
    fi
fi

tcp_keepalive=$(read_sysctl net.ipv4.tcp_keepalive_time)
if [[ "$tcp_keepalive" != "N/A" ]]; then
    if (( tcp_keepalive <= 600 )); then
        pass "net.ipv4.tcp_keepalive_time = $tcp_keepalive seconds"
    else
        warn "net.ipv4.tcp_keepalive_time = $tcp_keepalive seconds (recommended: <= 600 to detect dead connections faster)"
    fi
fi

tcp_fin_timeout=$(read_sysctl net.ipv4.tcp_fin_timeout)
if [[ "$tcp_fin_timeout" != "N/A" ]]; then
    if (( tcp_fin_timeout <= 30 )); then
        pass "net.ipv4.tcp_fin_timeout = $tcp_fin_timeout seconds"
    else
        warn "net.ipv4.tcp_fin_timeout = $tcp_fin_timeout seconds (recommended: <= 30 to free up sockets faster)"
    fi
fi

# ============================================================
header "Security & Miscellaneous"
# ============================================================

# -- ASLR --
aslr=$(read_sysctl kernel.randomize_va_space)
if [[ "$aslr" != "N/A" ]]; then
    if (( aslr == 2 )); then
        pass "ASLR = $aslr (full randomization — secure default)"
    else
        warn "ASLR = $aslr (recommended: 2 for full address space randomization)"
    fi
fi

# -- SELinux --
if command -v getenforce &>/dev/null; then
    se_status=$(getenforce 2>/dev/null || echo "N/A")
    info "SELinux: $se_status"
    if [[ "$se_status" == "Enforcing" ]]; then
        info "SELinux is enforcing — ensure CUBRID ports/paths have proper policies"
    fi
fi

# -- Firewall --
if command -v firewall-cmd &>/dev/null; then
    fw_state=$(firewall-cmd --state 2>/dev/null || echo "not running")
    info "firewalld: $fw_state"
elif command -v ufw &>/dev/null; then
    fw_state=$(ufw status 2>/dev/null | head -1 || echo "N/A")
    info "ufw: $fw_state"
else
    info "No recognized firewall tool detected"
fi

# -- NTP / time sync --
if command -v timedatectl &>/dev/null; then
    ntp_status=$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo "N/A")
    if [[ "$ntp_status" == "yes" ]]; then
        pass "NTP synchronized: yes"
    elif [[ "$ntp_status" == "no" ]]; then
        warn "NTP synchronized: no (time drift can cause replication issues and log confusion)"
    else
        info "NTP sync status: $ntp_status"
    fi
fi

# ============================================================
header "Summary"
# ============================================================
printf "\n"
printf "  ${GREEN}PASS: %d${NC}  ${YELLOW}WARN: %d${NC}  ${RED}FAIL: %d${NC}\n" "$PASS" "$WARN" "$FAIL"
printf "\n"

if (( FAIL > 0 )); then
    printf "  ${RED}${BOLD}Action required:${NC} %d critical issue(s) found. Fix FAIL items before production use.\n" "$FAIL"
    exit 2
elif (( WARN > 0 )); then
    printf "  ${YELLOW}${BOLD}Mostly good:${NC} %d warning(s). Review WARN items for optimal performance.\n" "$WARN"
    exit 1
else
    printf "  ${GREEN}${BOLD}All checks passed.${NC} Server is well-tuned for RDBMS workloads.\n"
    exit 0
fi
