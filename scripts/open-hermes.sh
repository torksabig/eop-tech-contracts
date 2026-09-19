#!/usr/bin/env bash
# Open Hermes Agent in the terminal (classic CLI or TUI).
set -euo pipefail

export PATH="${HOME}/.local/bin:${HOME}/.hermes/bin:${HOME}/.hermes/node/bin:${PATH:-}"

if ! command -v hermes >/dev/null 2>&1; then
  echo "hermes not found. Install with:"
  echo "  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"
  exit 1
fi

MODE="${1:---tui}"
case "$MODE" in
  --cli|-c) exec hermes --cli ;;
  --tui|-t|*) exec hermes --tui ;;
esac
