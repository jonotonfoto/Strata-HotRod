"""Answer and decode check for a change in how prompts are read: the same greedy requests against whatever server is
running.  Run it on the build without the change and on the build with it, then compare with check_table.py.

    python tools/prefill_plan/load_check.py [--config strata-MODEL.json] > NAME-load.txt

Three parts, temperature 0, thinking off, one attempt each:
  1. short gradable tasks (math, facts, format, Russian, code - the code is run against its tests);
  2. five long-form answers of up to 600 tokens with a fact rubric - the decode speed on long answers;
  3. four long conversations with "needles" (access codes) put into the text, a question per needle as the next
     turns, and a ~350-word summary at the end (decode at a long context).  Sizes are chosen around the points where
     STRATA_PREFILL_PLAN2 reads differently on a 16 GB card:
       A: ~9K tokens, then a ~16.7K-token appended turn (the long plan on an appended turn);
       B: ~12.7K tokens (one chunk with the plan; two chunks, layer-major, without it);
       C: ~30K tokens, D: ~45K tokens (chunks cut at other places).
Every call prints one JSON line (ASCII): id, cat, sent, done, usage, the server's timings, ok (graded) and the text.
The texts are this folder's own serve/*.py and docs/*.md, so the token counts move a little between versions."""
import json, math, random, re, subprocess, sys, tempfile
from pathlib import Path

from common import chat, load_config, texts

cfg = load_config()
src, docs = texts()


def call(id_, cat, msgs, max_tokens, grade=None):
    try:
        j, t, t1 = chat(cfg, msgs, max_tokens, thinking="none")
    except Exception as e:   # one failed call must not end the run
        print(json.dumps({"id": id_, "cat": cat, "error": "%s: %s" % (type(e).__name__, str(e)[:200])}), flush=True)
        return None
    m = j["choices"][0]["message"]
    txt = m.get("content") or ""
    ok = None
    if grade is not None:
        try:
            ok = bool(grade(txt))
        except Exception:
            ok = False
    print(json.dumps({"id": id_, "cat": cat, "sent": round(t, 2), "done": round(t1, 2), "usage": j.get("usage") or {},
                      "timings": j.get("timings") or {}, "finish": j["choices"][0].get("finish_reason"), "ok": ok,
                      "think": len(m.get("reasoning_content") or ""), "text": txt}), flush=True)
    return txt


# ---------------------------------------------------------------- part 1: short gradable tasks 
TASKS = []


def add(cat, id_, prompt, max_tokens, grade):
    TASKS.append((cat, id_, prompt, max_tokens, grade))


def num_answer(expected):
    def g(text):
        m = re.findall(r"ANSWER:\s*\$?\s*(-?[\d,]*\.?\d+)", text)
        if not m:
            return False
        try:
            return abs(float(m[-1].replace(",", "")) - expected) < 1e-6
        except ValueError:
            return False
    return g


rnd = random.Random(12345)
TAIL = "\n\nThink step by step briefly, then finish with a final line 'ANSWER: <number>'."
for i in range(2):
    a, b, x, y = rnd.randint(2, 9), rnd.randint(3, 12), rnd.randint(2, 9), rnd.randint(2, 9)
    total = a * x + b * y
    c = math.ceil(total / 10) * 10 + 10
    add("math", f"math-change-{i}", f"A shop sells pens for ${a} each and notebooks for ${b} each. Sam buys {x} pens and {y} notebooks and pays with a ${c} bill. How much change does Sam get?" + TAIL, 350, num_answer(c - total))
for i in range(2):
    s, t, u, v = rnd.choice(range(40, 95, 5)), rnd.randint(2, 5), rnd.choice(range(50, 110, 10)), rnd.randint(1, 4)
    add("math", f"math-distance-{i}", f"A train travels at {s} km/h for {t} hours and then at {u} km/h for {v} hours. What is the total distance in km?" + TAIL, 350, num_answer(s * t + u * v))
for i in range(2):
    b, m, y = rnd.randint(4, 14), rnd.choice([2, 3, 4]), rnd.choice([4, 5, 6, 8])
    S = (m * b + y) + (b + y)
    add("math", f"math-ages-{i}", f"Anna is {m} times as old as Ben. In {y} years the sum of their ages will be {S}. How old is Ben now?" + TAIL, 400, num_answer(b))
for i in range(2):
    L, W = rnd.randint(6, 15), rnd.randint(3, 10)
    add("math", f"math-rect-{i}", f"A rectangle has a perimeter of {2 * (L + W)} cm and a length of {L} cm. What is its area in square centimetres?" + TAIL, 350, num_answer(L * W))

FACTS = [("Capital of Australia?", ["canberra"]), ("Chemical symbol for gold?", ["au"]), ("In which year did World War II end in Europe?", ["1945"]),
         ("What is the atomic number of carbon?", ["6", "six"]), ("Longest river in Africa?", ["nile"]), ("In which year did the Berlin Wall fall?", ["1989"]),
         ("Who discovered penicillin?", ["fleming"]), ("How many bones does an adult human have?", ["206"])]
