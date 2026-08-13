#!/bin/bash

if [ -f /.dockerenv ]; then
    echo "🐳 Running in Docker"
    fastapi dev app/main.py --host 0.0.0.0 --port 8001 --reload &
    python watcher.py
else
    echo "🟣 Running locally with uv"
    uv run fastapi dev app/main.py --host 0.0.0.0 --port 8001 --reload &
    uv run python watcher.py
fi

wait
