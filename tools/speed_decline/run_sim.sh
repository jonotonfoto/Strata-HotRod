#!/bin/bash
# run_sim.sh <label> [VAR=VALUE ...]: restart the HotRod server with the given extra environment (the config file is
# not touched), run the Hermes-shaped load (hermes_sim.py), print its per-phase table, stop the server.
S="$(cd "$(dirname "$0")" && pwd)"
R="$(cd "$S/../.." && pwd)"
label="$1"; shift
stop_server() {
  powershell -NoProfile -Command "\$ids = Get-CimInstance Win32_Process | Where-Object { (\$_.Name -eq 'python.exe' -and \$_.CommandLine -like '*Strata-HotRod*serve*server.py*--engine strata*') } | Select-Object -ExpandProperty ProcessId; foreach (\$i in \$ids) { Stop-Process -Id \$i -Force -ErrorAction SilentlyContinue }; \$t=0; while ((Get-Process strata -ErrorAction SilentlyContinue) -and \$t -lt 25) { Start-Sleep -Seconds 1; \$t++ }; if (Get-Process strata -ErrorAction SilentlyContinue) { Get-Process strata | Where-Object { \$_.Path -like 'H:\Ai\Strata-HotRod\engine\*' } | Stop-Process -Force; 'engine had to be stopped' } else { 'server stopped, engine exited after ' + \$t + ' s' }; Start-Sleep -Seconds 3"
}
echo "== $(date +%H:%M:%S) sim $label: $*"
stop_server
bash "$S/restore_snap.sh"
cd "$R" || exit 1
env "$@" STRATA_DECODE_TIMING=1 STRATA_VERIFY_PROFILE=1 ./.venv/Scripts/python.exe serve/server.py --engine strata --config "${CFG:-$(cygpath -w "$R/strata-ud-q4_k_xl.json")}" --host 0.0.0.0 --port 8081 > "$S/server-sim-$label.out" 2>&1 &
cd "$S" || exit 1
t0=$(date +%s); ok=0
while [ $(( $(date +%s) - t0 )) -lt 420 ]; do sleep 5; if python replay.py health 2>/dev/null | grep -q '"loaded": true'; then ok=1; break; fi; done
echo "loaded=$ok after $(( $(date +%s) - t0 )) s"
[ "$ok" = 1 ] || { tail -5 "$S/server-sim-$label.out"; exit 1; }
python hermes_sim.py run "$label" | grep -v "^groups" | tail -45
python sim_table.py "$label"
tr -d '\000' < "$R/strata-ud-q4_k_xl.log" | tail -n 4000 | grep "moved in from the file\|STOP pending\|a round every\|work done" | tail -4 | cut -c1-200
stop_server
echo "== $(date +%H:%M:%S) sim $label done"
