"""prompt_trace.py - an opt-in diagnostic: WHICH part of a request's prompt changed since earlier requests.

Why: the engine resumes a conversation only from a checkpoint or from its live end, so one changed token near the start of
a prompt makes it read everything again, and its log says only how many tokens were reused - not what changed.  This trace
names the piece.  Off by default (the config's "prompt_trace_path", or STRATA_PROMPT_TRACE in the server's environment);
when off nothing here runs and the prompt, its tokens and the engine's request are what they were.

What it does when on, for every request the server encodes for the engine:
  * cuts the rendered prompt into pieces where the template itself puts boundaries: each tool definition, each section of
    the system text (a line that starts with '#', or a line that is one <tag>), each message of the history, and the open
    turn the model is about to write;
  * writes one JSON line to the trace file with every piece's kind, name, length and a hash - never its text;
  * compares the prompt with the previous request and with the closest of the last few requests (several conversations
    can alternate on one engine): the number of tokens they start with in common, and the first piece that differs -
    changed in place, inserted, removed, or simply appended to;
  * prints one line to the server's window.

Reading the file: tools/prefill_timing or the journal's scripts read it; `python -m serve.prompt_trace FILE` prints a
summary of the differences it holds.
"""
import hashlib
import json
import os
import re
import sys
import threading
import time

IM_START = "<|im_start|>"
IM_END = "<|im_end|>"
TOOLS_OPEN = "<tools>"
TOOLS_CLOSE = "</tools>"
_TOOL_NAME = re.compile(r'"name"\s*:\s*"([^"]{1,80})"')
_SECTION = re.compile(r"^(#{1,6} .{0,60}|<[A-Za-z_][\w\-]{0,40}>)\s*$")
MAX_BYTES = 256 * 2 ** 20          # the file stops growing here (a trace left on for weeks must not fill a drive)


