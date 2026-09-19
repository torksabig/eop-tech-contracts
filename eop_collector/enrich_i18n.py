#!/usr/bin/env python3
"""Add active status, budget scope, and English fields to the contacts dataset."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from client import EopClient, parse_dotnet_date
from enrich_contacts import (
    OUT_CSV,
    OUT_JSON,
    PUBLIC,
    load_cache,
    prioritize_tender_ids,
    write_outputs as write_contact_outputs,
)
from status import apply_status_and_budget
from translate import enrich_translations

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE_DIR = DATA / "cache"
INPUT_CONTACTS = DATA / "tech-development-contacts.json"
INPUT_BASE = DATA / "tech-development.json"


def _fetch_one_tender_full(tid: int) -> tuple[int, dict[str, Any]]:
    client = EopClient(delay_s=0.05, timeout_s=35)
    details = client.call_raw(
        "GetPublishedTenderDetails",
        {"tenderId": tid, "ianaTimeZone": "Europe/Sofia"},
        retries=3,
    )
    return tid, {
        "tender_id": tid,
        "tender_name": details.get("TenderName"),
        "tender_description": details.get("TenderDescription"),
        "special_number": details.get("SpecialNumber"),
        "organization_id": details.get("OrganizationId"),
        "organization_name": details.get("OrganizationName"),
        "contact_name": details.get("ContactPersonDisplayName"),
        "contact_email": details.get("ContactPersonEmail"),
        "contact_phone": details.get("ContactPersonPhone"),
        "publication_date": parse_dotnet_date(details.get("PublicationDate")),
        "offer_phase_end": parse_dotnet_date(details.get("OfferPhaseEndDate")),
        "offer_phase_start": parse_dotnet_date(details.get("OfferPhaseStartDate")),
        "estimated_value": details.get("EstimatedValue"),
        "currency_type": details.get("CurrencyType"),
        "participation_status": details.get("PublishedTenderParticipationStatus"),
        "published_tender_status": details.get("PublishedTenderStatus"),
        "explicit_tender_status": details.get("ExplicitTenderStatus"),
        "procedure_type": details.get("ProcedureType"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def refresh_tender_details(tender_ids: list[int], *, workers: int = 5) -> dict[str, Any]:
    """Fetch/merge richer tender details used for status + budget."""
    cache_path = CACHE_DIR / "tender-details.json"
    cache = load_cache(cache_path)
    missing: list[int] = []
    for tid in tender_ids:
        row = cache.get(str(tid)) or {}
        if row.get("error"):
            missing.append(tid)
            continue
        if "participation_status" not in row or "currency_type" not in row:
            missing.append(tid)
    print(
        f"Status details refresh: {len(tender_ids)} selected, {len(missing)} to fetch",
        flush=True,
    )
    if not missing:
        return cache

    from concurrent.futures import ThreadPoolExecutor, as_completed

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_one_tender_full, tid): tid for tid in missing}
        for fut in as_completed(futures):
            tid = futures[fut]
            done += 1
            try:
                _, row = fut.result()
                prev = cache.get(str(tid)) or {}
                prev.update(row)
                cache[str(tid)] = prev
            except Exception as exc:  # noqa: BLE001
                print(f"  ! tender {tid}: {exc}", flush=True)
                cache.setdefault(str(tid), {"tender_id": tid, "error": str(exc)})
            if done % 20 == 0 or done == len(missing):
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                print(f"  tenders {done}/{len(missing)}", flush=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


def apply_all(
    items: list[dict[str, Any]],
    tenders: dict[str, Any],
    *,
    translate: bool,
    translate_limit: int | None,
    delay_s: float,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in items:
        tid = item.get("tender_id")
        details = tenders.get(str(tid), {}) if tid else {}
        if details.get("error"):
            details = {}
        enriched.append(apply_status_and_budget(item, details or None))

    active_n = sum(1 for r in enriched if r.get("is_active"))
    print(f"Status applied: {active_n} active / {len(enriched)} total", flush=True)

    if not translate:
        return enriched

    print("Translating titles/descriptions (cached, active+high-score first)…", flush=True)
    enriched, stats = enrich_translations(
        enriched,
        limit=translate_limit,
        delay_s=delay_s,
    )
    print(f"Translation stats: {stats}", flush=True)
    return enriched


def write_extended_csv(enriched: list[dict[str, Any]]) -> None:
    fields = [
        "kind",
        "status",
        "is_active",
        "status_label",
        "relevance_score",
        "special_number",
        "title",
        "title_en",
        "description_en",
        "organization",
        "buyer_registry_number",
        "contact_name",
        "contact_email",
        "contact_phone",
        "contact_source",
        "buyer_contact_name",
        "buyer_contact_email",
        "buyer_contact_phone",
        "buyer_address",
        "buyer_city",
        "supplier",
        "amount",
        "contract_value",
        "budget_amount",
        "currency",
        "currency_code",
        "budget_scope",
        "estimated_value",
        "cpv",
        "publication_date",
        "contract_date",
        "deadline",
        "offer_phase_end",
        "url",
        "tender_id",
        "contract_id",
        "organization_id",
        "query",
        "source",
    ]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in enriched:
            w.writerow(row)
    (PUBLIC / "tech-development-contacts.csv").write_text(
        OUT_CSV.read_text(encoding="utf-8"), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Input JSON (default: contacts dataset, else tech-development.json)",
    )
    parser.add_argument("--refresh-details", action="store_true")
    parser.add_argument("--tender-limit", type=int, default=400)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--skip-translate", action="store_true")
    parser.add_argument(
        "--translate-limit",
        type=int,
        default=None,
        help="Max items to translate this run (default: all, using cache)",
    )
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    input_path = args.input
    if input_path is None:
        input_path = INPUT_CONTACTS if INPUT_CONTACTS.exists() else INPUT_BASE
    if not input_path.exists():
        print(f"Missing {input_path}; run collect/enrich_contacts first", file=sys.stderr)
        return 1

    dataset = json.loads(input_path.read_text(encoding="utf-8"))
    items = dataset["items"]

    tenders = load_cache(CACHE_DIR / "tender-details.json")
    if args.refresh_details:
        selected = prioritize_tender_ids(items, args.tender_limit)
        # Prefer active / high-score / high-value for refresh
        tenders = refresh_tender_details(selected, workers=args.workers)

    enriched = apply_all(
        items,
        tenders,
        translate=not args.skip_translate,
        translate_limit=args.translate_limit,
        delay_s=args.delay,
    )

    # Preserve contact fields; rewrite via enrich_contacts writer + extended CSV.
    collected_at = dataset.get("collected_at") or datetime.now(timezone.utc).isoformat()
    write_contact_outputs(enriched, collected_at)
    write_extended_csv(enriched)

    active = sum(1 for r in enriched if r.get("is_active"))
    with_en = sum(1 for r in enriched if r.get("title_en"))
    print(
        f"Done: {len(enriched)} rows · active={active} · title_en={with_en} · "
        f"{OUT_JSON}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
