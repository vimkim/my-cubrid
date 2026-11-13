#!/usr/bin/env python3
"""Usage: summarize.py <suite.qls> <analyze.log> <results.sarif>

Prints one TSV row per query in the suite: id, eval seconds, hits, query path.
A query with no 'Evaluation done' line gets eval '-' (it timed out or never ran).
Rows are sorted by eval time, slowest first."""
import json, os, re, subprocess, sys
from collections import Counter

suite, log, sarif = sys.argv[1:4]
codeql = os.environ.get("CODEQL", "codeql")

paths = json.loads(subprocess.run([codeql, "resolve", "queries", "--format=json", suite],
                                  check=True, capture_output=True, text=True).stdout)
def query_id(path):
    m = re.search(r"@id\s+(\S+)", open(path, encoding="utf-8").read())
    return m.group(1) if m else "?"
by_rel = {}
for p in paths:
    rel = p.split("/cpp-queries/", 1)[1].split("/", 1)[1]
    by_rel[rel[:-3]] = (query_id(p), rel)

def seconds(s):
    total = 0.0
    for num, unit in re.findall(r"([\d.]+)(ms|h|m|s)", s):
        total += float(num) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    return total

evals = {}
for line in open(log, encoding="utf-8", errors="replace"):
    m = re.search(r"\[\d+/\d+ eval ([^\]]+)\] Evaluation done; writing results to codeql/cpp-queries/(.+)\.bqrs", line)
    if m:
        evals[m.group(2)] = seconds(m.group(1))

hits = Counter()
if os.path.exists(sarif):
    for run in json.load(open(sarif, encoding="utf-8"))["runs"]:
        for r in run.get("results", []):
            hits[r.get("ruleId") or r.get("rule", {}).get("id")] += 1

rows = []
for key, (qid, rel) in by_rel.items():
    rows.append((evals.get(key), qid, hits.get(qid, 0), rel))
rows.sort(key=lambda r: float('inf') if r[0] is None else r[0], reverse=True)
print("id\teval_s\thits\tquery")
for ev, qid, n, rel in rows:
    print(f"{qid}\t{'-' if ev is None else f'{ev:.1f}'}\t{n}\t{rel}")
print(f"total\t{sum(r[0] or 0 for r in rows):.1f}\t{sum(r[2] for r in rows)}\t{len(rows)} queries, {sum(r[0] is None for r in rows)} without eval", file=sys.stderr)
