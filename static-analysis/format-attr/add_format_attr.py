#!/usr/bin/env python3
"""Add __attribute__ ((format (printf, F, A))) to printf-style logging prototypes.

usage: add_format_attr.py WORKTREE     (idempotent)
"""
import re
import sys

# (file, function, format index, first vararg index)
TABLE = [
    ("src/base/error_manager.h", "_er_log_debug", 3, 4),
    ("src/base/error_manager.h", "er_print_callstack", 3, 4),
    ("src/base/error_manager.c", "er_emergency", 3, 4),
    ("src/broker/cas_log.h", "cas_log_write_nonl", 3, 4),
    ("src/broker/cas_log.h", "cas_log_write_nonl_noflush", 3, 4),
    ("src/broker/cas_log.h", "cas_log_write", 3, 4),
    ("src/broker/cas_log.h", "cas_log_write_and_end", 3, 4),
    ("src/broker/cas_log.h", "cas_log_write2_nonl_noflush", 1, 2),
    ("src/broker/cas_log.h", "cas_log_write2", 1, 2),
    ("src/broker/cas_log.h", "cas_log_open_and_write", 4, 5),
    ("src/broker/cas_log.h", "cas_slow_log_write", 4, 5),
    ("src/broker/cas_log.h", "cas_slow_log_write_and_end", 3, 4),
    ("src/broker/cas_log.h", "cas_slow_log_write2", 1, 2),
    ("src/broker/cas_log.c", "cas_fprintf", 2, 3),
    ("src/broker/cas_sql_log2.h", "sql_log2_write", 1, 2),
    ("src/broker/shard_proxy_log.h", "proxy_log_write", 3, 4),
    ("src/base/util_func.h", "util_log_write_errstr", 1, 2),
    ("src/base/util_func.h", "util_log_write_warnstr", 1, 2),
    ("src/cm_common/cm_dep.h", "cm_util_log_write_errstr", 1, 2),
    ("src/base/ddl_log.h", "logddl_set_msg", 1, 2),
    ("src/base/ddl_log.h", "logddl_write_tran_str", 1, 2),
    ("src/base/ddl_log.h", "logddl_write_end_for_csql_fileinput", 1, 2),
    ("src/executables/master_heartbeat.h", "hb_disable_er_log", 2, 3),
    ("src/executables/unload_object.c", "unload_log_write", 2, 3),
    ("src/loaddb/load_sa_loader.hpp", "print_log_msg", 2, 3),
    ("src/transaction/log_comm.h", "log_dump_log_info", 3, 4),
    ("src/transaction/log_impl.h", "logpb_fatal_error", 5, 6),
    ("src/transaction/log_impl.h", "logpb_fatal_error_exit_immediately_wo_flush", 4, 5),
]

if __name__ == "__main__":
    root = sys.argv[1].rstrip("/") + "/"
    for path, func, f, a in TABLE:
        src = open(root + path).read()
        attr = f"__attribute__ ((format (printf, {f}, {a})))"
        # a prototype: "func (" ... "...)" then ";" (no body); may span lines
        proto = re.compile(r"(?m)^(?P<head>[^\n;{}]*\b" + re.escape(func) + r" \((?:[^;{}()]|\([^()]*\))*\.\.\.\))(?P<tail>[^;{]*);")
        hits = list(proto.finditer(src))
        if len(hits) != 1:
            sys.exit(f"{path}: {func}: expected 1 prototype, found {len(hits)}")
        m = hits[0]
        if "format (printf" in m["tail"]:
            continue
        last_line = m["head"].rsplit("\n", 1)[-1]
        indent = re.match(r"\s*", m["head"].split("\n", 1)[0])[0]
        if len(last_line.expandtabs(8)) + 1 + len(attr) + 1 <= 120:
            new = f"{m['head']} {attr};"
        else:
            new = f"{m['head']}\n{indent}  {attr};"
        src = src[: m.start()] + new + src[m.end():]
        open(root + path, "w").write(src)
        print(f"{path}: {func}")
