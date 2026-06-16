#!/usr/bin/env bash
# demo.sh — one-shot walkthrough: plant labeled data-quality defects, then
# independently verify they round-trip. Prints each command before running it.
#
#   ./demo.sh            # writes to ./out
#   ./demo.sh /tmp/demo  # writes elsewhere
set -euo pipefail
cd "$(dirname "$0")"

# Prefer the project virtualenv if it exists; otherwise use python3 from PATH.
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python

OUT="${1:-./out}"

run() { printf '\n\033[1;36m$ %s\033[0m\n\n' "$*"; "$@"; }

clear
echo "=== dq-synth demo: generate defective data, then verify it ==="
run "$PY" -m dq_synth --rows 100000 --batches 7 --out "$OUT"
run "$PY" verify.py "$OUT"
