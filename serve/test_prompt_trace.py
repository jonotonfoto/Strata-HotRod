"""The prompt trace (serve/prompt_trace.py): the pieces add up to the prompt, a change is named by its piece, and
nothing is written when the trace is off.  No engine, GPU or tokenizer needed.

    python -m unittest serve.test_prompt_trace
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from serve.prompt_trace import PromptTrace, first_difference, from_config, split_prompt  # noqa: E402


def prompt(tools, system, messages, tail="<|im_start|>assistant\n<think>\n"):
    t = "<|im_start|>system\nEffort line.\n\n# Tools\n\nYou have access to the following functions:\n\n<tools>"
    for name, desc in tools:
        t += "\n" + json.dumps({"type": "function", "function": {"name": name, "description": desc}})
    t += "\n</tools>\n\nIf you choose to call a function ONLY reply in the following format.\n\n" + system + "<|im_end|>\n"
    for role, text in messages:
        t += f"<|im_start|>{role}\n{text}<|im_end|>\n"
    return t + tail


TOOLS = [("terminal", "Run a command."), ("read_file", "Read a file."), ("skill_view", "Show a skill.")]
SYSTEM = "You are an agent.\n\n# Skills\n<available_skills>\nalpha: one\nbeta: two\n</available_skills>\n\n# Runtime\ncwd: C:/work\n"
HISTORY = [("user", "hello"), ("assistant", "<think>\nhm\n</think>\n\nhi"), ("user", "do it")]


def ids_of(text):
    return [ord(c) for c in text]          # one "token" per character: enough for the common-start count


class SplitTest(unittest.TestCase):
    def test_pieces_add_up(self):
        text = prompt(TOOLS, SYSTEM, HISTORY)
        pieces = split_prompt(text)
        self.assertEqual(sum(p[2] for p in pieces), len(text))
        self.assertEqual([p[1] for p in pieces if p[0] == "tool"], ["terminal", "read_file", "skill_view"])
        self.assertEqual(sum(1 for p in pieces if p[0] == "message"), len(HISTORY))
        self.assertEqual(pieces[-1][:2], ["open", "4:assistant"])
        self.assertIn("# Skills", [p[1] for p in pieces if p[0] == "system"])
        self.assertIn("# Runtime", [p[1] for p in pieces if p[0] == "system"])

    def test_no_system_turn_and_plain_text(self):
        for text in ("plain text, no template", "<|im_start|>user\nhi<|im_end|>\n<|im_start|>assistant\n", ""):
            self.assertEqual(sum(p[2] for p in split_prompt(text)), len(text))

    def test_no_text_in_pieces(self):
        secret = "SECRET-TOKEN-12345"
        pieces = split_prompt(prompt(TOOLS, SYSTEM + secret, HISTORY + [("user", secret)]))
        self.assertNotIn(secret, json.dumps(pieces))


class DifferenceTest(unittest.TestCase):
    def diff(self, a, b):
        return first_difference(split_prompt(a), split_prompt(b))

    def test_appended(self):
        a = prompt(TOOLS, SYSTEM, HISTORY, tail="")
        b = prompt(TOOLS, SYSTEM, HISTORY + [("assistant", "ok"), ("user", "next")], tail="")
        self.assertEqual(self.diff(a, b)["what"], "appended")
        self.assertEqual(self.diff(a, a)["what"], "same")

    def test_skill_list_changed(self):
        b = prompt(TOOLS, SYSTEM.replace("beta: two", "beta: two\ngamma: three"), HISTORY)
        d = self.diff(prompt(TOOLS, SYSTEM, HISTORY), b)
        self.assertEqual((d["what"], d["now"][0]), ("changed", "system"))
        self.assertIn(d["now"][1], ("# Skills", "<available_skills>"))

    def test_tool_changed_inserted_removed(self):
        base = prompt(TOOLS, SYSTEM, HISTORY)
        d = self.diff(base, prompt([TOOLS[0], ("read_file", "Read a file, new text."), TOOLS[2]], SYSTEM, HISTORY))
        self.assertEqual((d["what"], d["now"][:2]), ("changed", ["tool", "read_file"]))
        more = TOOLS[:1] + [("browser", "Open a page."), ("patch", "Edit."), ("write_file", "Write.")] + TOOLS[1:]
        d = self.diff(prompt(more[:2] + more[3:], SYSTEM, HISTORY), prompt(more, SYSTEM, HISTORY))
        self.assertEqual((d["what"], d["now"][:2]), ("inserted", ["tool", "patch"]))
        d = self.diff(prompt(more, SYSTEM, HISTORY), prompt(more[:2] + more[3:], SYSTEM, HISTORY))
        self.assertEqual((d["what"], d["was"][:2]), ("removed", ["tool", "patch"]))

    def test_last_message_replaced(self):
        a = prompt(TOOLS, SYSTEM, HISTORY + [("user", "review the conversation")])
        b = prompt(TOOLS, SYSTEM, HISTORY + [("user", "[kanban] task crashed")])
        d = self.diff(a, b)
        self.assertEqual(d["now"][0], "message")
        self.assertEqual(d["index"], len(split_prompt(a)) - 2)


class TraceTest(unittest.TestCase):
    def test_file_and_closest_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sub", "trace.jsonl")
            tr = PromptTrace(path)
            main = prompt(TOOLS, SYSTEM, HISTORY)
            other = prompt(TOOLS[:2], "Another agent.\n", [("user", "x")])
            later = prompt(TOOLS, SYSTEM, HISTORY + [("assistant", "done"), ("user", "more")])
            for text in (main, other, later):
                self.assertIsNotNone(tr.record(text, ids_of(text)))
            with open(path, encoding="utf-8") as f:
                body = f.read()
            recs = [json.loads(line) for line in body.splitlines()]
            self.assertEqual(len(recs), 3)
            self.assertNotIn("prev", recs[0])
            self.assertNotEqual(recs[2]["prev"]["what"], "appended")        # against the other conversation
            self.assertEqual(recs[2]["best"]["n"], 1)                       # the closest one is the first request
            self.assertEqual(recs[2]["best"]["what"], "appended")
            self.assertEqual(recs[2]["best"]["common_tokens"], len(main) - len("<think>\n"))   # the open turn's header is shared too
            self.assertNotIn("hello", body)                                 # no message text in the file

    def test_off_by_default(self):
        old = os.environ.pop("STRATA_PROMPT_TRACE", None)
        try:
            self.assertIsNone(from_config({}, str(ROOT)))
            self.assertIsNone(from_config({"prompt_trace_path": ""}, str(ROOT)))
            os.environ["STRATA_PROMPT_TRACE"] = "0"
            self.assertIsNone(from_config({}, str(ROOT)))
        finally:
            os.environ.pop("STRATA_PROMPT_TRACE", None)
            if old is not None:
                os.environ["STRATA_PROMPT_TRACE"] = old

    def test_bad_input_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            tr = PromptTrace(os.path.join(tmp, "t.jsonl"))
            self.assertIsNone(tr.record(None, [1, 2, 3]))                   # a failed trace returns None, no exception


if __name__ == "__main__":
    unittest.main()
