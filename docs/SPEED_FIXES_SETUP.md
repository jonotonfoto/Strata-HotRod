# Installing this fork's speed fixes (for an AI agent or a person)

This fork adds a few engine changes that keep the decode speed from falling during long agent sessions, plus two
Windows fixes. They are **not** in the ready-made engine that setup downloads: the engine has to be compiled from
this source, and the speed fixes have to be switched on in the server's config. Nothing here is automatic.

Everything below was measured on one PC only: RTX 4080 SUPER 16 GB, 64 GB RAM, Windows 10, Qwen3.8-Flash-Next
UD-Q4_K_XL, `--resident-budget-gib 38`, `--adapt-async 1`. On other cards, other RAM sizes or Linux the numbers are
not measured. The full record (in Russian) is [SPEED_DECLINE.md](SPEED_DECLINE.md) and
[SPEED_DECLINE_PLAN.md](SPEED_DECLINE_PLAN.md).

## 1. Which branch

- `speed-decline-fixes` - the state every measurement here was taken on. Use this one.
- `main` of this fork - the same commits merged with the upstream `main`. See the note at the end of this file for
  whether that merge has been built and checked.

```
git clone -b speed-decline-fixes https://github.com/jonotonfoto/Strata-HotRod.git
```

In an existing checkout: `git fetch <this fork> speed-decline-fixes` and `git switch speed-decline-fixes`.

## 2. Compile the engine from this source

