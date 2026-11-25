"""Replay of the finished Hermes session against the local engine.
  build           - make request.json from session-export.jsonl (system prompt + the last ~135K chars of the real history + one closing question)
  run <label> [n] - send request.json, print wall times; the engine log has the real numbers
  health          - the server's /health
Nothing is written outside this folder; the API key is read from the config and never printed."""
import http.client, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]   # the repository root
HERE = Path(__file__).parent
cfg = json.loads((ROOT / "strata-ud-q4_k_xl.json").read_text(encoding="utf-8-sig"))
PORT, KEY, MODEL = cfg.get("port", 8081), cfg.get("api_key", ""), cfg.get("model_name")
REQ = HERE / "request.json"
QUESTION = ("Не вызывая никаких инструментов, напиши подробный связный отчёт о работе, проделанной в этом разговоре: "
            "что было сделано по шагам, какие были ошибки и как их обходили, что осталось незаконченным. Не меньше 900 слов.")

def conn(timeout=1800):
    return http.client.HTTPConnection("127.0.0.1", PORT, timeout=timeout)

def build(budget_chars):
    j = json.loads((HERE / "session-export.jsonl").read_text(encoding="utf-8").splitlines()[0])
    ms = j["messages"]
    out, total = [], 0
    for m in reversed(ms):
        c = m.get("content") or ""
        total += len(c) + (len(json.dumps(m["tool_calls"])) if m.get("tool_calls") else 0)
        out.append(m)
        if total >= budget_chars and m["role"] == "user": break
    out.reverse()
    while out and out[0]["role"] != "user": out.pop(0)
    msgs = [{"role": "system", "content": j["system_prompt"]}]
    for m in out:
        c = m.get("content") or ""
        if m["role"] == "assistant":
            d = {"role": "assistant", "content": c}
            if m.get("tool_calls"):
                d["tool_calls"] = [{"id": t.get("id") or t.get("call_id"), "type": "function",
                                    "function": {"name": t["function"]["name"], "arguments": t["function"]["arguments"]}} for t in m["tool_calls"]]
            msgs.append(d)
        elif m["role"] == "tool":
            msgs.append({"role": "tool", "tool_call_id": m.get("tool_call_id") or "", "content": c})
        else:
            msgs.append({"role": "user", "content": c})
    msgs.append({"role": "user", "content": QUESTION})
    REQ.write_text(json.dumps({"model": MODEL, "messages": msgs, "stream": True, "max_tokens": 1500}, ensure_ascii=False), encoding="utf-8")
    print("messages:", len(msgs), "chars:", sum(len(m.get("content") or "") for m in msgs), "roles:", {r: sum(1 for m in msgs if m["role"] == r) for r in ("system", "user", "assistant", "tool")})

def run(label, max_tokens=None):
    body = json.loads(REQ.read_text(encoding="utf-8"))
    if max_tokens: body["max_tokens"] = max_tokens
    raw = json.dumps(body).encode()
    c = conn(); t0 = time.time()
    c.request("POST", "/v1/chat/completions", raw, {"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    r = c.getresponse()
    if r.status != 200:
        print(label, "HTTP", r.status, r.read()[:600].decode("utf-8", "replace")); return
    first = None; out = []; think = 0; usage = None
    for line in r:
        line = line.decode("utf-8", "replace").strip()
        if not line.startswith("data:"): continue
        d = line[5:].strip()
        if d == "[DONE]": break
        try: jj = json.loads(d)
        except ValueError: continue
        if jj.get("usage"): usage = jj["usage"]
        for ch in jj.get("choices", []):
            dl = ch.get("delta", {})
            if dl.get("content") or dl.get("reasoning_content") or dl.get("tool_calls"):
                if first is None: first = time.time() - t0
            if dl.get("content"): out.append(dl["content"])
            if dl.get("reasoning_content"): think += len(dl["reasoning_content"])
    c.close()
    txt = "".join(out)
    print("%s %s: first token after %.1f s, total %.1f s, %d content chars, %d reasoning chars, usage %s" % (time.strftime("%H:%M:%S"), label, first or -1, time.time() - t0, len(txt), think, usage))
    (HERE / ("answer-%s.txt" % label)).write_text(txt, encoding="utf-8")

def health():
    c = conn(10); c.request("GET", "/health", headers={"Authorization": "Bearer " + KEY}); r = c.getresponse()
    print(r.status, r.read()[:400].decode("utf-8", "replace"))

a = sys.argv[1]
if a == "build": build(int(sys.argv[2]) if len(sys.argv) > 2 else 135000)
elif a == "run": run(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else None)
elif a == "health": health()
