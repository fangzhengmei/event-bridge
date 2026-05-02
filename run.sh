#!/bin/bash
set -euo pipefail

echo "Starting event-bridge..."
exec uvicorn main:app --host 0.0.0.0 --port "${APP_PORT:-8000}"
