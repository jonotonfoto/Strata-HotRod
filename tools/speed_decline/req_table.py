import re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]   # the repository root
log = (ROOT / "strata-ud-q4_k_xl.log").read_bytes().replace(b"\x00", b"").decode("utf-8", "replace").split("\n")
start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
pat = {
 'req': re.compile(r"strata serve: prompt (\d+) tokens = (\d+) reused \+ (\d+)(?: of \d+)? read in (\d+) ms \(([\d.]+) tok/s\), (\d+) generated in (\d+) ms \(([\d.]+) tok/s\)(?:, drafts accepted (\d+) of (\d+))?"),
 'hit': re.compile(r"decode expert cache hit rate: ([\d.]+)% \((\d+) hits / (\d+) lookups\)"),
 'tiers': re.compile(r"expert tiers: GPU (\d+) hits this request; since the start RAM (\d+) blobs, files (\d+) blobs ([\d.]+) MB read"),
 'skip': re.compile(r"route tail skip: (\d+) missed experts skipped \((\d+) entries\) since the start"),
 'work': re.compile(r"work done: swap rounds (\d+) \((\d+) swaps, (\d+) quality\), ram evictions (\d+), look-ahead (\d+) predicted"),
 'kv': re.compile(r"KV streaming: ([\d.]+)% of (\d+) block reads hit VRAM, ([\d.]+) MiB read from RAM"),
 'tail': re.compile(r"prompt tail: (\d+) tokens, (\d+) experts not in VRAM among its hottest; the refill took (\d+)"),
 'async': re.compile(r"asynchronous adaptive tier: (\d+) rounds, (\d+) experts swapped in, ([\d.]+) ms per round"),
 'vram': re.compile(r"only (\d+) MiB of VRAM free at the start"),
 'mask': re.compile(r"mask \(STRATA_MASK\): (\d+) masked picks seen, (\d+) moved"),
 'latail': re.compile(r"look-ahead tail read: (\d+) rank>=lo guesses queued, (\d+) skipped \(a stand-in will serve them\), (\d+) held back"),
 'start': re.compile(r"\[strata\] (\S+ \S+) engine started"),
}
cur = {}; prev = dict(ram=0, fb=0, fmb=0.0, skip=0, kvr=0, kvm=0.0, rounds=0, sw=0, lq=0, ls=0, lh=0)
print("line   ctx   reuse  read  rd_s |  gen  tps  acc% | hit%  look/t | RAMb/t  FILEb/t  MB/t | skip/t | kvRAM MiB/t kvhit | rounds sw/round ms | refill vramfree")
for i, l in enumerate(log):
    if i < start: continue
    m = pat['start'].search(l)
    if m:
        print("=== engine start", m.group(1)); prev = dict(ram=0, fb=0, fmb=0.0, skip=0, kvr=0, kvm=0.0, rounds=0, sw=0, lq=0, ls=0, lh=0); cur = {}; continue
    for k in ('hit','tiers','skip','work','kv','tail','async','vram','mask','latail'):
        m = pat[k].search(l)
        if m: cur[k] = m.groups()
    m = pat['req'].search(l)
    if m: cur['req'] = m.groups(); cur['line'] = i
    # a request block ends at 'expert tiers' line (after req)
    if 'req' in cur and pat['tiers'].search(l):
        r = cur['req']; tot, reu, rd, rdms, gen, genms, tps = int(r[0]), int(r[1]), int(r[2]), int(r[3]), int(r[5]), int(r[6]), float(r[7])
        acc = (100*int(r[8])/int(r[9])) if r[8] and int(r[9]) else 0
        h = cur.get('hit', ('0','0','0')); t = cur['tiers']
        ram, fb, fmb = int(t[1]), int(t[2]), float(t[3])
        sk = int(cur.get('skip', ('0','0'))[0])
        kv = cur.get('kv'); kvm = float(kv[2]) if kv else 0; kvh = kv[0] if kv else '-'
        a = cur.get('async', ('0','0','0'))
        g = max(gen, 1)
        print(f"{cur['line']:5d} {tot:6d} {reu:6d} {rd:5d} {rdms/1000:5.1f} | {gen:4d} {tps:5.1f} {acc:4.0f} | {float(h[0]):4.1f} {int(h[2])/g:7.1f} | {(ram-prev['ram'])/g:6.1f} {(fb-prev['fb'])/g:7.1f} {(fmb-prev['fmb'])/g:6.1f} | {(sk-prev['skip'])/g:6.1f} | {(kvm-prev['kvm'])/g:6.2f} {kvh:>5} | {a[0]:>4} {a[1]:>5} {a[2]:>6} | {cur.get('tail',('','','-'))[2]:>5} {cur.get('vram',('-',))[0]:>5}")
        prev.update(ram=ram, fb=fb, fmb=fmb, skip=sk, kvm=kvm)
        cur = {}
