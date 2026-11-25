"""Test Z: what a small unrelated request between two turns costs the conversation's next short answer.

The 78K probe conversation (request.json) is loaded with one long answer, then: two short answers (the baseline), a
~400-token unrelated request with a 4-token answer (as an agent's title call), two short answers again; twice.
The engine log (req_table.py, the `strata decode timing:` lines) has the numbers.

    python aux_test.py <label>"""
import http.client, json, sys, time
from pathlib import Path
HERE = Path(__file__).parent
ROOT = Path(__file__).resolve().parents[2]
cfg = json.loads((ROOT / "strata-ud-q4_k_xl.json").read_text(encoding="utf-8-sig"))
PORT, KEY, MODEL = cfg.get("port", 8081), cfg.get("api_key", ""), cfg.get("model_name")

def chat(body):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=1800)
    t0 = time.time()
    c.request("POST", "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    r = c.getresponse(); raw = r.read(); c.close()
    if r.status != 200:
        print("HTTP", r.status, raw[:300]); sys.exit(1)
    return json.loads(raw).get("usage") or {}, time.time() - t0

probe = json.loads((HERE / "request.json").read_text(encoding="utf-8"))
probe["stream"] = False
aux_text = (ROOT / "README.md").read_text(encoding="utf-8", errors="replace")[:1500]
aux = {"model": MODEL, "stream": False, "max_tokens": 4,
       "messages": [{"role": "user", "content": aux_text + "\n\nGive a three-word title for this text."}]}

def step(name, body, max_tokens=None):
    b = dict(body)
    if max_tokens: b["max_tokens"] = max_tokens
    u, dt = chat(b)
    print("%s %-28s prompt %6s, gen %4s, %6.1f s" % (time.strftime("%H:%M:%S"), name, u.get("prompt_tokens"), u.get("completion_tokens"), dt), flush=True)

print("aux test", sys.argv[1] if len(sys.argv) > 1 else "")
step("load: long answer", probe, 1500)
step("short answer (baseline 1)", probe, 200)
step("short answer (baseline 2)", probe, 200)
for k in (1, 2):
    step("unrelated small request %d" % k, aux)
    step("short answer after it (1)", probe, 200)
    step("short answer after it (2)", probe, 200)
