"""Shared by the loads here: which server config to use and how to call the running server.

The config is the strata-<model>.json in the Strata folder (the only one, or the one named with --config); the
loads read the port and the API key from it and never print the key."""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # the Strata folder


def take_option(name, default=None):
    """Remove `--name value` from sys.argv and return the value."""
    if name in sys.argv:
        i = sys.argv.index(name)
        value = sys.argv[i + 1]
        del sys.argv[i:i + 2]
        return value
    return default


def load_config():
    named = take_option("--config")
    if named:
        path = Path(named)
    else:
        found = sorted(p for p in ROOT.glob("strata-*.json") if ".bak" not in p.name)
        if len(found) != 1:
            sys.exit("pass --config <strata-MODEL.json>: found %d configs in %s" % (len(found), ROOT))
        path = found[0]
    return json.loads(path.read_text(encoding="utf-8-sig"))


def texts():
    """Two long texts that every install has: the server's Python source and the docs."""
    def read(pattern):
        return "".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(ROOT.glob(pattern)))
    return read("serve/*.py"), read("docs/*.md")


def chat(cfg, messages, max_tokens, thinking=None):
    """One request to the running server -> (the response as a dict, seconds sent, seconds answered)."""
    body = {"model": "x", "messages": messages, "max_tokens": max_tokens, "temperature": 0}
    if thinking is not None:
        body["reasoning_effort"] = thinking
    req = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % cfg.get("port", 8080),
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + cfg.get("api_key", "")})
    t0 = time.time()
    out = json.loads(urllib.request.urlopen(req, timeout=1800).read())
    return out, t0, time.time()
