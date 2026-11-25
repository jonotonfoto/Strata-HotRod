"""A Hermes-shaped load built from the real exported session (session-export.jsonl), sent straight to the engine.

Phase A, the tool loop: the conversation starts at ~45K tokens and grows by a piece of the real history per request
  (an assistant turn with its tool results), answers cut at 600 / 1200 / 500 / 1200 tokens in turn, until the prompt
  passes Hermes's compression threshold (85% of 128,000 = 108,800 tokens).  A small unrelated request every 12 steps.
Phase B, the compression as Hermes does it: a separate summarisation request over ~86K chars of the history (answer up
  to 3000 tokens), then the conversation restarts as system prompt + summary + the recent tail, and the loop goes on
  for 10 more steps.

  python hermes_sim.py plan            - print the planned steps, send nothing
  python hermes_sim.py run <label>     - run it; steps are written to sim-<label>.json
Nothing is written outside this folder; no tools are executed (the requests carry no tool definitions)."""
import http.client, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]   # the repository root
HERE = Path(__file__).parent
cfg = json.loads((ROOT / "strata-ud-q4_k_xl.json").read_text(encoding="utf-8-sig"))
PORT, KEY, MODEL = cfg.get("port", 8081), cfg.get("api_key", ""), cfg.get("model_name")
THRESHOLD = 108800
CYCLE = [600, 1200, 500, 1200]
CAP = 12000            # one message's content, chars
START_CHARS = 190000   # ~55K tokens with the system prompt
STEP_CHARS = 4500      # a step adds at least this much real history
import os
TAIL_STEPS = int(os.environ.get('SIM_TAIL_STEPS', 6))
SUMMARY_TOKENS = int(os.environ.get('SIM_SUMMARY_TOKENS', 2000))   # the summary request's answer cap (Hermes wrote 2,936 and 13,003)
CYCLES = int(os.environ.get('SIM_CYCLES', 1))                    # compressions in one run

def ask(n):
    return ("Не вызывая инструменты: подробно и развёрнуто опиши, что показал последний результат, что из этого "
            "следует и какие шаги делать дальше. Не меньше %d слов." % n)

def norm(m):
    c = (m.get("content") or "")[:CAP]
    if m["role"] == "assistant":
        d = {"role": "assistant", "content": c}
        if m.get("tool_calls"):
            d["tool_calls"] = [{"id": t.get("id") or t.get("call_id"), "type": "function",
                                "function": {"name": t["function"]["name"], "arguments": t["function"]["arguments"][:CAP]}} for t in m["tool_calls"]]
        return d
    if m["role"] == "tool":
        return {"role": "tool", "tool_call_id": m.get("tool_call_id") or "", "content": c}
    return {"role": "user", "content": c}

def size(m):
    return len(m.get("content") or "") + sum(len(t["function"]["arguments"]) for t in m.get("tool_calls", []))

def load():
    j = json.loads((HERE / "session-export.jsonl").read_text(encoding="utf-8").splitlines()[0])
    ms = [norm(m) for m in j["messages"]]
    while ms and ms[0]["role"] != "user": ms.pop(0)
    groups, cur = [], []            # a group ends where the model would be asked to answer: before an assistant message
    for i, m in enumerate(ms):
        cur.append(m)
        nxt = ms[i + 1]["role"] if i + 1 < len(ms) else None
        if m["role"] in ("user", "tool") and nxt in ("assistant", None):
            groups.append(cur); cur = []
    return j["system_prompt"], groups

