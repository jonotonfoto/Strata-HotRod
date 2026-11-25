#!/bin/bash
# Put the learned-state files back to the snapshot in state-snap/ (make it with snap_state.sh while the server is stopped) (overwrite, nothing is deleted), so every run starts the same.
S="$(cd "$(dirname "$0")" && pwd)"
R="$(cd "$S/../.." && pwd)"
cp -p "$S/state-snap/root/"* "$R/" && cp -p "$S/state-snap/pack/online-tune.txt" "$R/Strata-data/packs/ud-q4_k_xl/" && echo "learned state restored to the snapshot"
