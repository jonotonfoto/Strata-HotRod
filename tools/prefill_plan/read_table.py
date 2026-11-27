"""Every prompt read in an engine log, with the read plan the engine chose.
    python tools/prefill_plan/read_table.py <engine log> [<memory samples csv or ->] [<log> <csv or -> ...]
The optional csv has the columns time,used_gib,avail_gib,strata_rss_gib (one sample every few seconds).  Per log: every request (context, new tokens, read time, read plan, chunks, refill, generated), then totals and
read speed by size class.  Read only."""
import re, sys

sys.stdout.reconfigure(encoding="utf-8")
CLASSES = [(0, 3000, "до 3 тыс."), (3000, 11776, "3–11,8 тыс."), (11776, 13825, "11,8–13,8 тыс."), (13825, 10**9, "от 13,8 тыс.")]

if len(sys.argv) == 2:
    sys.argv.append("-")
for k in range(1, len(sys.argv), 2):
    logp, memp = sys.argv[k], sys.argv[k + 1]
    rows, cur = [], {}
    for l in open(logp, encoding="utf-8", errors="replace"):
        m = re.search(r"read plan: ([^(]+)\(a segment of (\d+) tokens, chunk (\d+)\)", l)
        if m:
            cur.setdefault("plans", []).append((m.group(1).strip(), int(m.group(2)), int(m.group(3))))
        m = re.search(r"layer-major: (\d+) chunks, \d+ layers, (\d+) experts streamed, (\d+) reused from the layer map \((\d+) MB, (\w+)\)", l)
        if m:
            cur.setdefault("lm", []).append(tuple(m.groups()))
        m = re.search(r"layer-major state: (\d+) of (\d+) tokens on the GPU", l)
        if m:
            cur.setdefault("state", []).append((int(m.group(1)), int(m.group(2))))
        if "layer-major not taken" in l:
            cur["not_taken"] = cur.get("not_taken", 0) + 1
        if re.search(r"MB, cudaMalloc\)", l):
            cur["malloc"] = cur.get("malloc", 0) + 1
        m = re.search(r"trace: refilled (\d+) slots on \d+ stage\(s\) in ([\d.]+) ms", l)
        if m:
            cur.setdefault("refill", []).append((int(m.group(1)), float(m.group(2))))
        m = re.search(r"prompt (\d+) tokens = (\d+) reused \+ (\d+) read in (\d+) ms \(([\d.]+) tok/s\), (\d+) generated in (\d+) ms", l)
        if m:
            cur.update(ctx=int(m.group(1)), new=int(m.group(3)), read=int(m.group(4)) / 1000, gen=int(m.group(6)), gen_s=int(m.group(7)) / 1000)
            rows.append(cur)
            cur = {}
    log = open(logp, encoding="utf-8", errors="replace").read()
    head = re.search(r"prompt chunk auto: (\d+) tokens", log)
    slots = re.search(r"expert cache (\d+) slots", log)
    print(f"=== {logp}")
    print(f"пакет {head.group(1) if head else '?'} ток., кэш {slots.group(1) if slots else '?'} слотов, запросов {len(rows)}")
    print("№ | контекст | новых ток. | чтение, с | ток/с | план (пакет) | кусков: привезено / из карты | состояние на карте | возврат: слотов, с | сгенерировано, ток/с")
    for i, r in enumerate(rows, 1):
        plan = "; ".join(f"{'один кусок' if p[0].startswith('one') else 'послойный'} ({p[2]})" for p in r.get("plans", [])) or "-"
        lm = "; ".join(f"{a}: {b} / {c}" for a, b, c, _, _ in r.get("lm", [])) or "-"
        st = "; ".join(f"{a} из {b}" for a, b in r.get("state", [])) or "-"
        rf = r.get("refill", [])
        print(f"{i} | {r['ctx']} | {r['new']} | {r['read']:.1f} | {r['new'] / r['read']:.0f} | {plan} | {lm} | {st} | "
              f"{sum(x[0] for x in rf)}, {sum(x[1] for x in rf) / 1000:.1f} | {r['gen']}, {r['gen'] / r['gen_s']:.1f}" if r["gen_s"] else "")
    tr, tn = sum(r["read"] for r in rows), sum(r["new"] for r in rows)
    rf_s = sum(x[1] for r in rows for x in r.get("refill", [])) / 1000
    rf_n = sum(x[0] for r in rows for x in r.get("refill", []))
    print(f"всего: чтение {tr:.1f} с на {tn} токенов ({tn / tr:.0f} ток/с); возврат {rf_s:.1f} с ({rf_n} слотов, {100 * rf_s / tr:.0f}% чтения); "
          f"генерация {sum(r['gen_s'] for r in rows):.1f} с на {sum(r['gen'] for r in rows)} токенов; "
          f"не взят послойный: {sum(r.get('not_taken', 0) for r in rows)}; cudaMalloc карты: {sum(r.get('malloc', 0) for r in rows)}")
    for lo, hi, name in CLASSES:
        rs = [r for r in rows if lo <= r["new"] < hi]
        if rs:
            print(f"  чтения {name}: {len(rs)} шт., {sum(r['new'] for r in rs)} ток. за {sum(r['read'] for r in rs):.1f} с = "
                  f"{sum(r['new'] for r in rs) / sum(r['read'] for r in rs):.0f} ток/с")
    dec = [r["gen"] / r["gen_s"] for r in rows if r["gen"] >= 200 and r["gen_s"]]
    if dec:
        print(f"  генерация на ответах от 200 токенов: {len(dec)} шт., {min(dec):.1f}–{max(dec):.1f} ток/с")
    mem = [] if memp == "-" else [l.split(",") for l in open(memp, encoding="utf-8").read().splitlines()[1:] if l.strip()]
    if mem:
        used, avail, rss = [float(x[1]) for x in mem], [float(x[2]) for x in mem], [float(x[3]) for x in mem]
        print(f"  память: пик занятого {max(used):.1f} ГиБ, минимум свободного {min(avail):.1f} ГиБ, движок до {max(rss):.1f} ГиБ, "
              f"остальная система {min(u - r for u, r in zip(used, rss) if r > 30):.1f}–{max(u - r for u, r in zip(used, rss) if r > 30):.1f} ГиБ; "
              f"замеров выше 60 ГиБ: {sum(1 for u in used if u > 60)} из {len(used)}")
    print()
