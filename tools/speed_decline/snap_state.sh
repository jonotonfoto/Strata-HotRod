#!/bin/bash
# Copy the engine's learned-state files into state-snap/ (run while the server is stopped). restore_snap.sh puts them back
# before a run, so that every run of a comparison starts from the same learned expert profile.
S="$(cd "$(dirname "$0")" && pwd)"
R="$(cd "$S/../.." && pwd)"
mkdir -p "$S/state-snap/root" "$S/state-snap/pack"
cp -p "$R/expert-profile-ud-q4-learned.bin" "$R/layer-live.bin" "$R"/predictor-*.bin "$R/ram-reserve.json" "$S/state-snap/root/"   && cp -p "$R/Strata-data/packs/ud-q4_k_xl/online-tune.txt" "$S/state-snap/pack/" && echo "snapshot written to $S/state-snap"
