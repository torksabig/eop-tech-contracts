#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 eop_collector/collect.py "$@"
cp -f data/tech-development.json web/public/data/tech-development.json
echo "Synced web/public/data/tech-development.json"
