alias cualias='$EDITOR ~/my-cubrid/aliases.sh'
alias cuali='$EDITOR ~/my-cubrid/aliases.sh'
alias socuali='source ~/my-cubrid/aliases.sh'

alias cu_dir='cd $ISSUE_DIR'
alias cud='cu_dir'

alias cu_build='. ~/my-cubrid/build.sh'
alias cub='cu_build'

alias cu_rmdb='. ~/my-cubrid/remove-db.sh'

alias cu_createdb='. ~/my-cubrid/create-db.sh'

alias cu_prepare='. ~/my-cubrid/prepare.sh'
alias cu_prepare_edit='$EDITOR ~/my-cubrid/prepare.sh'
alias cup='cu_prepare'
alias cupe='cu_prepare_edit'

alias cu_run='. ~/my-cubrid/run.sh'
alias cu_run_edit='$EDITOR ~/my-cubrid/run.sh'
alias cur='cu_run'
alias cure='cu_run_edit'

alias cu_all='cub && cu_rmdb && cu_createdb && cup && cur'
alias cua='cu_all'

### trace
alias cu_trace='. ~/my-cubrid/trace.sh'
alias cut='cu_trace'
alias cu_trace_edit='$EDITOR ~/my-cubrid/trace.sh'
alias cu_tracee='cu_trace_edit'
alias cute='cu_trace_edit'

### trace dump
alias cu_trace_dump='uftrace dump'
alias cutd='cu_trace_dump'
alias cu_trace_dump_edit='$EDITOR ~/my-cubrid/trace-dump.sh'
alias cutde='cu_trace_dump_edit'
alias cu_trace_dump_flame='. ~/my-cubrid/trace-dump-flame-graph.sh'
alias cu_trace2html='trace2html uftrace-dump-chrome.json'
#alias cu_trace_serve='python3 ~/my-cubrid/serve_and_open.py'
alias cu_trace_dump_serve='open uftrace-dump-chrome.html'
alias cu_trace_dump_all='cu_trace_dump && cu_trace2html && cu_trace_dump_serve'

alias cu_trace_success='. ~/my-cubrid/trace-success.sh'
alias cu_trace_fail='. ~/my-cubrid/trace-fail.sh'
alias cu_trace_both='. ~/my-cubrid/trace-both.sh'

