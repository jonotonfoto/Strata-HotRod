"""How much of a decode window is spent fetching experts that are not in VRAM, by answer length.

    python disk_wait.py results/27-long.txt [results/29-longctl.txt ...]

Reads the per-step rows that sim_table.py printed into a results file.  The "jobs" stage of the engine's
`strata decode timing:` line is the time between the activation quantize and the CPU pool's run in the per-layer
dispatch: building the job list, which is where `blob(layer, expert)` is called for every miss - a pointer for an
expert in RAM, a read from the file for one that is not.  So jobs is the upper bound of what a read-ahead could save.
"tok/s without jobs" is the same request with that stage taken out entirely (ms/window - jobs)."""
import re
import sys

row = re.compile(r"^\s*(\d+)\s+(A|B\d*)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d.]+) \|\s*(\d+)\s+([\d.]+) \|\s*([\d.]+) \|\s*([\d.]+)\s+([\d.]+)\s+([\d.]+) \|"
                 r"\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\(\s*([\d.]+)\s+([\d.]+)\)\s*([\d.]+)")
buckets = [(1, 150, "up to 150"), (151, 450, "151-450"), (451, 700, "451-700"), (701, 99999, "over 700")]

for path in sys.argv[1:]:
    rows = []
    for line in open(path, encoding="utf-8", errors="replace"):
        m = row.match(line)
        if not m:
            continue
        g = [float(x) if i != 1 else x for i, x in enumerate(m.groups())]
        rows.append(dict(read=g[4], gen=g[6], tps=g[7], filet=g[10], msw=g[12], wait=g[13], host=g[14], jobs=g[15], cpu=g[16], tpw=g[17]))
    print("%s: %d steps" % (path, len(rows)))
    print("answer, tokens | n  | tok/s | ms/window | jobs ms | jobs share | wait ms | CPU ms | tokens/window | file blobs/token | tok/s without jobs")
    for lo, hi, name in buckets + [(1, 99999, "all")]:
        sel = [r for r in rows if lo <= r["gen"] <= hi]
        if not sel:
            continue
        gen = sum(r["gen"] for r in sel)
        # weight every per-window figure by the request's windows (generated tokens / tokens per window)
        win = [r["gen"] / r["tpw"] for r in sel]
        W = sum(win)
        av = lambda k: sum(r[k] * w for r, w in zip(sel, win)) / W
        msw, jobs = av("msw"), av("jobs")
        tps = 1000.0 * gen / (msw * W)
        print("%-14s | %2d | %5.1f | %9.1f | %7.1f | %9.0f%% | %7.1f | %6.1f | %13.2f | %16.1f | %5.1f" % (
            name, len(sel), tps, msw, jobs, 100 * jobs / msw, av("wait"), av("cpu"), gen / W,
            sum(r["filet"] * r["gen"] for r in sel) / gen, 1000.0 * gen / ((msw - jobs) * W)))
    print()
