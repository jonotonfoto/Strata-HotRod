#!/bin/bash
# with_server.sh <label> <config file> <command ...>: stop the HotRod server, put the learned files back to the snapshot,
# start the server with that config (and the variables in $EXTRA, e.g. EXTRA="STRATA_DECODE_TIMING=1"), wait until the
# model is loaded, run the command from this folder, print the request table of this engine run, stop the server.
# The config is a file written by make_cfg.py (the engine exe, its arguments and its environment are in it).
S="$(cd "$(dirname "$0")" && pwd)"
R="$(cd "$S/../.." && pwd)"
L="$R/strata-ud-q4_k_xl.log"
label="$1"; cfgfile="$2"; shift; shift
stop_server() {
  powershell -NoProfile -Command "\$ids = Get-CimInstance Win32_Process | Where-Object { (\$_.Name -eq 'python.exe' -and \$_.CommandLine -like '*Strata-HotRod*serve*server.py*--engine strata*') } | Select-Object -ExpandProperty ProcessId; foreach (\$i in \$ids) { Stop-Process -Id \$i -Force -ErrorAction SilentlyContinue }; \$t=0; while ((Get-Process strata -ErrorAction SilentlyContinue) -and \$t -lt 25) { Start-Sleep -Seconds 1; \$t++ }; if (Get-Process strata -ErrorAction SilentlyContinue) { Get-Process strata | Where-Object { \$_.Path -like 'H:\Ai\Strata-HotRod\engine*' } | Stop-Process -Force; 'engine had to be stopped' } else { 'server stopped, engine exited after ' + \$t + ' s' }; Start-Sleep -Seconds 3"
}
echo "== $(date +%H:%M:%S) $label: config $(basename "$cfgfile") extra: ${EXTRA:-none}"
stop_server
bash "$S/restore_snap.sh"
cd "$R" || exit 1
env $EXTRA ./.venv/Scripts/python.exe serve/server.py --engine strata --config "$(cygpath -w "$cfgfile")" --host 0.0.0.0 --port 8081 > "$S/server-$label.out" 2>&1 &
cd "$S" || exit 1
t0=$(date +%s); ok=0
while [ $(( $(date +%s) - t0 )) -lt 420 ]; do sleep 5; if python replay.py health 2>/dev/null | grep -q '"loaded": true'; then ok=1; break; fi; done
echo "loaded=$ok after $(( $(date +%s) - t0 )) s"
[ "$ok" = 1 ] || { tail -5 "$S/server-$label.out"; exit 1; }
"$@"
n=$(tr -d '\000' < "$L" | grep -n "engine started" | tail -1 | cut -d: -f1)
echo "-- engine run starts at log line $n: $(tr -d '\000' < "$L" | sed -n "${n}p" | grep -o 'engine[^ ]*\\strata.exe' | head -1)"
python "$S/req_table.py" $((n-1)) | cut -c1-200
tr -d '\000' < "$L" | tail -n +"$n" | grep "prompt tail:\|STOP pending\|RAM stats:\|moved in from the file\|a round every" | cut -c1-330 | tail -14
stop_server
echo "== $(date +%H:%M:%S) $label finished"
