#!/usr/bin/env bash
# Wrapper for the twice-daily sync cron/Task Scheduler entry (specs/04-sources.md,
# "Scheduling"). Logs to data/logs/sync-YYYY-MM-DD.log so cron's own output,
# which most schedulers discard or bury, isn't the only record of a run.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# Cron/Task Scheduler environments often don't have ~/.local/bin on PATH.
export PATH="$HOME/.local/bin:$PATH"

# shellcheck disable=SC1091
source "$REPO_DIR/.venv/bin/activate"

LOG_DIR="$REPO_DIR/data/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/sync-$(date -u +%Y-%m-%d).log"

{
    echo "=== $(date -u +"%Y-%m-%dT%H:%M:%SZ") sync started ==="
    uv run python -m jobengine.sources.sync
    echo "=== $(date -u +"%Y-%m-%dT%H:%M:%SZ") sync finished ==="
} >> "$LOG_FILE" 2>&1
