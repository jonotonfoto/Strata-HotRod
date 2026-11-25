"""Per-phase summary of a hermes_sim run, from the engine log (the last engine start) and sim-<label>.json."""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]   # the repository root
HERE = Path(__file__).parent
label = sys.argv[1]
steps = [s for s in json.loads((HERE / ("sim-%s.json" % label)).read_text(encoding="utf-8"))]
log = (ROOT / "strata-ud-q4_k_xl.log").read_bytes().replace(b"\x00", b"").decode("utf-8", "replace").split("\n")
starts = [i for i, l in enumerate(log) if "engine started" in l]
# the run's engine start: the last one, or the log line given as the second argument (for an earlier run)
st = int(sys.argv[2]) - 1 if len(sys.argv) > 2 else starts[-1]
log = log[:min([i for i in starts if i > st] or [len(log)])]
rq = re.compile(r"strata serve: prompt (\d+) tokens = (\d+) reused \+ (\d+)(?: of \d+)? read in (\d+) ms \([\d.]+ tok/s\), (\d+) generated in (\d+) ms")
ht = re.compile(r"decode expert cache hit rate: ([\d.]+)%")
tr = re.compile(r"expert tiers: GPU \d+ hits this request; since the start RAM (\d+) blobs, files (\d+) blobs ([\d.]+) MB")
tm = re.compile(r"strata decode timing: (\d+) windows, avg T [\d.]+, ([\d.]+) tokens/window, ([\d.]+) ms/window = verify [\d.]+ \(GPU-reach wait ([\d.]+) \+ per-layer host ([\d.]+) \[plan [\d.]+ actq [\d.]+ jobs ([\d.]+) CPU ([\d.]+)\]")
rows = []; cur = None; pr = pf = 0; pmb = 0.0; t = None
for l in log[st:]:
    m = tm.search(l)
    if m: t = dict(win=int(m.group(1)), tpw=float(m.group(2)), msw=float(m.group(3)), wait=float(m.group(4)), host=float(m.group(5)), jobs=float(m.group(6)), cpu=float(m.group(7)))
    m = rq.search(l)
    if m:
        cur = dict(ctx=int(m.group(1)), read=int(m.group(3)), rd_s=int(m.group(4)) / 1000, gen=int(m.group(5)), gms=int(m.group(6)), t=t); t = None; continue
    if cur is None: continue
    m = ht.search(l)
    if m: cur["hit"] = float(m.group(1))
    m = tr.search(l)
    if m:
        r, f, mb = int(m.group(1)), int(m.group(2)), float(m.group(3))
        cur.update(ram=r - pr, file=f - pf, mb=mb - pmb); pr, pf, pmb = r, f, mb
        rows.append(cur); cur = None
# the server may split one completion into two engine requests: merge a row into the previous one when it only continues it
merged = []
for r in rows:
    if merged and r["read"] <= 40 and abs(r["ctx"] - (merged[-1]["ctx"] + merged[-1]["gen"])) <= 40 and merged[-1]["gen"] > 0:
        a = merged[-1]
        a["gen"] += r["gen"]; a["gms"] += r["gms"]; a["ram"] += r["ram"]; a["file"] += r["file"]; a["mb"] += r["mb"]
        if r["t"] and a["t"]:
            w = a["t"]["win"] + r["t"]["win"]
            for k in ("tpw", "msw", "wait", "host", "jobs", "cpu"): a["t"][k] = (a["t"][k] * a["t"]["win"] + r["t"][k] * r["t"]["win"]) / w
            a["t"]["win"] = w
    else: merged.append(r)
main = [s for s in steps if s["phase"] == "A" or (s["phase"].startswith("B") and "-" not in s["phase"])]
by = {}
for s in main:
    cands = [r for r in merged if abs(r["ctx"] - s["prompt"]) <= 2 and "used" not in r]
    if cands: cands[0]["used"] = 1; s["row"] = cands[0]
nA = sum(1 for s in main if s["phase"] == "A")
def part(s):
    if s["phase"].startswith("B"):          # the first three answers after a compression apart from the rest
        k = s["phase"][1:] or "1"
        first = [x["step"] for x in main if x["phase"] == s["phase"]][:3]
        return "B%s: after compression %s, first 3" % (k, k) if s["step"] in first else "B%s: after compression %s, later" % (k, k)
    return "A1: tool loop, first half" if s["step"] < nA / 2 else "A2: tool loop, second half"
print("step ph  max  ctx     read  rd_s | gen   tok/s | hit%% | RAM/t FILE/t  MB/t | ms/win wait  host(jobs cpu) tok/win")
for s in main:
    r = s.get("row")
    if not r: print("%3d %s  (no log row for prompt %s)" % (s["step"], s["phase"], s["prompt"])); continue
    g = max(r["gen"], 1); tt = r["t"] or {}
    print("%3d  %s %5d %6d %6d %5.1f | %4d  %5.1f | %4.1f | %5.1f %5.1f %6.1f | %5.1f %5.1f %5.1f (%4.1f %4.1f) %4.2f" % (s["step"], s["phase"], s["max_tokens"], r["ctx"], r["read"], r["rd_s"], r["gen"], 1000 * r["gen"] / max(r["gms"], 1), r.get("hit", 0), r["ram"] / g, r["file"] / g, r["mb"] / g, tt.get("msw", 0), tt.get("wait", 0), tt.get("host", 0), tt.get("jobs", 0), tt.get("cpu", 0), tt.get("tpw", 0)))
    by.setdefault(part(s), []).append((s, r))
print()
print("part                               | n | tok/s short  long   all | hit%  | FILE/t | ms/win  wait  host  jobs")
for k in sorted(by):
    v = by[k]
    def tps(sel):
        g = sum(r["gen"] for s, r in v if sel(s)); ms = sum(r["gms"] for s, r in v if sel(s))
        return 1000 * g / ms if ms else 0
    g = sum(r["gen"] for s, r in v); w = sum((r["t"] or {}).get("win", 0) for s, r in v) or 1
    avg = lambda key: sum((r["t"] or {}).get(key, 0) * (r["t"] or {}).get("win", 0) for s, r in v) / w
    print("%-34s | %2d | %5.1f      %5.1f %5.1f | %5.1f | %6.1f | %5.1f  %5.1f %5.1f %5.1f" % (k, len(v), tps(lambda s: s["max_tokens"] <= 600), tps(lambda s: s["max_tokens"] > 600), tps(lambda s: True),
          sum(r.get("hit", 0) * r["gen"] for s, r in v) / max(g, 1), sum(r["file"] for s, r in v) / max(g, 1), avg("msw"), avg("wait"), avg("host"), avg("jobs")))
for s in steps:
    if s not in main: print("other request:", s)
