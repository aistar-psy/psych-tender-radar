#!/bin/sh
set -eu
RADAR_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$RADAR_DIR"
if [ ! -x .venv/bin/python ]; then
  printf '%s\n' '请先执行：python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt' >&2
  exit 1
fi
exec .venv/bin/python -m radar.cli "$@"
