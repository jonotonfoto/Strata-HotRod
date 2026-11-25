#!/bin/bash
# watch.sh <need_new_requests> <timeout_s>: waits for N more finished requests (or a cancel / engine restart / timeout),
# then prints the table of the current engine run plus the lines worth a look. Reads only.
S="$(cd "$(dirname "$0")" && pwd)"
L="$R/strata-ud-q4_k_xl.log"
need=${1:-4}; tmo=${2:-420}
cnt() { tr -d '\000' < "$L" | grep -c "$1"; }
r0=$(cnt "strata serve: prompt [0-9]* tokens = "); c0=$(cnt "STOP pending"); e0=$(cnt "engine started")
t0=$(date +%s); why=timeout
while [ $(( $(date +%s) - t0 )) -lt "$tmo" ]; do
  sleep 10
  r=$(cnt "strata serve: prompt [0-9]* tokens = "); c=$(cnt "STOP pending"); e=$(cnt "engine started")
  if [ "$c" -gt "$c0" ]; then why="CANCEL seen"; sleep 20; break; fi
  if [ "$e" -gt "$e0" ]; then why="ENGINE RESTART"; break; fi
  if [ $((r - r0)) -ge "$need" ]; then why="$((r - r0)) new requests"; break; fi
done
st=$(tr -d '\000' < "$L" | grep -n "engine started" | tail -1 | cut -d: -f1)
echo "== $(date '+%H:%M:%S') stop reason: $why; engine run starts at log line $st"
python "$S/req_table.py" $((st - 1)) 2>&1 | cut -c1-240
echo "-- flagged lines of this run"
tail -n +"$st" "$L" | tr -d '\000' | grep -n -i "cancel\|STOP pending\|error\|failed\|prompt tail\|after the read\|out of memory\|Traceback\|exception\|only [0-9]* MiB of VRAM free\|conversation cache:\|evict" | grep -v "lendable slots\|a prompt chunk of" | cut -c1-250 | tail -30
echo "-- gpu"; nvidia-smi --query-gpu=memory.used,memory.free,utilization.gpu --format=csv,noheader
echo "-- last log line"; tail -n 2 "$L" | tr -d '\000' | cut -c1-250
