#!/bin/sh
set -eu
TASK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$TASK_DIR/.venv-api/bin/python" "$TASK_DIR/launch.py"
