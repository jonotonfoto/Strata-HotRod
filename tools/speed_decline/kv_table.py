import re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]   # the repository root
log = (ROOT / "strata-ud-q4_k_xl.log").read_bytes().replace(b"\x00", b"").decode("utf-8", "replace").split("\n")
start = int(sys.argv[1])
rq = re.compile(r"strata serve: prompt (\d+) tokens = (\d+) reused \+ (\d+)(?: of \d+)? read in (\d+) ms \(([\d.]+) tok/s\), (\d+) generated in (\d+) ms \(([\d.]+) tok/s\)")
kv = re.compile(r"KV streaming: ([\d.]+)% of (\d+) block reads hit VRAM, ([\d.]+) MiB read from RAM")
cur = None; pn = 0; pm = 0.0; pmib = 0.0; i = 0
print(" #    ctx   read   gen   tps | KV reads/tok(k)  KV miss/tok  miss%  MiB RAM/tok | note")
for l in log[start:]:
    m = rq.search(l)
    if m: cur = (int(m.group(1)), int(m.group(3)), int(m.group(6)), float(m.group(8))); continue
    m = kv.search(l)
    if m and cur:
        i += 1
        h, n, mib = float(m.group(1)), int(m.group(2)), float(m.group(3))
        miss = n * (100 - h) / 100
        note = ''
        if n < pn: note = 'counter reset'; dn, dm, dmib = n, miss, mib
        else: dn, dm, dmib = n - pn, miss - pm, mib - pmib
        pn, pm, pmib = n, miss, mib
        tok = cur[1] + cur[2]   # KV is read by prompt tokens and generated tokens alike
        if cur[2] >= 100:
            print(f"{i:2d} {cur[0]:6d} {cur[1]:6d} {cur[2]:5d} {cur[3]:5.1f} | {dn/tok/1000:10.1f}  {dm/tok:10.0f}  {100*dm/max(dn,1):5.2f}  {dmib/tok:8.2f}   | {note}")
        cur = None
