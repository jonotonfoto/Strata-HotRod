#!/bin/bash
# run_matrix.sh <arm> [<arm> ...]: run the named test arms one after another, each on a freshly started server from the
# learned-state snapshot, the engine in engine-test2 (the build with fixes 1-4), decode timing on.  Each arm writes
# results/<nn>-<arm>.txt.  Before every arm the Hermes log is checked: if a message came in since this script started,
# the matrix stops (the user wants the server) and says so.
S="$(cd "$(dirname "$0")" && pwd)"
EXE="${EXE:-H:\Ai\Strata-HotRod\engine-test2\strata.exe}"   # EXE=<engine> picks another build; MFLAGS / MARGS add variables / make_cfg.py arguments to every arm
HLOG="${HERMES_LOG:-$(cygpath -u "${LOCALAPPDATA:-.}")/hermes/logs/agent.log}"   # the agent's log (an inbound message stops the matrix)
START="$(date '+%Y-%m-%d %H:%M:%S')"
BASEFLAGS="STRATA_RAM_ADAPT=4 STRATA_RAM_UPKEEP_GAP=1 STRATA_RAM_STATS=1"
cd "$S" || exit 1
for arm in "$@"; do
  if [ -f "$HLOG" ] && awk -v s="$START" '($1 " " substr($2,1,8)) >= s' "$HLOG" | grep -q "inbound message"; then
    echo "== $(date +%H:%M:%S) STOPPED before arm $arm: Hermes received a message after $START"; exit 3
  fi
  cmd="python hermes_sim.py run $arm | grep -v '^groups' | tail -60; python sim_table.py $arm"
  case "$arm" in
    ctl)          n=20; flags="";                                                           env_sim="" ;;
    fill)         n=21; flags="$BASEFLAGS STRATA_RAM_ADAPT_FILL=1";                         env_sim="" ;;
    guard32)      n=22; flags="$BASEFLAGS STRATA_RAM_ADAPT_FILL=1 STRATA_TAIL_GUARD=1 STRATA_TAIL_MIN_TOKENS=32";  env_sim="" ;;
    guard256)     n=22b; flags="$BASEFLAGS STRATA_RAM_ADAPT_FILL=1 STRATA_TAIL_GUARD=1 STRATA_TAIL_MIN_TOKENS=256"; env_sim="" ;;
    longsum)      n=23; flags="$BASEFLAGS STRATA_RAM_ADAPT_FILL=1";                         env_sim="SIM_SUMMARY_TOKENS=13000" ;;
    longsumkeep)  n=24; flags="$BASEFLAGS STRATA_RAM_ADAPT_FILL=1 STRATA_RAM_ADAPT_KEEP=1"; env_sim="SIM_SUMMARY_TOKENS=13000" ;;
    spill)        n=25; flags="$BASEFLAGS STRATA_RAM_ADAPT_FILL=1 STRATA_LOAN_SPILL=1";     env_sim="" ;;
    aux)          n=26; flags="$BASEFLAGS STRATA_RAM_ADAPT_FILL=1";                         env_sim=""; cmd="python aux_test.py aux" ;;
    long)         n=27; flags="$BASEFLAGS STRATA_RAM_ADAPT_FILL=1 STRATA_RAM_ADAPT_KEEP=1 STRATA_TAIL_GUARD=1 STRATA_TAIL_MIN_TOKENS=32"; env_sim="SIM_CYCLES=4" ;;
    short)        n=30; flags="$BASEFLAGS STRATA_RAM_ADAPT_FILL=1 STRATA_RAM_ADAPT_KEEP=1 STRATA_TAIL_GUARD=1 STRATA_TAIL_MIN_TOKENS=32"; env_sim="SIM_ANSWER_TOKENS=100,200,300,150" ;;
    longctl)      n=29; flags="";                                                           env_sim="SIM_CYCLES=4" ;;
    *) echo "unknown arm $arm"; exit 2 ;;
  esac
  cfg="$(python make_cfg.py "m-$arm" "exe=$EXE" $flags $MFLAGS $MARGS | tail -1)"
  out="results/$n-$arm${SUFFIX:-}.txt"
  echo "== $(date +%H:%M:%S) arm $arm -> $out  flags: ${flags:-none}  ${env_sim}"
  EXTRA="STRATA_DECODE_TIMING=1 STRATA_VERIFY_PROFILE=1" bash with_server.sh "m-$arm" "$(cygpath -u "$cfg")" env $env_sim bash -c "$cmd" > "$out" 2>&1
  grep -A8 "^part " "$out" | cut -c1-130
  grep "RAM stats:" "$out" | tail -1 | cut -c1-520
done
echo "== $(date +%H:%M:%S) matrix finished"
