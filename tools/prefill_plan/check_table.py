"""Table of the answer and decode check: the outputs of load_check.py, saved as <dir>/<name>-load.txt.
    python tools/prefill_plan/check_table.py <dir> <base run> <changed run> [<base repeat> ...]
Per run: graded answers by category, decode speed on answers of 400+ tokens, the long reads.  Then, pair by pair,
which answers are the same text.  Read only."""
import json, statistics, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
D = Path(sys.argv[1])
names = sys.argv[2:]
CATS = ["math", "facts", "format", "russian", "code", "longform", "needle", "summary"]


def load(name):
    rows = {}
    for line in (D / f"{name}-load.txt").read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("{"):
            r = json.loads(line)
            rows[r["id"]] = r
    return rows


runs = {n: load(n) for n in names}
print("== Оценённые ответы (верно / всего), ошибки вызовов")
print("прогон | " + " | ".join(CATS) + " | всего | ошибок")
for n, rows in runs.items():
    cells, K, N = [], 0, 0
    for c in CATS:
        rs = [r for r in rows.values() if r["cat"] == c and r.get("ok") is not None]
        k = sum(r["ok"] for r in rs)
        K, N = K + k, N + len(rs)
        cells.append(f"{k}/{len(rs)}" if rs else "-")
    print(f"{n} | " + " | ".join(cells) + f" | {K}/{N} | {sum(1 for r in rows.values() if 'error' in r)}")
for n, rows in runs.items():
    bad = [r for r in rows.values() if r.get("ok") is False or "error" in r]
    for r in bad:
        print(f"  НЕВЕРНО {n} {r['id']}: {(r.get('error') or r.get('text') or '')[-120:]!r}")

print("\n== Скорость генерации, ток/с (по часам движка); ответы от 400 токенов")
print("прогон | длинные ответы без контекста: число, медиана, мин–макс | итоги после длинного чтения: число, медиана, мин–макс | все ответы от 100 токенов: медиана")
for n, rows in runs.items():
    def tps(cat, least):
        return [r["timings"]["predicted_per_second"] for r in rows.values()
                if r["cat"] == cat and (r.get("timings") or {}).get("predicted_per_second") and r["usage"].get("completion_tokens", 0) >= least]
    lf, sm = tps("longform", 400), tps("summary", 400)
    allr = [r["timings"]["predicted_per_second"] for r in rows.values()
            if (r.get("timings") or {}).get("predicted_per_second") and r["usage"].get("completion_tokens", 0) >= 100]
    f = lambda v: f"{len(v)}, {statistics.median(v):.1f}, {min(v):.1f}–{max(v):.1f}" if v else "0"
    print(f"{n} | {f(lf)} | {f(sm)} | {statistics.median(allr):.1f} ({len(allr)})" if allr else f"{n} | {f(lf)} | {f(sm)} | -")
print("по ответам: id | токенов | ток/с по прогонам")
for i in [i for i, r in runs[names[0]].items() if r["cat"] in ("longform", "summary")]:
    print(f"  {i} | " + " / ".join(str(runs[n].get(i, {}).get("usage", {}).get("completion_tokens")) for n in names) + " | "
          + " / ".join(str((runs[n].get(i, {}).get("timings") or {}).get("predicted_per_second")) for n in names))

print("\n== Длинные чтения (первый ход разговора и длинное дочитывание): токенов прочитано, секунд по часам движка")
for i in ("A-first", "A-append", "B-first", "C-first", "D-first"):
    print(f"  {i} | " + " / ".join(f"{(runs[n].get(i, {}).get('timings') or {}).get('prompt_n')} ток., "
                                    f"{((runs[n].get(i, {}).get('timings') or {}).get('prompt_ms') or 0) / 1000:.1f} с" for n in names))

print("\n== Одинаков ли текст ответов (температура 0)")
for a in range(len(names)):
    for b in range(a + 1, len(names)):
        A, B = runs[names[a]], runs[names[b]]
        print(f"{names[a]} и {names[b]}:")
        for c in CATS:
            ids = [i for i, r in A.items() if r["cat"] == c and i in B and "text" in r and "text" in B[i]]
            same = [i for i in ids if A[i]["text"] == B[i]["text"]]
            diff = [i for i in ids if i not in same]
            line = f"  {c}: одинаковых {len(same)} из {len(ids)}"
            if diff:
                def first(i):
                    x, y = A[i]["text"], B[i]["text"]
                    return next((k for k, (p, q) in enumerate(zip(x, y)) if p != q), min(len(x), len(y)))
                line += "; разные: " + ", ".join(f"{i} (с символа {first(i)} из {len(A[i]['text'])})" for i in diff)
            print(line)
