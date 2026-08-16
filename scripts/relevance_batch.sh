#!/usr/bin/env bash
# Wrapper for the once-daily relevance+extraction batch Task Scheduler entry
# (docs/architecture.md's pipeline stages 2.5/3, D38 in docs/decisions.md).
# Logs to data/logs/relevance_batch-YYYY-MM-DD.log, same reasoning as
# sync.sh's own log file: most schedulers discard or bury their own
# captured stdout, so it shouldn't be the only record of a run.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# Cron/Task Scheduler environments often don't have ~/.local/bin on PATH.
export PATH="$HOME/.local/bin:$PATH"

# Needed for the Ollama-backed relevance/extraction calls; not required
# by sync.sh so it was never added there. See specs/05-model-routing.md.
export OLLAMA_BASE_URL="http://$(ip route show default | awk '{print $3}'):11434"

# shellcheck disable=SC1091
source "$REPO_DIR/.venv/bin/activate"

LOG_DIR="$REPO_DIR/data/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/relevance_batch-$(date -u +%Y-%m-%d).log"

{
    echo "=== $(date -u +"%Y-%m-%dT%H:%M:%SZ") relevance_batch started ==="
    uv run python -m jobengine.pipeline.batch
    echo "=== $(date -u +"%Y-%m-%dT%H:%M:%SZ") relevance_batch finished ==="
} >> "$LOG_FILE" 2>&1
