#!/usr/bin/env python3
"""Extract unique -Wformat* diagnostics from a CUBRID GCC build log, map each to its call site, classify it.

usage: fmtwarn.py BUILD_LOG WORKTREE > warnings.tsv   (summary on stderr)

site     = where the format string is written ("format string is defined here"), else the
           outermost macro expansion, else the diagnostic location.
category = width     both sides are integers of the same size on LP64 (long vs long long): prints correctly
           real      size or kind differs (int vs 64-bit, pointer vs integer, %s vs non-string),
                     too many or too few arguments
           nonliteral non-literal format with no arguments (-Wformat-security): misprints if it holds '%'
           empty     zero-length format string
"""
import collections
import re
import sys

ansi = re.compile(r"\x1b\[[0-9;]*[mK]")
loc = r"(?P<file>[^:\s]+):(?P<line>\d+):(?P<col>\d+): "
diag = re.compile("^" + loc + r"(?P<kind>warning|error): (?P<msg>.*) \[(?P<flag>-W[^\]]*format[^\]]*)\]$")
any_diag = re.compile("^" + loc + r"(?:warning|error): ")
expand = re.compile("^" + loc + r"note: in expansion of macro ‘(?P<macro>[^’]+)’")
fmtdef = re.compile("^" + loc + r"note: format string is defined here")
types = re.compile(r"format ‘(?P<spec>[^’]*)’ expects argument of type ‘(?P<exp>[^’]*)’, but argument \d+ has type ‘(?P<act>[^’]*)’(?: \{aka ‘(?P<aka>[^’]*)’\})?")

INT = {"char": 1, "signed char": 1, "unsigned char": 1, "short int": 2, "short unsigned int": 2,
       "int": 4, "unsigned int": 4, "long int": 8, "long unsigned int": 8,
       "long long int": 8, "long long unsigned int": 8, "bool": 1}


def int_size(t):
    t = t.replace("const ", "").strip()
    return INT.get(t)


def classify(flag, msg):
    if "format-security" in flag:
        return "nonliteral"
    if "zero-length" in flag:
        return "empty"
    m = types.search(msg)
    if m:
        exp, act = m["exp"], m["aka"] or m["act"]
        se, sa = int_size(exp), int_size(act)
        if se and sa and se == sa:
            return "width"
    return "real"


root = sys.argv[2].rstrip("/") + "/"
rel = lambda f: f[len(root):] if f.startswith(root) else f

records, cur = [], None
for raw in open(sys.argv[1], errors="replace"):
    s = ansi.sub("", raw.rstrip("\n"))
    m = diag.match(s)
    if m:
        cur = {"diag": (rel(m["file"]), int(m["line"])), "flag": m["flag"], "msg": m["msg"], "macro": None, "fmt": None}
        records.append(cur)
        continue
    if any_diag.match(s):
        cur = None
        continue
    if cur is None:
        continue
    if (e := expand.match(s)):
        cur["macro"] = (rel(e["file"]), int(e["line"]), e["macro"])
    elif (f := fmtdef.match(s)):
        cur["fmt"] = (rel(f["file"]), int(f["line"]))

uniq = {}
for r in records:
    site = r["fmt"] or (r["macro"][:2] if r["macro"] else r["diag"])
    key = (site, r["msg"])
    uniq.setdefault(key, (r["flag"], r["macro"][2] if r["macro"] else "", classify(r["flag"], r["msg"])))

print("file\tline\tcategory\tflag\tmacro\tmessage")
rows = sorted(uniq.items())
for ((f, line), msg), (flag, macro, cat) in rows:
    print(f"{f}\t{line}\t{cat}\t{flag}\t{macro}\t{msg}")

cats = collections.Counter(v[2] for v in uniq.values())
files = collections.defaultdict(collections.Counter)
for ((f, _), _), (_, _, cat) in rows:
    files[f][cat] += 1
lines = {(k[0], c) for k, (_, _, c) in uniq.items()}
print(f"unique diagnostics: {len(rows)}  sites(line,category): {len(lines)}", file=sys.stderr)
print("by category: " + ", ".join(f"{c}={n}" for c, n in cats.most_common()), file=sys.stderr)
for f, c in sorted(files.items(), key=lambda kv: -sum(kv[1].values())):
    print(f"  {sum(c.values()):4d} {f}  " + " ".join(f"{k}={v}" for k, v in sorted(c.items())), file=sys.stderr)
