
# Generate a timestamp
timestamp=$(date +"%Y-%m-%d_%H-%M-%S")

cu_trace_success

uftrace dump --chrome > dump-success-chrome-$timestamp.json

cu_trace_fail

uftrace dump --chrome > dump-fail-chrome-$timestamp.json
