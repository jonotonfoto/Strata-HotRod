"""A long-read load: one long first read from nothing, then long appended turns, as the tool results of an agent
task are.  Against whatever server is running.

    python tools/prefill_plan/load_long.py [SIZES] [FIRST_CHARS] [--config strata-MODEL.json]

SIZES        the appended turns in tokens, comma-separated (default 12000,6000,14000,20000)
FIRST_CHARS  the characters of the first read (default 130000, about 33.6K tokens of this source; 348000 is about 90K)

It prints, per call, the time it was sent and answered and the token counts, so that the engine's log lines and an
outside sampler can be matched to the call.  The texts are this folder's own serve/*.py and docs/*.md, so the token
counts move a little from version to version.  Answers are at most 60 tokens: this load measures reading."""
import sys

from common import chat, load_config, texts

cfg = load_config()
src, docs = texts()
pos = [0, 0]


def take(kind, chars):
    text = src if kind == 0 else docs
    piece = text[pos[kind]:pos[kind] + chars]
    pos[kind] += chars
    return piece


def call(name, msgs):
    out, t0, t1 = chat(cfg, msgs, 60)
    usage = out.get("usage", {})
    print("%s sent=%.2f done=%.2f %.1fs in=%s out=%s" % (name, t0, t1, t1 - t0, usage.get("prompt_tokens"), usage.get("completion_tokens")), flush=True)
    return out["choices"][0]["message"].get("content") or ""


sizes = [int(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 else [12000, 6000, 14000, 20000]
first = int(sys.argv[2]) if len(sys.argv) > 2 else 130000
msgs = [{"role": "system", "content": "You are a code assistant. After each file excerpt, answer with one short sentence saying what the excerpt is about."},
        {"role": "user", "content": "Excerpt:\n" + take(0, first)}]
msgs.append({"role": "assistant", "content": call("first", msgs)})
for i, n in enumerate(sizes):
    msgs.append({"role": "user", "content": "Excerpt:\n" + take((i + 1) % 2, int(n * 3.6))})
    msgs.append({"role": "assistant", "content": call("append%d" % n, msgs)})
