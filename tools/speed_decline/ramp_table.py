"""The first windows of an answer against the settled ones, from the engine's `strata decode ramp` lines.

    python ramp_table.py <first log line> [<last log line>]

Needs STRATA_DECODE_TIMING=1 and STRATA_WIN_RAMP=1 in the engine's environment.  Every request's ramp line gives, for
the windows 1-5, 6-10, 11-20, 21-40, 41-80, 81-160, 161-320 and the rest: ms per window, tokens per window, the
GPU-reach wait, the jobs stage (fetching the experts that are not in VRAM), the CPU pool and the CPU experts per
layer-window.  The table averages them over the requests (weighted by windows), apart for requests that read a new
piece of the prompt first (1,000 tokens or more), requests that read almost nothing (under 40) and requests that
generated at most 320 tokens."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
log = (ROOT / "strata-ud-q4_k_xl.log").read_bytes().replace(b"\x00", b"").decode("utf-8", "replace").split("\n")
a = int(sys.argv[1]); b = int(sys.argv[2]) if len(sys.argv) > 2 else len(log)
grp = re.compile(r" (\d+)-(\d+): ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+);")
rq = re.compile(r"strata serve: prompt (\d+) tokens = (\d+) reused \+ (\d+)(?: of \d+)? read in (\d+) ms \([\d.]+ tok/s\), (\d+) generated in (\d+) ms")
EDGES = [5, 10, 20, 40, 80, 160, 320]
def bucket(lo, hi):
    for e0, e1 in zip([0] + EDGES, EDGES):
        if lo == e0 + 1 and hi <= e1: return "%d-%d" % (e0 + 1, e1)
    return "over 320" if lo > 320 else None
ORDER = ["1-5", "6-10", "11-20", "21-40", "41-80", "81-160", "161-320", "over 320"]

reqs = []; ramp = None
for l in log[a - 1:b]:
    if l.startswith("strata decode ramp"):
        ramp = [(int(g[0]), int(g[1])) + tuple(float(x) for x in g[2:]) for g in grp.findall(l)]; continue
    m = rq.search(l)
    if m and ramp:
        reqs.append(dict(read=int(m.group(3)), gen=int(m.group(5)), gms=int(m.group(6)), ramp=ramp)); ramp = None

def table(name, sel):
    if not sel: return
    gen = sum(r["gen"] for r in sel); ms = sum(r["gms"] for r in sel)
    print("%s: %d requests, %.1f tok/s" % (name, len(sel), 1000.0 * gen / ms))
    print("  windows  | requests | ms/window | tokens/window | tok/s | wait | jobs | CPU  | CPU experts per layer-window")
    for key in ORDER:
        acc = [0.0] * 7; n = 0
        for r in sel:
            for lo, hi, msw, tpw, wait, jobs, cpu, miss in r["ramp"]:
                if bucket(lo, hi) != key: continue
                w = hi - lo + 1
                for i, v in enumerate((msw, tpw, wait, jobs, cpu, miss)): acc[i] += v * w
                acc[6] += w; n += 1
        if not n: continue
        W = acc[6]; msw, tpw = acc[0] / W, acc[1] / W
        print("  %-8s | %8d | %9.1f | %13.2f | %5.1f | %4.1f | %4.1f | %4.1f | %.2f" % (key, n, msw, tpw, 1000.0 * tpw / msw, acc[2] / W, acc[3] / W, acc[4] / W, acc[5] / W))
    print()

print("%d requests with a ramp line" % len(reqs))
warm = [r for r in reqs if r["read"] < 20000 and r["gen"] >= 20]      # not the cold read of a whole conversation, not a 4-token helper
table("after a read of 1,000 tokens or more", [r for r in warm if r["read"] >= 1000])
table("after a read of under 40 tokens", [r for r in warm if r["read"] < 40])
table("answers of at most 320 tokens (any read)", [r for r in warm if r["gen"] <= 320])
table("the cold read of a whole conversation", [r for r in reqs if r["read"] >= 20000])
