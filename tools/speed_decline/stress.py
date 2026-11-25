"""Two kinds of load between probes, to see which one moves misses from the RAM tier to the file tier.
  reads N [chars]  - a second conversation that grows by one chunk of real text per request, answer cut at 8 tokens:
                     N prompt reads (each with its slot refill), almost no decoding
The probe itself is replay.py run (the 78K request, 1500 tokens): pure decoding once its prefix is reused."""
import http.client, json, sys, time
from pathlib import Path
HERE = Path(__file__).parent
ROOT = Path(__file__).resolve().parents[2]
cfg = json.loads((ROOT / "strata-ud-q4_k_xl.json").read_text(encoding="utf-8-sig"))
PORT, KEY, MODEL = cfg.get("port", 8081), cfg.get("api_key", ""), cfg.get("model_name")

def chat(messages, max_tokens):
    body = json.dumps({"model": MODEL, "messages": messages, "stream": False, "max_tokens": max_tokens}).encode()
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=1800)
    c.request("POST", "/v1/chat/completions", body, {"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    r = c.getresponse(); raw = r.read(); c.close()
    if r.status != 200:
        print("HTTP", r.status, raw[:300]); sys.exit(1)
    return json.loads(raw).get("usage")

if sys.argv[1] == "reads":
    n = int(sys.argv[2]); size = int(sys.argv[3]) if len(sys.argv) > 3 else 5000
    text = (ROOT / "SPEC.md").read_text(encoding="utf-8", errors="replace") + (ROOT / "docs" / "DETAILS.md").read_text(encoding="utf-8", errors="replace")
    msgs = [{"role": "system", "content": "You read documents part by part. After each part you answer with the single word OK."}]
    t0 = time.time()
    for i in range(n):
        part = text[i * size:(i + 1) * size]
        if not part: break
        msgs.append({"role": "user", "content": "Part %d:\n\n%s\n\nAnswer OK." % (i + 1, part)})
        u = chat(msgs, 8)
        msgs.append({"role": "assistant", "content": "OK"})
        if i % 5 == 4 or i == n - 1: print("%s reads: %d done, %.0f s, usage %s" % (time.strftime("%H:%M:%S"), i + 1, time.time() - t0, u), flush=True)
