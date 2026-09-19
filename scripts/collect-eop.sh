#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 eop_collector/collect.py "$@"
cp -f data/tech-development.json web/public/data/tech-development.json
echo "Synced web/public/data/tech-development.json"

if [[ "${EOP_ENRICH:-1}" == "1" ]]; then
  python3 eop_collector/enrich_contacts.py --tender-limit "${EOP_TENDER_LIMIT:-180}"
  python3 eop_collector/enrich_i18n.py --translate-limit "${EOP_TRANSLATE_LIMIT:-400}"
  echo "Contacts + status/budget/EN enrichment complete"
fi
