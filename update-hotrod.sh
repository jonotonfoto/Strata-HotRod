#!/bin/sh
# Update a copy of this fork that was installed as docs/SPEED_FIXES_SETUP.md says:
#   1. ./update.sh: the newest code from the address this folder was cloned from (git pull), then the engine is
#      compiled again if its source changed, and the Python packages and each model's settings are brought up to date;
#   2. tools/speed_decline/apply_env.py: the speed-fix variables this fork recommends are added to the "env" of every
#      strata-<model>.json that does not have them yet (a value that is already there is kept; a copy of the config is
#      saved first as <name>.json.bak-speed-fixes).
# Stop the model first: a running engine should not be replaced. The model files are not touched.
# Options are passed on to ./update.sh (and from there to setup.py).
cd "$(dirname "$0")" || exit 1
# all of it in a function, read before it runs: the git pull below can change this very file
main() {
  if [ -e .git ] && command -v git >/dev/null 2>&1; then
    echo "Updating from: $(git remote get-url origin 2>/dev/null)"
  fi
  # ./update.sh ends with `exec`, so it runs in its own shell here and this script goes on after it
  if ! sh ./update.sh "$@"; then
    echo
    echo "The update did not finish (the reason is above): the variables were not touched."
    exit 1
  fi
  echo
  echo "The speed-fix variables:"
  if [ -x .venv/bin/python ]; then
    .venv/bin/python tools/speed_decline/apply_env.py
  else
    echo "No .venv here yet: install first (docs/SPEED_FIXES_SETUP.md, section 0)."
  fi
  echo
  echo "How to check that the fixes work: docs/SPEED_FIXES_SETUP.md, section 4."
}
main "$@"