Follow [AI_SETUP.md](AI_SETUP.md) as usual, with one extra flag: **`--build`** ("compile the engine instead of using
the ready-made one"). Without it setup downloads the upstream ready-made engine, which has none of these changes.

```
Windows:  START-HERE.bat --yes --family unsloth --model UD-Q4_K_XL --build --no-start
Linux:    ./setup.sh --yes --family unsloth --model UD-Q4_K_XL --build --no-start
```

Pick `--family` / `--model` for the user's RAM as AI_SETUP.md says; the fixes do not depend on the model.
Setup offers to install the build tools and compiles for 20-40 minutes; `--yes` accepts. After a later `git pull`,
run setup again with `--build`: only the changed files are compiled.

How to tell the engine is the compiled one: `engine/BUILD.json` has `"source": "local"`.

What works right after the build, with nothing to switch on (Windows only; other platforms did not need them):

- learned state files are replaced on every save (`std::rename` did not replace an existing file on Windows, so the
  learned expert profile, the predictor and the tuner state were written once and never again);
- `generate.cpp` compiles with MSVC (`setenv` / `sysconf` shims).

## 3. Switch the speed fixes on

They are opt-in. Add them to the `"env"` object of the server's config - the `strata-<model>.json` file setup wrote in
the Strata folder - and restart the server. Do not replace the file: it holds the API key and the engine arguments.
[tools/speed_decline/env.example.json](../tools/speed_decline/env.example.json) has the same block ready to copy.

```json
"env": {
  "STRATA_RAM_ADAPT": "4",
  "STRATA_RAM_UPKEEP_GAP": "1",
  "STRATA_RAM_ADAPT_FILL": "1",
  "STRATA_TAIL_GUARD": "1",
  "STRATA_TAIL_MIN_TOKENS": "32",
  "STRATA_RAM_STATS": "1"
}
```

Keep whatever the config's `"env"` already has; add these keys beside it. Values are strings.

| Variable | What it does | What was measured |
| --- | --- | --- |
| `STRATA_RAM_ADAPT=4` | upstream's own opt-in: the set of experts kept in RAM follows the conversation (up to 4 moves before a window) | alone, with a round every window, it moved 0 experts - it needs the next line |
| `STRATA_RAM_UPKEEP_GAP=1` | gives that upkeep a tick between two rounds of the asynchronous adaptive tier | a 22-step agent-shaped load with one context compression: 59.5 tok/s after the compression instead of 48.2; 2,627 experts moved |
| `STRATA_RAM_ADAPT_FILL=1` | the upkeep first fills RAM places that the refill after a prompt read left empty | 19 places free at the end of the same load instead of 257; in a live session without it 1,397 of 12,956 places were empty after 33 requests. The effect on speed in a long session is not measured |
| `STRATA_TAIL_GUARD=1` | the cache slots are not re-planned from a prompt read that was cancelled, nor from a very short last chunk | after another conversation's read was cancelled 10 s in: 72.6 and 70.0 tok/s instead of 15.1 and 16.8 |
| `STRATA_TAIL_MIN_TOKENS=32` | what counts as "very short" for the line above | the value 32 is **not** measured; the default (256) also skipped the plan on ordinary short follow-up reads |
| `STRATA_RAM_STATS=1` | one diagnostic line per request (step 4) | - |

Not in the block above: `STRATA_RAM_ADAPT_KEEP=1` (keeps the agent conversation's experts in RAM while a helper request
such as a context summary runs). It is in the code but its measurement was not finished when this file was written;
see SPEED_DECLINE_PLAN.md, section 7, before turning it on.

When these apply: the engine keeps part of the experts in RAM and reads the rest from the SSD (`--resident-budget-gib`
in the config's `"args"`, the usual case when RAM is smaller than the model), on one GPU, with `--adapt-async 1`.
With every expert in VRAM or RAM there is nothing for them to do. They do nothing with a layer split, a helper GPU or
`--batch`. Do not add `--adapt-every`: these were measured with the default (a round every window).

Never expose the server beyond `127.0.0.1` without `--api-key` (AGENTS.md).

## 4. Check in the log that they work

The engine log is the file named by `"log"` in the config (`strata-<model>.log` in the Strata folder). Send two or
three requests, then look for:

| Line in the log | Means |
| --- | --- |
| `strata serve: RAM stats: N experts held in RAM, M places free; ...` | the compiled engine has the changes and `STRATA_RAM_STATS` is on. No such line: the engine is the ready-made one, or the variable is not in `"env"`, or the engine keeps no RAM copy of experts on this PC (then these fixes have nothing to do) |
| in that line: `... K gaps left between rounds (STRATA_RAM_UPKEEP_GAP)` with K above 0 and growing | the upkeep gap works |
| `strata serve: resident RAM: N experts moved in from the file in place of unused ones (STRATA_RAM_ADAPT)` with N growing | the RAM set follows the conversation |
| in the stats line: `the refills freed X RAM places, Y were filled again (STRATA_RAM_ADAPT_FILL)` with Y close to X | free places are being filled |
| `prompt tail: ... [STRATA_TAIL_GUARD: no plan from a cancelled read]` | appears only after a request was cancelled while its prompt was being read; then the guard worked |

`python tools/speed_decline/req_table.py <log line of the last "engine started">` prints one row per request (context,
tokens read, tok/s, VRAM hit rate, RAM and file blobs per token). Healthy: a hit rate of 82-88% and up to 5-6 file
blobs per token on requests that read little. File blobs per token climbing hour after hour is the decline these
fixes are for.

## 5. What these do not fix

- Short answers (100-400 tokens) run slower than long ones (26-44 tok/s against 48-58 here): the first windows after
  a prompt read are slow.
- A client that changes text in the middle of the conversation makes the engine read it again from the last
  checkpoint (seen: 73-77K tokens, about 130 s, on every turn).
- A very long helper request between two turns (seen: a 13,003-token summary) still pulls the RAM set toward itself;
  `STRATA_RAM_ADAPT_KEEP` is meant for that and is not measured yet.
- On Windows the file tier's read-ahead workers do not exist (`set_io_prefetch` has a Linux-only body), so predicted
  experts are neither read ahead nor promoted into RAM. Not changed here.

## Note on `main`

2026-11-25: the merge of `speed-decline-fixes` with the upstream `main` was built from scratch (CUDA, Windows 10, RTX
4080 SUPER) and given one short check with the block of section 3: the engine loads the model, the `RAM stats` line
appears, 34 freed RAM places of 34 were filled again, and after another conversation's read was cancelled 10 s in the
first conversation ran at 70.6 and 78.3 tok/s (`tools/speed_decline/results/28-merged-main-guard-test.txt`). That is
all that was checked on `main`: the agent-shaped loads and every other number in this file were measured on
`speed-decline-fixes` before the merge, and the HIP and SYCL backends and Linux were not built.
