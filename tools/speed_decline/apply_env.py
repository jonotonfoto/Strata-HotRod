"""Add this fork's speed-fix variables to the server configs, after an update or a first install.

    python tools/speed_decline/apply_env.py [--dry-run]

For every strata-<model>.json in the Strata folder: the keys of "env" in env.example.json (beside this script) that
the config's "env" does not have yet are added. A key the config already has keeps its value, whatever it is, and
nothing else in the file is changed. Before a config is written, a copy is saved beside it as
<name>.json.bak-speed-fixes (git-ignored) (once: an existing copy is left alone). --dry-run only prints.

It also says whether the engine in engine/ is the one compiled from this source (the fixes are only in that one).
Prints variable names, never the config's other content."""
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
dry = "--dry-run" in sys.argv[1:]

want = json.loads((HERE / "env.example.json").read_text(encoding="utf-8"))["env"]

build = ROOT / "engine" / "BUILD.json"
try:
    source = json.loads(build.read_text(encoding="utf-8")).get("source")
except (OSError, ValueError):
    source = None
if source == "local":
    print("engine: compiled from this source (engine/BUILD.json says \"local\")")
elif source is None:
    print("engine: no engine/BUILD.json yet - run setup with --build first (docs/SPEED_FIXES_SETUP.md, section 2)")
else:
    print("engine: NOT compiled from this source (engine/BUILD.json says \"%s\"), so it has none of the fixes and the\n"
          "        variables below do nothing. Run setup again with --build (docs/SPEED_FIXES_SETUP.md, section 2)." % source)

found = 0
for path in sorted(ROOT.glob("strata-*.json")):
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        cfg = json.loads(raw.decode("utf-8-sig"))
    except ValueError:
        continue
    if not isinstance(cfg, dict) or "exe" not in cfg or "args" not in cfg:
        continue                                           # not a server config
    found += 1
    env = cfg.get("env")
    if not isinstance(env, dict):
        env = {}
    add = {k: v for k, v in want.items() if k not in env}
    if not add:
        print("%s: nothing to add (all %d variables are there)" % (path.name, len(want)))
        continue
    print("%s: %s %s" % (path.name, "would add" if dry else "adding", ", ".join("%s=%s" % kv for kv in add.items())))
    if dry:
        continue
    backup = path.with_name(path.name + ".bak-speed-fixes")
    if not backup.exists():
        shutil.copy2(path, backup)
    cfg["env"] = {**env, **add}
    text = json.dumps(cfg, indent=1, ensure_ascii=False) + "\n"
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))

if not found:
    print("no strata-<model>.json in %s yet: install a model first (docs/SPEED_FIXES_SETUP.md, section 0)" % ROOT.name)
elif not dry:
    print("Restart the server for the variables to take effect, then check the log (docs/SPEED_FIXES_SETUP.md, section 4).")
