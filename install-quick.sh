#!/bin/sh
set -eu
TASK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
UV_PROJECT_ENVIRONMENT="$TASK_DIR/.venv" uv sync --project "$TASK_DIR" --python 3.11 --locked
UV_PROJECT_ENVIRONMENT="$TASK_DIR/.venv-api" uv sync --project "$TASK_DIR" --python "${STUDIO_API_PYTHON:-3.12}" --only-group api --locked