for i, (q, kws) in enumerate(FACTS):
    add("facts", f"fact-{i}", q + " Answer in one short sentence.", 60, (lambda kws: lambda t: any(k in t.lower() for k in kws))(kws))


def fmt_bullets(t):
    lines = [l for l in t.strip().splitlines() if l.strip()]
    return len(lines) == 3 and all(l.startswith("- ") for l in lines)


def fmt_json(t):
    try:
        return json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", t.strip())) == {"a": 1, "b": 2, "c": 3}
    except Exception:
        return False


add("format", "fmt-bullets", "Reply with exactly three bullet points, each starting with '- ', about the benefits of sleep. No other text.", 120, fmt_bullets)
add("format", "fmt-tokyo", "What is the capital of Japan? Reply with exactly one word.", 20, lambda t: re.sub(r"\W", "", t).lower() == "tokyo")
add("format", "fmt-mul", "What is 17 * 23? Reply with the number only.", 20, lambda t: t.strip().strip(".") == "391")
add("format", "fmt-json", 'Return only a valid JSON object with the keys "a", "b", "c" and the integer values 1, 2, 3.', 60, fmt_json)
add("format", "fmt-sort", "Sort these numbers in ascending order, comma-separated, nothing else: 42, 7, 19, 3, 88, 25", 60, lambda t: re.sub(r"\s", "", t.strip().strip(".")) == "3,7,19,25,42,88")
add("format", "fmt-words", "How many words are in this sentence: 'The quick brown fox jumps over the lazy dog'? Reply with the number only.", 20, lambda t: t.strip().strip(".") == "9")

RU = [("Какая столица Франции? Ответь одним словом.", ["париж"]), ("Кто написал роман «Война и мир»? Ответь коротко.", ["толстой"]),
      ("Сколько дней в високосном году? Только число.", ["366"]), ("Сколько будет 144 разделить на 12? Только число.", ["12"])]
for i, (q, kws) in enumerate(RU):
    add("russian", f"ru-{i}", q, 40, (lambda kws: lambda t: any(k in t.lower() for k in kws))(kws))

CODE = [
    ("is_palindrome", "is_palindrome(s)", "returns True if s is a palindrome, ignoring case and non-alphanumeric characters",
     'assert is_palindrome("A man, a plan, a canal: Panama") is True\nassert is_palindrome("race a car") is False\nassert is_palindrome("") is True\nassert is_palindrome("No lemon, no melon") is True'),
    ("flatten", "flatten(lst)", "flattens an arbitrarily nested list of integers into a flat list",
     "assert flatten([1, [2, [3, [4]], 5]]) == [1, 2, 3, 4, 5]\nassert flatten([]) == []\nassert flatten([[], [1]]) == [1]"),
    ("roman_to_int", "roman_to_int(s)", "converts a Roman numeral string to an integer",
     'assert roman_to_int("MCMXCIV") == 1994\nassert roman_to_int("IX") == 9\nassert roman_to_int("LVIII") == 58\nassert roman_to_int("III") == 3'),
    ("is_balanced", "is_balanced(s)", "returns True if the brackets ()[]{} in s are balanced and properly nested",
     'assert is_balanced("([]{})") is True\nassert is_balanced("([)]") is False\nassert is_balanced("((") is False\nassert is_balanced("") is True'),
    ("two_sum", "two_sum(nums, target)", "returns a tuple (i, j) with i < j of the indices of the two numbers that add up to target",
     "assert two_sum([2, 7, 11, 15], 9) == (0, 1)\nassert two_sum([3, 2, 4], 6) == (1, 2)\nassert two_sum([3, 3], 6) == (0, 1)"),
    ("merge_intervals", "merge_intervals(iv)", "merges overlapping intervals given as a list of [start, end] lists and returns the merged list sorted by start",
     "assert merge_intervals([[1, 3], [2, 6], [8, 10], [15, 18]]) == [[1, 6], [8, 10], [15, 18]]\nassert merge_intervals([[1, 4], [4, 5]]) == [[1, 5]]\nassert merge_intervals([]) == []"),
]


def code_grader(tests):
    def g(text):
        m = re.search(r"```(?:python)?\n(.*?)```", text, re.S)
        if not m:
            return False
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "t.py"
            f.write_text(m.group(1) + "\n\n" + tests + "\n", encoding="utf-8")
            try:
                return subprocess.run([sys.executable, "-I", str(f)], capture_output=True, timeout=15, cwd=td).returncode == 0
            except Exception:
                return False
    return g


for name, sig, desc, tests in CODE:
    add("code", f"code-{name}", f"Write a Python function {sig} that {desc}. Reply with one python code block only, no tests.", 420, code_grader(tests))

