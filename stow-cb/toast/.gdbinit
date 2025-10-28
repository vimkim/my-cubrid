# config
# set detach-on-fork off
set breakpoint pending on
# set follow-fork-mode parent

b main
run
# catch fork
# catch vfork
b start_csql
continue
