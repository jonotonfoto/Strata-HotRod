"""Write a temporary server config cfg-<name>.json beside this script (git-ignored: it holds the API key).

    python make_cfg.py <name> [base=<config file>] [exe=<engine exe>] [VAR=VALUE ...] [~VAR ...] [+<arg> [value] ...] [-<arg> ...]

  base=   the config to start from (default: strata-ud-q4_k_xl.json.before-ram-adapt in the repository root)
  exe=    the engine to run instead of the config's
  VAR=V   set an engine environment variable;  ~VAR  take one out
  +--x v  append an engine argument (with its value);  ---x  take the argument --x and its value out
Prints the path of the file it wrote."""
import json, sys
from pathlib import Path
HERE = Path(__file__).parent
ROOT = Path(__file__).resolve().parents[2]
name = sys.argv[1]
base = ROOT / "strata-ud-q4_k_xl.json.before-ram-adapt"
ops = sys.argv[2:]
for o in ops:
    if o.startswith("base="): base = Path(o[5:])
c = json.loads(base.read_text(encoding="utf-8-sig"))
args = list(c["args"]); env = dict(c.get("env") or {})
i = 0
while i < len(ops):
    o = ops[i]; i += 1
    if o.startswith("base="): continue
    if o.startswith("exe="): c["exe"] = o[4:]
    elif o.startswith("~"): env.pop(o[1:], None)
    elif o.startswith("+"):
        args.append(o[1:])
        if i < len(ops) and not ops[i].startswith(("+", "-", "~")) and "=" not in ops[i]:
            args.append(ops[i]); i += 1
    elif o.startswith("-"):
        a = o[1:]
        if a in args:
            k = args.index(a)
            n = 2 if k + 1 < len(args) and not args[k + 1].startswith("--") else 1
            args = args[:k] + args[k + n:]
    elif "=" in o:
        k, v = o.split("=", 1); env[k] = v
c["args"] = args; c["env"] = env
out = HERE / ("cfg-%s.json" % name)
out.write_text(json.dumps(c, indent=1), encoding="utf-8")
print(out)