def _hash(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8", "surrogatepass"), digest_size=6).hexdigest()


def _system_cuts(body: str) -> list[tuple[int, str, str]]:
    """Cut points inside the first system turn, as (offset, kind, name): the text before the tool list, each tool, the
    text after the list by sections."""
    cuts = [(0, "system", "start")]
    a = body.find(TOOLS_OPEN)
    b = body.find(TOOLS_CLOSE, a + 1) if a >= 0 else -1
    rest = 0
    if a >= 0 and b > a:
        at = a + len(TOOLS_OPEN)
        cuts.append((a, "tools", "open"))
        for line in body[at:b].split("\n"):
            if line.strip():
                m = _TOOL_NAME.search(line)
                cuts.append((at, "tool", m.group(1) if m else "?"))
            at += len(line) + 1
        cuts.append((b, "tools", "close"))
        rest = b + len(TOOLS_CLOSE)
    at = rest
    for line in body[rest:].split("\n"):
        if _SECTION.match(line) and at > rest:
            cuts.append((at, "system", line.strip()[:48]))
        at += len(line) + 1
    return cuts


def split_prompt(text: str) -> list[list]:
    """The prompt as pieces [kind, name, chars, hash], in order; the lengths add up to len(text)."""
    cuts: list[tuple[int, str, str]] = []
    starts = [m.start() for m in re.finditer(re.escape(IM_START), text)]
    if not starts or starts[0] > 0:
        cuts.append((0, "head", ""))
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(text)
        role = text[s + len(IM_START):s + len(IM_START) + 24].split("\n", 1)[0].strip()[:16]
        if i == 0 and role == "system":
            cuts += [(s + off, kind, name) for off, kind, name in _system_cuts(text[s:e])]
        elif i + 1 == len(starts) and IM_END not in text[s:e]:
            cuts.append((s, "open", f"{i}:{role}"))      # the turn the model is about to write (the generation prompt)
        else:
            cuts.append((s, "message", f"{i}:{role}"))
    cuts = sorted(set(cuts), key=lambda c: c[0])
    out, seen = [], set()
    for k, (at, kind, name) in enumerate(cuts):
        if at in seen:
            continue
        seen.add(at)
        end = next((c[0] for c in cuts[k + 1:] if c[0] > at), len(text))
        if end > at:
            out.append([kind, name, end - at, _hash(text[at:end])])
    return out


def common_tokens(a: list[int], b: list[int]) -> int:
    """How many tokens the two prompts start with in common (whole blocks first: a 100K-token prompt in about a millisecond)."""
    n = min(len(a), len(b))
    i = 0
    while i + 4096 <= n and a[i:i + 4096] == b[i:i + 4096]:
        i += 4096
    while i < n and a[i] == b[i]:
        i += 1
    return i


def first_difference(was: list[list], now: list[list]) -> dict:
    """Where `now` stops being `was`, and what kind of change it is."""
    hw, hn = [p[3] for p in was], [p[3] for p in now]
    i = 0
    while i < len(hw) and i < len(hn) and hw[i] == hn[i]:
        i += 1
    chars = sum(p[2] for p in now[:i])
    if i == len(hw) and i == len(hn):
        return {"what": "same", "index": i, "chars_before": chars}
    if i == len(hw):
        return {"what": "appended", "index": i, "chars_before": chars, "now": now[i][:3], "added_pieces": len(hn) - i}
    if i == len(hw) - 1 and was[i][0] == "open":       # the open turn of `was` is where the model's answer went: a continuation
        return {"what": "appended", "index": i, "chars_before": chars, "now": now[i][:3], "added_pieces": len(hn) - i}
    if i == len(hn):
        return {"what": "shorter", "index": i, "chars_before": chars, "was": was[i][:3], "dropped_pieces": len(hw) - i}
    if hw[i + 1:] == hn[i + 1:]:
        what = "changed"            # one piece differs, everything after it is the same
    elif hw[i:i + 3] == hn[i + 1:i + 4]:
        what = "inserted"           # a piece appeared, the old ones follow
    elif hw[i + 1:i + 4] == hn[i:i + 3]:
        what = "removed"            # a piece went away, the later ones follow
    else:
        what = "diverged"           # from here on it is another text
    return {"what": what, "index": i, "chars_before": chars, "was": was[i][:3], "now": now[i][:3],
            "pieces_in_common_after": len(set(hw[i:]) & set(hn[i:]))}


class PromptTrace:
    def __init__(self, path: str, keep: int = 8):
        self.path = path
        self.keep = keep
        self.recent: list[dict] = []        # the last `keep` prompts: ids and pieces (in RAM only)
        self.n = 0
        self.lock = threading.Lock()
        self.full = False
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def record(self, text: str, ids: list[int]) -> dict | None:
        """Never raises into the request: a failed trace is said once and the request goes on."""
        try:
            return self._record(text, ids)
        except Exception as e:                                   # noqa: BLE001 - a diagnostic must not break a request
            print(f"[strata] prompt trace failed ({type(e).__name__}: {e}); the request goes on", flush=True)
            return None

    def _record(self, text: str, ids: list[int]) -> dict:
        pieces = split_prompt(text)
        with self.lock:
            self.n += 1
            rec = {"t": round(time.time(), 3), "n": self.n, "tokens": len(ids), "chars": len(text),
                   "tools": sum(1 for p in pieces if p[0] == "tool"),
                   "messages": sum(1 for p in pieces if p[0] == "message")}
            if self.recent:
                prev = self.recent[-1]
                best = max(reversed(self.recent), key=lambda r: common_tokens(r["ids"], ids))   # a tie goes to the newest
                rec["prev"] = dict(first_difference(prev["pieces"], pieces), n=prev["n"],
                                   common_tokens=common_tokens(prev["ids"], ids), tokens=len(prev["ids"]))
                if best is not prev:
                    rec["best"] = dict(first_difference(best["pieces"], pieces), n=best["n"],
                                       common_tokens=common_tokens(best["ids"], ids), tokens=len(best["ids"]))
            rec["pieces"] = pieces
            self.recent.append({"n": self.n, "ids": list(ids), "pieces": pieces})
            del self.recent[:-self.keep]
            self._write(rec)
        self._say(rec)
        return rec

    def _write(self, rec: dict) -> None:
        if self.full:
            return
        if os.path.exists(self.path) and os.path.getsize(self.path) > MAX_BYTES:
            self.full = True
            print(f"[strata] prompt trace: {self.path} reached {MAX_BYTES >> 20} MiB, nothing more is written", flush=True)
            return
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")

    @staticmethod
    def _say(rec: dict) -> None:
        d = rec.get("best") or rec.get("prev")
        if not d:
            print(f"[strata] prompt trace: {rec['tokens']} tokens, {rec['tools']} tools, the first prompt traced", flush=True)
            return
        piece = d.get("now") or d.get("was") or ["", "", 0]
        which = "the closest of the last requests" if "best" in rec else "the previous request"
        print(f"[strata] prompt trace: {rec['tokens']} tokens, {rec['tools']} tools; starts like {which} for "
              f"{d['common_tokens']} of its {d['tokens']} tokens; first difference: {d['what']}"
              + (f" at piece {d['index']} ({piece[0]} {piece[1]})" if d["what"] not in ("same", "appended") else ""), flush=True)


def from_config(cfg: dict, root: str) -> "PromptTrace | None":
    """The trace the config or the environment asks for, or None (the default)."""
    path = cfg.get("prompt_trace_path") or os.environ.get("STRATA_PROMPT_TRACE") or ""
    if not path or str(path) == "0":
        return None
    if str(path) == "1":
        path = "prompt-trace.jsonl"
    if not os.path.isabs(path):
        path = os.path.join(cfg.get("cwd") or root, path)
    return PromptTrace(path)


def summary(path: str) -> None:
    """`python -m serve.prompt_trace FILE`: the differences a trace file holds, counted."""
    import collections
    kinds = collections.Counter()
    where = collections.Counter()
    n = 0
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        d = r.get("best") or r.get("prev")
        if not d:
            continue
        n += 1
        kinds[d["what"]] += 1
        if d["what"] not in ("same", "appended"):
            p = d.get("now") or d.get("was")
            where[f"{d['what']}: {p[0]} {p[1] if p[0] != 'message' else ''}".strip()] += 1
    print(f"{n} requests compared")
    for k, v in kinds.most_common():
        print(f"  {v:5d}  {k}")
    print("first differing piece, when the prompt did not simply continue:")
    for k, v in where.most_common(30):
        print(f"  {v:5d}  {k}")


if __name__ == "__main__":
    summary(sys.argv[1])
