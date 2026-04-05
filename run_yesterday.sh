#!/bin/bash
cd "$(cd "$(dirname "$0")" && pwd)"

# Log an error if launchd kills us due to ExitTimeout
trap 'echo "[$(date -Iseconds)] ERROR: script killed by launchd (ExitTimeout reached)" >&2; exit 1' TERM

# Wait for network after wake (up to 60s)
for i in $(seq 1 60); do
  curl -s --max-time 2 https://www.google.com > /dev/null 2>&1 && break
  echo "Waiting for network... ($i)"
  sleep 1
done

# Always run from main, then restore the original branch
ORIGINAL_BRANCH=$(git rev-parse --abbrev-ref HEAD)
git checkout main && git pull --ff-only origin main
trap 'git checkout "$ORIGINAL_BRANCH"' EXIT

YESTERDAY=$(date -v-1d +%Y-%m-%d)
.venv/bin/second-brain --date "$YESTERDAY"