# ---------------------------------------------------------------- part 2: long answers 
LONG = [
    ("ww1", "Explain the main causes of World War I in five detailed paragraphs.", [r"1914", r"sarajevo", r"ferdinand", r"alliance", r"militar|arms race", r"nationalis"]),
    ("fridge", "Explain how a refrigerator works in five detailed paragraphs.", [r"refrigerant", r"compressor", r"condenser", r"evaporator", r"expansion valve|capillary", r"heat"]),
    ("photo", "Describe photosynthesis in five detailed paragraphs.", [r"chlorophyll", r"light", r"carbon dioxide", r"glucose|sugar", r"oxygen", r"chloroplast"]),
    ("internet", "Summarize the history of the internet in five detailed paragraphs.", [r"arpanet", r"1969", r"tcp", r"world wide web", r"berners-lee", r"199\d"]),
    ("vaccine", "Explain how vaccines work in five detailed paragraphs.", [r"antigen", r"antibod", r"memory", r"immune", r"pathogen|virus|bacteri", r"booster|dose|exposure"]),
]


def rubric(req):
    return lambda t: all(re.search(r, t, re.I) for r in req)


# ---------------------------------------------------------------- part 3: long conversations with needles
lrnd = random.Random(2711)
used = set()


def needles(text, fracs):
    """Put one 'access code' line into the text at each fraction of its length (at a line break); -> text, [(vault, code)]."""
    out, last, found = [], 0, []
    for f in fracs:
        cut = text.find("\n", int(len(text) * f))
        cut = len(text) if cut < 0 else cut
        while True:
            n = lrnd.randint(100, 999)
            if n not in used:
                used.add(n)
                break
        code = f"{lrnd.randint(10000, 99999)}-{lrnd.choice('XQZKW')}"
        out.append(text[last:cut] + f"\nNote: the access code for vault {n} is {code}.")
        found.append((n, code))
        last = cut
    return "".join(out) + text[last:], found


def q(n):
    return f"What is the access code for vault {n}? Reply with the code only."


def has(code):
    return lambda t: code in t


SYS = {"role": "system", "content": "You are a careful assistant. You are given long documents and answer questions about them exactly."}
SUMMARY = "Now describe in about 350 words what the text above contains: its main parts and what each of them is for."


def converse(cid, first_text, first_needles, order, more=None):
    """One conversation: the document and a question, the other needles as the next turns, then a summary."""
    msgs = [SYS, {"role": "user", "content": "Document:\n" + first_text + "\n\n" + q(first_needles[order[0]][0])}]
    a = call(f"{cid}-first", "needle", msgs, 30, has(first_needles[order[0]][1]))
    if a is None:
        return
    msgs.append({"role": "assistant", "content": a})
    for k in order[1:]:
        n, code = first_needles[k]
        msgs.append({"role": "user", "content": q(n)})
        a = call(f"{cid}-n{k}", "needle", msgs, 30, has(code))
        if a is None:
            return
        msgs.append({"role": "assistant", "content": a})
    if more:   # a long appended turn with its own needles, then questions about both parts
        text2, nd2 = more
        msgs.append({"role": "user", "content": "The document continues:\n" + text2 + "\n\n" + q(nd2[1][0])})
        a = call(f"{cid}-append", "needle", msgs, 30, has(nd2[1][1]))
        if a is None:
            return
        msgs.append({"role": "assistant", "content": a})
        for tag, (n, code) in (("p1", first_needles[order[0]]), ("p2a", nd2[0]), ("p2c", nd2[2]), ("p1b", first_needles[order[-1]])):
            msgs.append({"role": "user", "content": q(n)})
            a = call(f"{cid}-{tag}", "needle", msgs, 30, has(code))
            if a is None:
                return
            msgs.append({"role": "assistant", "content": a})
    msgs.append({"role": "user", "content": SUMMARY})
    call(f"{cid}-summary", "summary", msgs, 520)


if __name__ == "__main__":
    for cat, id_, prompt, mt, grade in TASKS:
        call(id_, cat, [{"role": "user", "content": prompt}], mt, grade)
    for lid, prompt, req in LONG:
        call("long-" + lid, "longform", [{"role": "user", "content": prompt}], 600, rubric(req))
    # A: ~9K tokens of code, then ~16.7K tokens of docs as an appended turn
    a1, na1 = needles(src[200000:236000], (0.1, 0.5, 0.9))
    a2, na2 = needles(docs[43200:93600], (0.08, 0.55, 0.93))
    converse("A", a1, na1, (1, 0, 2), (a2, na2))
    # B: ~12.7K tokens of docs: between the one-chunk limits with and without the plan on a 16 GB card
    b, nb = needles(docs[0:43200], (0.04, 0.22, 0.41, 0.6, 0.79, 0.97))
    converse("B", b, nb, (3, 0, 5, 1, 4, 2))
    # C: ~30K tokens of code; needles also near the chunk borders of both builds (10 240 / 11 776 and their doubles)
    c, nc = needles(src[0:115000], (0.05, 0.34, 0.39, 0.68, 0.785, 0.95))
    converse("C", c, nc, (2, 5, 0, 3, 1, 4))
    # D: ~45K tokens of code
    d, nd = needles(src[300000:475000], (0.1, 0.2275, 0.455, 0.52, 0.68, 0.91))
    converse("D", d, nd, (4, 1, 3, 0, 5, 2))
