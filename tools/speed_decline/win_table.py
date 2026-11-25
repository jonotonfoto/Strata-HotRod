import re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]   # the repository root
log = (ROOT / "strata-ud-q4_k_xl.log").read_bytes().replace(b"\x00", b"").decode("utf-8", "replace").split("\n")
start = int(sys.argv[1])
rq = re.compile(r"strata serve: prompt (\d+) tokens = (\d+) reused \+ (\d+)(?: of \d+)? read in (\d+) ms \(([\d.]+) tok/s\), (\d+) generated in (\d+) ms \(([\d.]+) tok/s\)(?:, drafts accepted (\d+) of (\d+))?")
wn = re.compile(r"look-ahead learner: trained in (\d+) of (\d+) windows")
ht = re.compile(r"decode expert cache hit rate: ([\d.]+)% \((\d+) hits / (\d+) lookups\)")
pw = 0
def z(): return dict(n=0, gen=0, ms=0, da=0, dn=0, look=0, hits=0, ctx=[])
a = z()
print("requests  ctx range        gen   tps | windows tok/win ms/win | draft acc% | lookups/win  hit%  miss/win")
for l in log[start:]:
    m = rq.search(l)
    if m:
        a['n'] += 1; a['ctx'].append(int(m.group(1))); a['gen'] += int(m.group(6)); a['ms'] += int(m.group(7)); a['da'] += int(m.group(9) or 0); a['dn'] += int(m.group(10) or 0); continue
    m = ht.search(l)
    if m: a['hits'] += int(m.group(2)); a['look'] += int(m.group(3)); continue
    m = wn.search(l)
    if m:
        w = int(m.group(2)) - pw; pw = int(m.group(2))
        if w > 0 and a['n'] and a['look']:
            print(f"{a["dn"]/w:5.2f} drafts/win | {a["n"]:5d}   {min(a['ctx']):6d}-{max(a['ctx']):6d} {a['gen']:6d} {1000*a['gen']/a['ms']:5.1f} | {w:6d}  {a['gen']/w:5.2f} {a['ms']/w:6.1f} | {100*a['da']/max(a['dn'],1):6.0f}    | {a['look']/w:8.0f}   {100*a['hits']/a['look']:5.1f}  {(a['look']-a['hits'])/w:6.0f}")
        a = z()
