#!/bin/bash
# run_cfg.sh <label> [VAR=VALUE ...]: restart the HotRod server with the given extra environment (the config file is
# not touched), run the probe / decode / reads / probe sequence, print the per-request table, stop the server.
S="$(cd "$(dirname "$0")" && pwd)"
R="$(cd "$S/../.." && pwd)"
L="$R/strata-ud-q4_k_xl.log"
label="$1"; shift
stop_server() {
  powershell -NoProfile -Command "\$ids = Get-CimInstance Win32_Process | Where-Object { (\$_.Name -eq 'python.exe' -and \$_.CommandLine -like '*Strata-HotRod*serve*server.py*--engine strata*') } | Select-Object -ExpandProperty ProcessId; foreach (\$i in \$ids) { Stop-Process -Id \$i -Force -ErrorAction SilentlyContinue }; \$t=0; while ((Get-Process strata -ErrorAction SilentlyContinue) -and \$t -lt 25) { Start-Sleep -Seconds 1; \$t++ }; if (Get-Process strata -ErrorAction SilentlyContinue) { Get-Process strata | Where-Object { \$_.Path -like 'H:\Ai\Strata-HotRod\engine\*' } | Stop-Process -Force; 'engine had to be stopped' } else { 'server stopped, engine exited after ' + \$t + ' s' }; Start-Sleep -Seconds 3"
}
echo "== $(date +%H:%M:%S) config $label: $*"
stop_server
bash "$S/restore_snap.sh"
cd "$R" || exit 1
env "$@" STRATA_DECODE_TIMING=1 STRATA_VERIFY_PROFILE=1 ./.venv/Scripts/python.exe serve/server.py --engine strata --config "$(cygpath -w "$R/strata-ud-q4_k_xl.json")" --host 0.0.0.0 --port 8081 > "$S/server-$label.out" 2>&1 &
cd "$S" || exit 1
t0=$(date +%s); ok=0
while [ $(( $(date +%s) - t0 )) -lt 420 ]; do sleep 5; if python replay.py health 2>/dev/null | grep -q '"loaded": true'; then ok=1; break; fi; done
echo "loaded=$ok after $(( $(date +%s) - t0 )) s"
[ "$ok" = 1 ] || { tail -5 "$S/server-$label.out"; exit 1; }
python replay.py run "$label-p1" && python replay.py run "$label-p2" \
 && python replay.py run "$label-d1" && python replay.py run "$label-d2" && python replay.py run "$label-d3" \
 && python stress.py reads 30 5000 | tail -1 \
 && python replay.py run "$label-r1" && python replay.py run "$label-r2"
n=$(tr -d '\000' < "$L" | grep -n "engine started" | tail -1 | cut -d: -f1)
echo "-- engine run starts at log line $n"
python "$S/req_table.py" $((n-1)) | awk -F'|' 'NR<=2 || ($2+0) >= 200' | cut -c1-200
tr -d '\000' < "$L" | tail -n +"$n" | grep "STRATA_RAM_ADAPT\|LOAN_SPILL\|moved in from the file\|ram evictions [1-9]\|STOP pending\|decode timing" | cut -c1-330 | tail -6
tr -d '\000' < "$L" | tail -n +"$n" | grep "work done" | tail -1 | cut -c1-260
stop_server
echo "== $(date +%H:%M:%S) config $label done"
