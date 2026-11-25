"""Why short answers decode slower: per-request decode timing against the number of windows in the request.

    python short_answers.py <first log line> <last log line> [<first> <last> ...]

For every request in the given line ranges of the engine log (needs STRATA_DECODE_TIMING=1) it takes the
`strata decode timing:` line and the `strata decode GPU stages (ms/window)` line, then
  1. prints the averages by answer length (windows-weighted);
  2. fits  ms/window = a + C / windows  over the requests: C is a cost paid once per request (ms), a the steady cost
     of a window; the same fit for the GPU-reach wait alone and for tokens per window;
  3. prints the GPU stages whose ms/window differ most between the short and the long answers."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
log = (ROOT / "strata-ud-q4_k_xl.log").read_bytes().replace(b"\x00", b"").decode("utf-8", "replace").split("\n")
tm = re.compile(r"strata decode timing: (\d+) windows, avg T ([\d.]+), ([\d.]+) tokens/window, ([\d.]+) ms/window = verify ([\d.]+) "
                r"\(GPU-reach wait ([\d.]+) \+ per-layer host ([\d.]+) \[plan [\d.]+ actq [\d.]+ jobs ([\d.]+) CPU ([\d.]+)\] \+ stage [\d.]+\) "
                r"\+ commit/emit ([\d.]+) \+ draft ([\d.]+).*adapt wait ([\d.]+)")
rq = re.compile(r"strata serve: prompt (\d+) tokens = (\d+) reused \+ (\d+)(?: of \d+)? read in (\d+) ms \([\d.]+ tok/s\), (\d+) generated in (\d+) ms.*?drafts accepted (\d+) of (\d+)")
st = re.compile(r"([A-Za-z0-9+/\-\. ]+?) (\d+\.\d+)(?=\s|$)")
kv = re.compile(r"KV streaming: ([\d.]+)% of (\d+) block reads hit VRAM, ([\d.]+) MiB read from RAM")

rows = []
args = [int(x) for x in sys.argv[1:]]
for a, b in zip(args[0::2], args[1::2]):
    t = None; stages = None; pkv = None
    for l in log[a - 1:b]:
        m = tm.search(l)
        if m:
            g = [float(x) for x in m.groups()]
            t = dict(win=g[0], T=g[1], tpw=g[2], msw=g[3], verify=g[4], wait=g[5], host=g[6], jobs=g[7], cpu=g[8], draft=g[10], adaptw=g[11]); continue
        if l.startswith("strata decode GPU stages"):
            stages = {}
            for sec in l.split(":", 1)[1].split("|"):
                name = sec.split(":", 1)[0].strip().split(" ")[-2] if ":" in sec else "?"
                body = sec.split(":", 1)[1] if ":" in sec else sec
                for k, v in st.findall(body):
                    stages[name + " " + " ".join(k.split())] = float(v)
            continue
        m = kv.search(l)
        if m:
            cur_kv = float(m.group(3))
            if rows and "kv" not in rows[-1]:
                rows[-1]["kv"] = cur_kv - (pkv or 0.0)
            pkv = cur_kv; continue
        m = rq.search(l)
        if m and t:
            r = dict(t, read=int(m.group(3)), gen=int(m.group(5)), gms=int(m.group(6)), da=int(m.group(7)), dn=int(m.group(8)), stages=stages or {})
            if r["gen"] >= 20 and r["read"] < 20000:        # not the cold read of a whole conversation, not a 4-token helper
                rows.append(r)
            t = None; stages = None
print("%d requests" % len(rows))

def avg(sel, k):
    W = sum(r["win"] for r in sel)
    return sum(r[k] * r["win"] for r in sel) / W

print("answer        | n   | windows | tok/s | tok/win | drafts ok | ms/win | wait  | CPU   | jobs | draft | rest")
for lo, hi, name in [(20, 150, "up to 150"), (151, 320, "151-320"), (321, 700, "321-700"), (701, 99999, "over 700")]:
    sel = [r for r in rows if lo <= r["gen"] <= hi]
    if not sel:
        continue
    msw = avg(sel, "msw")
    rest = msw - avg(sel, "wait") - avg(sel, "cpu") - avg(sel, "jobs") - avg(sel, "draft")
    print("%-13s | %3d | %7.0f | %5.1f | %7.2f | %8.0f%% | %6.1f | %5.1f | %5.1f | %4.1f | %5.2f | %4.1f" % (
        name, len(sel), sum(r["win"] for r in sel) / len(sel), 1000 * sum(r["gen"] for r in sel) / sum(r["gms"] for r in sel),
        avg(sel, "tpw"), 100.0 * sum(r["da"] for r in sel) / max(1, sum(r["dn"] for r in sel)), msw, avg(sel, "wait"), avg(sel, "cpu"),
        avg(sel, "jobs"), avg(sel, "draft"), rest))

def fit(key):
    # weighted least squares of  y = a + C * (1 / windows),  weights = windows
    xs = [1.0 / r["win"] for r in rows]; ys = [r[key] for r in rows]; ws = [r["win"] for r in rows]
    W = sum(ws); mx = sum(x * w for x, w in zip(xs, ws)) / W; my = sum(y * w for y, w in zip(ys, ws)) / W
    sxx = sum(w * (x - mx) ** 2 for x, w in zip(xs, ws)); sxy = sum(w * (x - mx) * (y - my) for x, y, w in zip(xs, ys, ws))
    syy = sum(w * (y - my) ** 2 for y, w in zip(ys, ws))
    C = sxy / sxx; a = my - C * mx
    return a, C, (sxy * sxy / (sxx * syy) if syy > 0 else 0.0)

print()
for key, what in [("msw", "ms/window"), ("wait", "GPU-reach wait"), ("cpu", "CPU"), ("jobs", "jobs"), ("draft", "draft"), ("tpw", "tokens/window")]:
    a, C, r2 = fit(key)
    print("%-15s = %6.2f + %8.1f / windows   (R^2 %.2f)" % (what, a, C, r2))

short = [r for r in rows if r["gen"] <= 320 and r["stages"]]; long_ = [r for r in rows if r["gen"] > 700 and r["stages"]]
if short and long_:
    keys = set(short[0]["stages"]) & set(long_[0]["stages"])
    def sa(sel, k):
        ok = [r for r in sel if k in r["stages"]]
        return sum(r["stages"][k] * r["win"] for r in ok) / max(1.0, sum(r["win"] for r in ok))
    d = sorted(((sa(short, k) - sa(long_, k), k, sa(short, k), sa(long_, k)) for k in keys), reverse=True)
    print("\nGPU stages, ms/window: short (up to 320 tokens) against long (over 700), the largest differences")
    for diff, k, s, lg in d[:9]:
        print("  %-34s short %5.2f  long %5.2f  %+5.2f" % (k, s, lg, diff))
    print("  ... sum over all %d stages: short %.2f, long %.2f" % (len(keys), sum(x[2] for x in d), sum(x[3] for x in d)))
