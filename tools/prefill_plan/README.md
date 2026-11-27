# tools/prefill_plan

What the per-request read plan (`STRATA_PREFILL_PLAN2`) was measured with. The record of the measurements is
[docs/PREFILL_PLAN.md](../../docs/PREFILL_PLAN.md) (in Russian); how to switch the plan on is
[docs/SPEED_FIXES_SETUP.md](../../docs/SPEED_FIXES_SETUP.md), section 3a.

| File | What it is |
| --- | --- |
| `env.16gb.example.json` | the three variables as measured on a 16 GB card |
| `env.12gb.example.json` | a starting block for a 12 GB card; **not measured**, to be tuned on the card |
| `load_long.py` | a long first read, then long appended turns; answers of 60 tokens. Measures reading |
| `load_check.py` | 32 graded short tasks, 5 long answers, 4 long conversations with hidden codes to find. Checks answers and decode speed |
| `check_table.py` | compares two or more outputs of `load_check.py`: graded answers, decode speed, which texts are identical |
| `read_table.py` | every prompt read in an engine log: tokens, seconds, the plan the engine chose, chunks, experts streamed and reused |
| `common.py` | shared: finds the server config, calls the running server. Never prints the API key |

All loads talk to the server that is running, on the port in the config. They read `strata-<model>.json` in the
Strata folder; with more than one config there, pass `--config strata-<model>.json`.

## Comparing two settings

The engine learns while it runs (the expert profile, the predictor, the stand-in tuner), so a second run starts from
another state than the first. For a fair pair, give both runs the same start:

1. Stop the server. Copy the learned files aside: in the Strata folder `expert-profile-*-learned.bin`,
   `layer-live.bin`, `predictor-*.bin`, `ram-reserve.json`, `mask-learn-*.bin`, `standin-tune-*.txt`,
   `standin-tune-*.txt.gate`; in the model's pack folder `online-tune.txt`.
2. Start the server with the first setting. Add `"STRATA_TRACE": "1"` to `"env"` for the `read plan` lines.
3. Run the load and keep its output and the engine log:

   ```
   python tools/prefill_plan/load_long.py > base-load.txt
   python tools/prefill_plan/read_table.py strata-<model>.log
   ```

4. Stop the server, put the learned files back, start it with the second setting, run the same load.
5. Run the first setting once more at the end: the difference between the two runs of the same setting is the noise
   to compare the change against. On the PC of the measurements two runs of one setting differed by 1-6% per read.

For the answers and the decode speed:

```
python tools/prefill_plan/load_check.py > runs/base-load.txt
python tools/prefill_plan/load_check.py > runs/plan-load.txt      (after the restart with the other setting)
python tools/prefill_plan/check_table.py runs base plan
```

`load_check.py` takes 6-7 minutes on the PC of the measurements. At temperature 0 the engine does not repeat its
own text from run to run, so compare graded answers, and compare texts only against a second run of the base.

The tables print in Russian.
