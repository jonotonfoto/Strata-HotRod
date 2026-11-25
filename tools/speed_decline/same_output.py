"""Test A: the same greedy requests against whatever server is running; the answers are kept to compare two engines.

    python same_output.py run <label>        - four requests at temperature 0, answers written to same-<label>.json
    python same_output.py compare <a> <b>    - which answers are the same text

The requests: a short one, a ~20K-token document with a question, the next turn of that conversation (the previous
prompt is reused), and the document again as a new conversation (a full read once more)."""
import http.client, json, sys
from pathlib import Path
HERE = Path(__file__).parent
ROOT = Path(__file__).resolve().parents[2]
cfg = json.loads((ROOT / "strata-ud-q4_k_xl.json").read_text(encoding="utf-8-sig"))
PORT, KEY, MODEL = cfg.get("port", 8081), cfg.get("api_key", ""), cfg.get("model_name")

def chat(messages, max_tokens):
    body = json.dumps({"model": MODEL, "messages": messages, "stream": False, "max_tokens": max_tokens, "temperature": 0}).encode()
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=1800)
    c.request("POST", "/v1/chat/completions", body, {"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    r = c.getresponse(); raw = r.read(); c.close()
    if r.status != 200:
        print("HTTP", r.status, raw[:300]); sys.exit(1)
    j = json.loads(raw); m = j["choices"][0]["message"]
    return (m.get("reasoning_content") or "") + "\n---\n" + (m.get("content") or ""), j.get("usage") or {}

if sys.argv[1] == "run":
    label = sys.argv[2]
    doc = (ROOT / "SPEC.md").read_text(encoding="utf-8", errors="replace")[:60000]
    out = []
    a, u = chat([{"role": "user", "content": "Name three prime numbers above 100 and explain in two sentences how you checked them."}], 200)
    out.append(("short", a, u))
    m = [{"role": "user", "content": "Here is a specification.\n\n" + doc + "\n\nList the five most important mechanisms it describes, one sentence each."}]
    a, u = chat(m, 300)
    out.append(("document", a, u))
    m2 = m + [{"role": "assistant", "content": a.split("\n---\n", 1)[1]},
              {"role": "user", "content": "Now give the single number from the document you consider most important and say why."}]
    a2, u = chat(m2, 200)
    out.append(("next turn", a2, u))
    a3, u = chat([{"role": "user", "content": "A specification follows.\n\n" + doc + "\n\nWrite one paragraph on how prompts are read."}], 250)
    out.append(("document again", a3, u))
    (HERE / ("same-%s.json" % label)).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    for n, a, u in out:
        print("%-15s prompt %6s tokens, %4s generated, %5d chars" % (n, u.get("prompt_tokens"), u.get("completion_tokens"), len(a)))
else:
    A = json.loads((HERE / ("same-%s.json" % sys.argv[2])).read_text(encoding="utf-8"))
    B = json.loads((HERE / ("same-%s.json" % sys.argv[3])).read_text(encoding="utf-8"))
    same = 0
    for (n, a, ua), (_, b, ub) in zip(A, B):
        eq = a == b; same += eq
        k = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        print("%-15s %s  (%d and %d chars%s)" % (n, "SAME" if eq else "DIFFERENT", len(a), len(b), "" if eq else ", first difference at char %d" % k))
    print("%d of %d answers are the same text" % (same, len(A)))
