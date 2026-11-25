# Installing this fork's speed fixes (for an AI agent or a person)

This fork adds a few engine changes that keep the decode speed from falling during long agent sessions, plus two
Windows fixes. They are **not** in the ready-made engine that setup downloads: the engine has to be compiled from
this source, and the speed fixes have to be switched on in the server's config. Nothing here is automatic.

Everything below was measured on one PC only: RTX 4080 SUPER 16 GB, 64 GB RAM, Windows 10, Qwen3.8-Flash-Next
UD-Q4_K_XL, `--resident-budget-gib 38`, `--adapt-async 1`. On other cards, other RAM sizes or Linux the numbers are
not measured. The full record (in Russian) is [SPEED_DECLINE.md](SPEED_DECLINE.md) and
[SPEED_DECLINE_PLAN.md](SPEED_DECLINE_PLAN.md).

## 0. From nothing, into a folder on a drive the user picks

For a PC with no Strata on it. Steps 1-4 below are the same steps in detail; this is the order to do them in.

1. **Check the PC** as [AI_SETUP.md](AI_SETUP.md) step 1 says (GPU, driver, RAM, free disk). Stop if it does not fit.
2. **Ask the user which drive and folder.** Do not pick the system drive yourself. The drive needs about 80 GB free
   for the smaller models (AI_SETUP.md); UD-Q4_K_XL's download alone is 111 GB ([MODELS.md](MODELS.md)) and the
   files setup prepares from it come on top, so ask for clearly more than that. Ideally an NVMe SSD (`Get-PSDrive -PSProvider FileSystem`
   / `df -h`). Below, `D:\AI` stands for the user's answer.
3. **Clone this fork there** - not the upstream address that AI_SETUP.md step 2 prints:

   ```
   Windows:  git clone https://github.com/jonotonfoto/Strata-HotRod.git D:\AI\Strata-HotRod
   Linux:    git clone https://github.com/jonotonfoto/Strata-HotRod.git /mnt/data/Strata-HotRod
   ```

   `main` has everything; `-b speed-decline-fixes` is the state the measurements were taken on (section 1).
4. **Pick the model** from the table in "Recommended settings" below.
5. **Run setup from that folder with `--build` and `--data-dir` on the same drive** (section 2 for the flags):

   ```
   Windows:  cd /d D:\AI\Strata-HotRod
             START-HERE.bat --yes --family <family> --model <model> --build --data-dir D:\AI\Strata-data --no-start
   Linux:    cd /mnt/data/Strata-HotRod
             ./setup.sh --yes --family <family> --model <model> --build --data-dir /mnt/data/Strata-data --no-start
   ```

   Without `--data-dir` the model files go to a `Strata-data` folder next to the Strata folder, which is the same
   drive anyway; the flag only makes it explicit.
6. **Switch the speed fixes on** (section 3), **start and verify the server** (AI_SETUP.md steps 6-7), **check the
   log** (section 4), then connect the user's apps (AI_SETUP.md step 8).

**What still lands on the system drive - tell the user before step 5.** Read from `setup.py`, not timed or sized by
us on a clean PC:

- Python for the user account, if the PC has none.
- The build tools that `--build` needs, if they are missing: Visual Studio 2022 Build Tools and the NVIDIA CUDA
  Toolkit 13.0, installed with `winget` into their default places (setup says "about 8-10 GB, 15-40 minutes" and
  Windows asks for permission); on Linux `build-essential` and the CUDA toolkit through `sudo apt`, which the user
  has to run.
- One small settings file: `%APPDATA%\Strata\settings.json` (Linux: `~/.config/strata/settings.json`). It remembers
  the data folder.

Everything else - the source, `.venv`, the compiled engine, the model files, the configs and logs - stays in the two
folders on the drive the user picked.

### Model files that are already on the PC

Ask the user before step 5 whether the model was downloaded before, and where. Read from `setup.py` and upstream's
docs; an install with such paths was not run by us.