def chat(messages, max_tokens):
    body = json.dumps({"model": MODEL, "messages": messages, "stream": False, "max_tokens": max_tokens}).encode()
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=3600)
    t0 = time.time()
    c.request("POST", "/v1/chat/completions", body, {"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    r = c.getresponse(); raw = r.read(); c.close()
    if r.status != 200:
        print("HTTP", r.status, raw[:400].decode("utf-8", "replace"), flush=True); sys.exit(1)
    j = json.loads(raw)
    msg = j["choices"][0]["message"]
    return j.get("usage") or {}, (msg.get("content") or ""), time.time() - t0

def flat(groups):
    out = []
    for g in groups:
        for m in g:
            out.append("[%s] %s" % (m["role"], m.get("content") or ""))
            for t in m.get("tool_calls", []): out.append("[tool call] %s %s" % (t["function"]["name"], t["function"]["arguments"]))
    return "\n\n".join(out)

def main():
    mode = sys.argv[1]; label = sys.argv[2] if len(sys.argv) > 2 else "x"
    system, groups = load()
    dry = mode == "plan"
    print("groups: %d, chars: %d" % (len(groups), sum(size(m) for g in groups for m in g)))
    msgs = [{"role": "system", "content": system}]; gi = 0; total = len(system)
    while gi < len(groups) and total < START_CHARS:
        msgs += groups[gi]; total += sum(size(m) for m in groups[gi]); gi += 1
    steps = []; step = 0; est = total / 2.3; prompt_tokens = 0
    def one(phase, limit):
        nonlocal gi, step, est, prompt_tokens, msgs
        added = 0
        while added < STEP_CHARS:
            g = groups[gi % len(groups)]; gi += 1
            msgs += g; added += sum(size(m) for m in g)
        mt = CYCLE[step % len(CYCLE)]
        if step and step % 12 == 0:       # the small unrelated request Hermes sends now and then
            if not dry:
                u, _, dt = chat([{"role": "system", "content": "You write short titles."}, {"role": "user", "content": "Give a three-word title for this text:\n\n" + flat(groups[:3])[:1100]}], 4)
                steps.append({"phase": phase + "-aux", "prompt": u.get("prompt_tokens"), "gen": u.get("completion_tokens"), "s": round(dt, 1)})
        if dry:
            est += added / 2.3
            print("%s step %2d: +%5d chars, max_tokens %4d, prompt ~%6d tokens" % (phase, step, added, mt, est)); prompt_tokens = est
        else:
            # The question stays in the history and the answer is not echoed back: the next prompt only EXTENDS this one,
            # so the engine goes on from the checkpoint at this prompt's end.  (A prompt that changes earlier text is
            # re-read from the last checkpoint before the change - the system prompt; the first version did that.)
            msgs.append({"role": "user", "content": ask(mt)})
            u, _, dt = chat(msgs, mt)
            prompt_tokens = u.get("prompt_tokens", 0)
            steps.append({"phase": phase, "step": step, "max_tokens": mt, "prompt": prompt_tokens, "cached": (u.get("prompt_tokens_details") or {}).get("cached_tokens"), "gen": u.get("completion_tokens"), "s": round(dt, 1)})
            print("%s %s step %2d: prompt %6d (cached %s), gen %4d, %.1f s" % (time.strftime("%H:%M:%S"), phase, step, prompt_tokens, steps[-1]["cached"], steps[-1]["gen"] or 0, dt), flush=True)
            (HERE / ("sim-%s.json" % label)).write_text(json.dumps(steps), encoding="utf-8")
        step += 1
        return prompt_tokens < limit
    def compress(cycle):
        nonlocal msgs, est
        body = msgs[1:]
        cut = max(1, len(body) - 60)          # what gets summarised: everything but the recent tail
        text = flat([body[:cut]])[-86000:]
        if dry:
            print("compression %d: summarise %d chars -> up to %d tokens; then system + summary + %d recent messages (%d chars)" % (cycle, len(text), SUMMARY_TOKENS, len(body) - cut, sum(size(m) for m in body[cut:])))
            summary = "x" * 8000
        else:
            want = "Summarise this conversation history for a handoff: goals, what was done, results, errors, open items. Be detailed"
            if SUMMARY_TOKENS > 4000: want += ", step by step, at least %d words" % (SUMMARY_TOKENS // 2)
            u, summary, dt = chat([{"role": "system", "content": "You compress agent conversations into a faithful, detailed handoff summary."},
                                   {"role": "user", "content": want + ".\n\n" + text}], SUMMARY_TOKENS)
            steps.append({"phase": "C-summary", "prompt": u.get("prompt_tokens"), "gen": u.get("completion_tokens"), "s": round(dt, 1)})
            print("%s compression %d summary: prompt %s, gen %s, %.1f s" % (time.strftime("%H:%M:%S"), cycle, u.get("prompt_tokens"), u.get("completion_tokens"), dt), flush=True)
        tail = body[cut:]
        while tail and tail[0]["role"] != "user": tail.pop(0)
        msgs = [{"role": "system", "content": system},
                {"role": "user", "content": "[CONTEXT COMPACTION - REFERENCE ONLY] Earlier turns were compacted into the summary below.\n\n" + ((summary or "(empty)")[:12000])},
                {"role": "assistant", "content": "Understood. Continuing from the summary."}] + tail
        est = sum(size(m) for m in msgs) / 2.3
    while one("A", THRESHOLD) and step < 60: pass
    for cycle in range(1, CYCLES + 1):
        compress(cycle)
        if cycle < CYCLES:                 # grow to the threshold again, then the next compression
            n0 = step
            while one("B%d" % cycle, THRESHOLD) and step - n0 < 60: pass
        else:
            for _ in range(TAIL_STEPS): one("B%d" % cycle, 10 ** 9)
    if not dry: print("done: %d records in sim-%s.json" % (len(steps), label))

main()
