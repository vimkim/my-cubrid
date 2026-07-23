set minimum-version := "1.55.0"
set no-cd
set shell := ["sh", "-cu"]

# Dump the current uftrace data as a Perfetto-compatible JSON trace.
[working-directory(justfile_directory())]
uftrace-dump-chrome:
    uftrace dump --chrome >"uftrace/uftrace-chrome-$(date '+%Y%m%d_%H%M%S').json"

# Dump the current uftrace data as folded stacks.
[working-directory(justfile_directory())]
uftrace-dump-flamegraph:
    uftrace dump --flame-graph --sample-time=1us >"uftrace/uftrace-flame-$(date '+%Y%m%d_%H%M%S').log"

# Preview the current uftrace data as a flame graph.
[working-directory(justfile_directory())]
uftrace-preview:
    uftrace dump --flame-graph --sample-time=1us | flamelens

# Serve generated trace JSON through trace_processor.
[working-directory(justfile_directory())]
uftrace-serve:
    trace_processor --httpd ./uftrace/uftrace-chrome-*.json

# Record system-wide samples for a selected cub_server.
[working-directory(justfile_directory())]
perf-record-server:
    sudo perf record -F max -g -a -p "$(ps aux | rg vimkim | rg cub_server | fzf | awk '{print $2}')"

# Open the current perf recording.
[working-directory(justfile_directory())]
perf-report:
    sudo perf report -M intel

# Preview the current perf recording as a flame graph.
[working-directory(justfile_directory())]
perf-flamegraph:
    sudo perf script | inferno-collapse-perf | flamelens

# Check whether the installed cosine metric contains native AVX instructions.
[working-directory(justfile_directory())]
check-simd-native:
    objdump -d "$CUBRID/lib/libcubrid.so" | rg metric_cos_gt -A 5 | rg ymm | wc -l
