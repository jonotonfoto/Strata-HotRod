"""Repro driver: one phase per call. State (the conversation) is kept in conv.json beside this file."""
import http.client, json, sys, time
from pathlib import Path
HERE = Path(__file__).parent
ROOT = Path(__file__).resolve().parents[2]
cfg = json.loads((ROOT / "strata-ud-q4_k_xl.json").read_text(encoding="utf-8-sig"))
PORT, KEY, MODEL = cfg.get("port", 8081), cfg.get("api_key", ""), cfg.get("model_name")
CONV = HERE / "conv.json"

def text(path, n):
    return (ROOT / path).read_text(encoding="utf-8", errors="replace")[:n]

A = "Here is a technical specification.\n\n" + text("SPEC.md", 88000)
B = "Here is a second document, the engine's detailed manual.\n\n" + text("docs/DETAILS.md", 68000)
Q1 = "\n\nWrite a long, detailed, structured summary of this document: every major section, the mechanisms, and the numbers. At least 1500 words."

def chat(messages, max_tokens, abort_after=None):
    body = json.dumps({"model": MODEL, "messages": messages, "stream": True, "max_tokens": max_tokens, "temperature": 0}).encode()
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=1800)
    t0 = time.time()
    c.request("POST", "/v1/chat/completions", body, {"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    if abort_after is not None:
        c.sock.settimeout(abort_after)
        try:
            r = c.getresponse()
            while time.time() - t0 < abort_after:
                r.fp.readline()
        except Exception as e:
            print("  (abort wait ended: %s)" % type(e).__name__)
        c.close()
        print("  ABORTED the connection after %.1f s" % (time.time() - t0))
        return None
    r = c.getresponse()
    out, think, n = [], [], 0
    for line in r:
        line = line.decode("utf-8", "replace").strip()
        if not line.startswith("data:"): continue
        d = line[5:].strip()
        if d == "[DONE]": break
        try: j = json.loads(d)
        except ValueError: continue
        for ch in j.get("choices", []):
            dl = ch.get("delta", {})
            if dl.get("content"): out.append(dl["content"]); n += 1
            if dl.get("reasoning_content"): think.append(dl["reasoning_content"])
    c.close()
    txt = "".join(out)
    print("  status %s, %.1f s, %d content chars, %d reasoning chars" % (r.status, time.time() - t0, len(txt), len("".join(think))))
    return txt

def load(): return json.loads(CONV.read_text(encoding="utf-8")) if CONV.exists() else []
def save(m): CONV.write_text(json.dumps(m), encoding="utf-8")

phase = sys.argv[1]
mt = int(sys.argv[2]) if len(sys.argv) > 2 else 1800
print(time.strftime("%H:%M:%S"), "phase", phase)
if phase == "fresh":            # the 25K-token document, a new conversation
    m = [{"role": "user", "content": A + Q1}]
    a = chat(m, mt); m.append({"role": "assistant", "content": a}); save(m)
elif phase == "fresh2":         # the same prompt again, not saved (compare with the first `fresh`)
    chat([{"role": "user", "content": A + Q1}], mt)
elif phase == "short":          # a short follow-up turn in the kept conversation
    m = load(); m.append({"role": "user", "content": "Now go deeper: explain the expert cache, the adaptive tier and the prompt path in much more detail, at least 1500 words. " + (sys.argv[3] if len(sys.argv) > 3 else "")})
    a = chat(m, mt); m.append({"role": "assistant", "content": a}); save(m)
elif phase == "big-abort":      # a turn that adds the 19K-token document; the client leaves mid-read
    m = load(); m.append({"role": "user", "content": B + "\n\nCompare this manual with the specification above, in detail."})
    chat(m, mt, abort_after=float(sys.argv[3]) if len(sys.argv) > 3 else 10.0)
elif phase == "big":            # the same turn (a few tokens longer), read to the end
    m = load(); m.append({"role": "user", "content": B + "\n\nCompare this manual with the specification above, in detail. Write at least 1500 words and be concrete."})
    a = chat(m, mt); m.append({"role": "assistant", "content": a}); save(m)
elif phase == "grow":           # one more turn that adds block k (about 4K tokens of new text) to the kept conversation
    k = int(sys.argv[3])
    src = (ROOT / "SPEC.md").read_text(encoding="utf-8", errors="replace")[88000:] + (ROOT / "docs/DETAILS.md").read_text(encoding="utf-8", errors="replace")
    blk = src[k * 14000:(k + 1) * 14000]
    m = load(); m.append({"role": "user", "content": "More of the documentation follows.\n\n" + blk + "\n\nSummarize this new part in about 350 words: the mechanisms and the numbers."})
    a = chat(m, mt); m.append({"role": "assistant", "content": a}); save(m)
elif phase == "aux":            # a short unrelated request in between (as an agent's title / helper call), not saved
    t = (ROOT / "README.md").read_text(encoding="utf-8", errors="replace")[:1800 + 200 * int(sys.argv[3] if len(sys.argv) > 3 else 0)]
    chat([{"role": "user", "content": t + "\n\nПридумай короткий заголовок для этого текста, 5-8 слов."}], mt)
elif phase == "bfresh-abort":   # the second document alone as a NEW conversation; the client leaves mid-read
    chat([{"role": "user", "content": B + "\n\nSummarize this manual in detail, at least 1000 words."}], mt, abort_after=float(sys.argv[3]) if len(sys.argv) > 3 else 10.0)
elif phase == "bfresh":         # the same new conversation, read to the end
    chat([{"role": "user", "content": B + "\n\nSummarize this manual in detail, at least 1000 words. Be concrete."}], mt)
