set pagination off
set confirm off

set logging off
set logging file gdb.cub_server.log
set logging overwrite on
set logging on

set inferior-tty /dev/null

delete breakpoints

# rbreak spage_.*
# b spage_insert
# b spage_get_record
# b spage_delete
# b spage_update
# b spage_update_record_in_place
python
import gdb
cmds = "silent\nprintf \"\\n--- hit bp %d ---\\n\", $bpnum\nbt\ncontinue\n"
for bp in gdb.breakpoints() or []:
    # Skip internal/disabled if you want:
    # if not bp.enabled: continue
    bp.commands = cmds
end

# break /home/vimkim/gh/cb/oos-update/src/connection/server_support.c:427
# b spage_update_record_in_place
# b spage_update
b heap_midxkey_get_value
