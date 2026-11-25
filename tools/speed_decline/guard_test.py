"""Tests for STRATA_TAIL_GUARD against whatever server is running (the engine log has the numbers).

  short tail (test G): a new conversation whose LAST message is a few words - the read's last segment is then a
    handful of tokens, and without the guard the end-of-read plan hands the lent slots out by that sample;
  cancelled read (test V): a healthy conversation, then another conversation whose read is dropped by the client after
    10 s (in the middle of the layer pass), then the first conversation again.

    python guard_test.py <label>

Prints one line per step; read the engine log with req_table.py and the `prompt tail:` lines."""
import http.client, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
cfg = json.loads((ROOT / "strata-ud-q4_k_xl.json").read_text(encoding="utf-8-sig"))
PORT, KEY, MODEL = cfg.get("port", 8081), cfg.get("api_key", ""), cfg.get("model_name")
A = (ROOT / "SPEC.md").read_text(encoding="utf-8", errors="replace")[:88000]
B = (ROOT / "docs" / "DETAILS.md").read_text(encoding="utf-8", errors="replace")[:68000]
LONG = "Explain this in detail, at least 600 words: the expert cache, the adaptive tier and the prompt path."

def chat(messages, max_tokens, abort_after=None):
    body = json.dumps({"model": MODEL, "messages": messages, "stream": True, "max_tokens": max_tokens, "temperature": 0}).encode()
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=1800)
    t0 = time.time()
    c.request("POST", "/v1/chat/completions", body, {"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    if abort_after is not None:          # the client leaves while the engine is still reading the prompt
        c.sock.settimeout(abort_after)
        try:
            r = c.getresponse()
            while time.time() - t0 < abort_after: r.fp.readline()
        except Exception:
            pass
        c.close()
        return None, time.time() - t0
    r = c.getresponse(); out = []
    for line in r:
        line = line.decode("utf-8", "replace").strip()
        if not line.startswith("data:"): continue
        d = line[5:].strip()
        if d == "[DONE]": break
        try: j = json.loads(d)
        except ValueError: continue
        for ch in j.get("choices", []):
            if ch.get("delta", {}).get("content"): out.append(ch["delta"]["content"])
    c.close()
    return "".join(out), time.time() - t0

def step(name, messages, max_tokens, abort_after=None):
    a, dt = chat(messages, max_tokens, abort_after)
    print("%s %-34s %6.1f s%s" % (time.strftime("%H:%M:%S"), name, dt, "  (the client left)" if a is None else ", %d chars" % len(a)), flush=True)
    return a

label = sys.argv[1] if len(sys.argv) > 1 else "x"
print("guard test", label)
# ---- test G: a cold read whose last message is tiny
g = [{"role": "user", "content": "Here is a specification.\n\n" + A + "\n\nRead it; I will ask about it."},
     {"role": "assistant", "content": "I have read the specification."},
     {"role": "user", "content": "Continue."}]
a = step("G1 short tail, cold read", g, 600)
g += [{"role": "assistant", "content": a or ""}, {"role": "user", "content": LONG}]
a = step("G2 next turn", g, 600)
# ---- test V: a healthy conversation, another one cancelled mid-read, the first one again
v = [{"role": "user", "content": "A manual follows.\n\n" + B + "\n\n" + LONG}]
a = step("V1 healthy conversation, cold read", v, 600)
v += [{"role": "assistant", "content": a or ""}, {"role": "user", "content": "Now the same for the conversation cache and the K/V streaming, at least 600 words."}]
a = step("V2 its next turn (before)", v, 600)
step("V3 other conversation, cancelled", [{"role": "user", "content": "Second copy.\n\n" + A + "\n\nSummarize this in detail, at least 1000 words."}], 600, abort_after=10.0)
time.sleep(3)
v += [{"role": "assistant", "content": a or ""}, {"role": "user", "content": "Now the same for the look-ahead and the stand-ins, at least 600 words."}]
a = step("V4 first conversation (after)", v, 600)
v += [{"role": "assistant", "content": a or ""}, {"role": "user", "content": "Now the same for the prompt chunking and checkpoints, at least 600 words."}]
step("V5 its next turn (after)", v, 600)