| What the user has | Add to the setup line of step 5 | What happens |
| --- | --- | --- |
| Only the GGUF files, in a folder of their own | `--gguf-dir E:\models\UD-Q4_K_XL` (keep `--data-dir`) | setup uses the files where they are, without copying, and never deletes them. The folder must hold every shard under its original name (`<name>-00001-of-0000N.gguf` ...). Setup checks their SHA-256: only the very files it would download itself pass, another build of the same model does not. The files setup prepares from them are still made anew and go to `--data-dir`, so that drive needs room (how much per model was not checked here). One model per run: for a second model in another folder, run setup again with `--setup` and its own `--gguf-dir` |
| A whole `Strata-data` folder from an earlier Strata install | `--data-dir E:\old\Strata-data` (instead of the new one) | the GGUF files and the prepared files are found there; nothing is downloaded or prepared again |
| GGUF files wanted on one drive, everything else on another | `--models-dir E:\gguf --data-dir D:\AI\Strata-data` | `--models-dir` is the place for the GGUF files only, `--data-dir` for the rest (prepared files, the MTP layer) |

Setup remembers the data folder it used last in `%APPDATA%\Strata\settings.json` (Linux:
`~/.config/strata/settings.json`, the `data_dir` entry) and uses it again for every Strata folder on the PC. On a PC
that had Strata before, a new install without `--data-dir` therefore goes to the old folder without saying so: always
pass `--data-dir` explicitly.

### Recommended settings by VRAM and RAM

Only the last row was measured with these fixes. The model column of the other rows is upstream's recommendation by
RAM (AI_SETUP.md step 3, [DETAILS.md](DETAILS.md)); whether the fixes change anything there is not measured. Say so to
the user.

| GPU / RAM | `--family` / `--model` | Context setup picks | The speed-fix block (section 3) |
| --- | --- | --- | --- |
| 12 GB / 32 GB | `--family coder` (IQ1_M) | 32,768 | not measured. Add it, then look for the `RAM stats` line (section 4): no line means the engine keeps no RAM copy of experts here and the block does nothing |
| 16 GB / 32 GB | `--family coder` (IQ1_M) | 65,536 | the same: not measured, decide by the `RAM stats` line |
| 12 GB / 64 GB | `--family qwen --model IQ2_XS` | 32,768 | the same: not measured, decide by the `RAM stats` line. `--family unsloth --model UD-Q4_K_XL` also installs (NVIDIA, NVMe SSD); upstream measured 7-8.5 tok/s for it on an RTX 5070 12 GB with 64 GB on an older engine, and this fork has no number for 12 GB |
| 16 GB / 64 GB | `--family unsloth --model UD-Q4_K_XL` for the best answers, or `--family qwen --model IQ2_XS` (upstream's recommendation, smaller and not measured here) | 65,536 (the measurements here used 128,000: `--context 128000`) | **measured** with UD-Q4_K_XL on an RTX 4080 SUPER: the whole block of section 3, plus `STRATA_RAM_ADAPT_KEEP=1` if wanted. 60 tok/s held over 110 agent turns; 38 tok/s at the end without the block |

For all four:

- Keep the engine arguments setup wrote into `strata-<model>.json` (`--resident-budget-gib`, `--adapt-async` and the
  rest): setup sizes them for the PC's RAM and VRAM. The measured PC ran `--resident-budget-gib 38` and
  `--adapt-async 1`; do not copy 38 to a 32 GB PC.
- Do not add `--adapt-every` and do not add `STRATA_LOAN_SPILL` (section 3).
- A longer context than setup picks costs VRAM that the expert cache then does not have; on a 12 GB card raise it only
  if the user's agent needs it, and say that the speed was not measured there.
- Windows: a fixed page file (AI_SETUP.md step 9) if the engine reports `cudaMalloc ... out of memory` with free VRAM.

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

The long measurement (2026-11-25, `tools/speed_decline/results/27-long.txt` and `29-longctl.txt`): an agent-shaped load
of 110 turns through four context compressions, the context reaching 110-112K tokens four times, the same build with
and without the variables, one run each. Without them the speed fell from 63.7 to 38.0 tok/s over 65 minutes and the
file blobs per token rose from 3.2 to 13.5. With the block above plus `STRATA_RAM_ADAPT_KEEP=1` it stayed at 60 tok/s
for the whole 53 minutes (55.5-63.4 by part) with 1.7-3.2 file blobs per token. The run does not say which variable
gives which share.

Not in the block above:

- `STRATA_RAM_ADAPT_KEEP=1` (keeps the agent conversation's experts in RAM while a helper request such as a context
  summary runs). It was on in the long run above and did no harm there, but its own effect was not shown: the two runs
  made to show it (a 7,700-8,000-token summary with and without it) both ran at 54-59 tok/s after the summary.
- `STRATA_LOAN_SPILL=1` (upstream's opt-in). Do not add it to this block: with it the refills freed 19,155 RAM places
  in one 22-turn load instead of 226, 1,183 of 12,956 were still empty at the end, and the first answers after the
  compression ran at 43.9 tok/s instead of 59.9.

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

## 5. Updating later

Close the model window (a running engine cannot be replaced), then from the Strata folder:

```
Windows:  UPDATE-HOTROD.bat
Linux:    ./update-hotrod.sh
```

It does two things:

1. upstream's own `UPDATE.bat` / `update.sh`: `git pull --ff-only` from the address the folder was cloned from (it
   prints that address first; it must be this fork), then setup's update step. For an engine compiled here
   (`engine/BUILD.json` says `"source": "local"`) that step compiles the engine again when the source changed. The
   model files are not touched, and setup keeps the `"env"` entries it did not write itself.
2. `tools/speed_decline/apply_env.py`: adds the variables of
   [env.example.json](../tools/speed_decline/env.example.json) that a `strata-<model>.json` does not have yet. A
   variable that is already there keeps its value, nothing is removed, and a copy of the config is saved first as
   `<name>.json.bak-speed-fixes`. It also says whether the engine is the compiled one.

So a variable this fork adds to its recommendation later reaches an installed copy; one it withdraws does not leave by
itself - this file will say so, take it out by hand. `apply_env.py --dry-run` only prints what it would add.

Checked on Windows 10 with a stand-in for `UPDATE.bat` and a test config (both outcomes of the update, the variables
added, the other keys kept). The whole path on a real install - pull, compile, variables - and `update-hotrod.sh`
were not run.

If `git pull` stops because files were changed in the folder, `git status` lists them; the update changes nothing
until that is settled.

## 6. What these do not fix

- Short answers (100-400 tokens) run slower than long ones (26-44 tok/s against 48-58 here): the first windows after
  a prompt read are slow.
- A client that changes text in the middle of the conversation makes the engine read it again from the last
  checkpoint (seen: 73-77K tokens, about 130 s, on every turn).
- After a very long helper request between two turns (seen live: a 13,003-token summary) the next answers ran at
  18-30 tok/s. The tests did not reproduce this, so neither its cause nor a cure is established.
- On Windows the file tier's read-ahead workers do not exist (`set_io_prefetch` has a Linux-only body), so predicted
  experts are neither read ahead nor promoted into RAM. Not changed here.

## Note on `main`

2026-11-25: the merge of `speed-decline-fixes` with the upstream `main` was built from scratch (CUDA, Windows 10, RTX
4080 SUPER) and given one short check with the block of section 3: the engine loads the model, the `RAM stats` line
appears, 34 freed RAM places of 34 were filled again, and after another conversation's read was cancelled 10 s in the
first conversation ran at 70.6 and 78.3 tok/s (`tools/speed_decline/results/28-merged-main-guard-test.txt`). That is
all that was checked on `main`: the agent-shaped loads and every other number in this file were measured on
`speed-decline-fixes` before the merge, and the HIP and SYCL backends and Linux were not built.
