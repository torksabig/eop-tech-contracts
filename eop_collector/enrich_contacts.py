#!/usr/bin/env python3
"""Enrich curated EOP items with tender + buyer contact persons."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from client import EopClient, parse_dotnet_date

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE_DIR = DATA / "cache"
INPUT = DATA / "tech-development.json"
OUT_JSON = DATA / "tech-development-contacts.json"
OUT_CSV = DATA / "tech-development-contacts.csv"
OUT_MD = DATA / "tech-development-contacts.md"
OUT_LIST = DATA / "contact-list.csv"
PUBLIC = ROOT / "web" / "public" / "data"


def flat_address(addr: dict[str, Any] | None) -> str:
    if not addr or not isinstance(addr, dict):
        return ""
    parts = [addr.get("StreetAddress"), addr.get("City"), addr.get("Postcode")]
    return ", ".join(str(p).strip() for p in parts if p)


def load_cache(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_cache(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def fetch_orgs(client: EopClient, org_ids: list[int]) -> dict[str, Any]:
    cache_path = CACHE_DIR / "buyer-profiles.json"
    cache = load_cache(cache_path)
    missing = [oid for oid in org_ids if str(oid) not in cache]
    print(f"Buyer profiles: {len(org_ids)} unique, {len(missing)} to fetch", flush=True)
    for i, oid in enumerate(missing, 1):
        try:
            profile = client.call_raw(
                "GetPublicBuyerProfileBasicInformation",
                {"organizationId": oid},
            )
            cache[str(oid)] = {
                "organization_id": oid,
                "organization_name": profile.get("OrganizationName"),
                "registry_number": profile.get("RegistryNumber"),
                "vat_number": profile.get("VatNumber"),
                "batch_number": profile.get("BatchNumber"),
                "url": profile.get("Url"),
                "contact_name": profile.get("ContactPersonDisplayName"),
                "contact_email": profile.get("ContactPersonEmail"),
                "contact_phone": profile.get("ContactPersonPhone"),
                "address": flat_address(profile.get("Address")),
                "city": (profile.get("Address") or {}).get("City"),
                "postcode": (profile.get("Address") or {}).get("Postcode"),
                "street": (profile.get("Address") or {}).get("StreetAddress"),
                "nuts": ((profile.get("NutsCode") or {}).get("CodeText")),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:  # noqa: BLE001
            print(f"  ! org {oid}: {exc}", flush=True)
            cache[str(oid)] = {"organization_id": oid, "error": str(exc)}
        if i % 25 == 0 or i == len(missing):
            save_cache(cache_path, cache)
            print(f"  orgs {i}/{len(missing)}", flush=True)
    save_cache(cache_path, cache)
    return cache


def _fetch_one_tender(tid: int) -> tuple[int, dict[str, Any]]:
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


def fetch_tender_details_parallel(
    tender_ids: list[int], *, workers: int = 4
) -> dict[str, Any]:
    cache_path = CACHE_DIR / "tender-details.json"
    cache = load_cache(cache_path)
    missing = [tid for tid in tender_ids if str(tid) not in cache]
    print(
        f"Tender details: {len(tender_ids)} selected, {len(missing)} to fetch "
        f"({workers} workers)",
        flush=True,
    )
    if not missing:
        return cache

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_one_tender, tid): tid for tid in missing}
        for fut in as_completed(futures):
            tid = futures[fut]
            done += 1
            try:
                _, row = fut.result()
                cache[str(tid)] = row
            except Exception as exc:  # noqa: BLE001
                print(f"  ! tender {tid}: {exc}", flush=True)
                cache[str(tid)] = {"tender_id": tid, "error": str(exc)}
            if done % 20 == 0 or done == len(missing):
                save_cache(cache_path, cache)
                print(f"  tenders {done}/{len(missing)}", flush=True)
    save_cache(cache_path, cache)
    return cache


def prioritize_tender_ids(items: list[dict[str, Any]], limit: int) -> list[int]:
    """Highest relevance first, unique tender ids. Prefer open deadlines."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    def open_deadline_bonus(item: dict[str, Any]) -> int:
        for key in ("deadline", "offer_phase_end", "offers_receiving_deadline"):
            raw = item.get(key)
            if not raw:
                continue
            try:
                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                continue
            return 1 if dt >= now else 0
        return 0

    best: dict[int, tuple[int, int]] = {}
    for item in items:
        tid = item.get("tender_id")
        if not tid:
            continue
        score = int(item.get("relevance_score") or 0)
        bonus = open_deadline_bonus(item)
        prev = best.get(tid)
        if prev is None or (bonus, score) > prev:
            best[tid] = (bonus, score)
    ranked = sorted(best.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))
    return [tid for tid, _ in ranked[:limit]]


def enrich(
    items: list[dict[str, Any]], orgs: dict[str, Any], tenders: dict[str, Any]
) -> list[dict[str, Any]]:
    from status import apply_status_and_budget

    enriched: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        tid = item.get("tender_id")
        oid = item.get("organization_id")
        t = tenders.get(str(tid), {}) if tid else {}
        o = orgs.get(str(oid), {}) if oid else {}
        if t.get("error"):
            t = {}

        contact_name = t.get("contact_name") or o.get("contact_name") or ""
        contact_email = t.get("contact_email") or o.get("contact_email") or ""
        contact_phone = t.get("contact_phone") or o.get("contact_phone") or ""

        if t.get("contact_email") or t.get("contact_phone") or t.get("contact_name"):
            source = "tender"
        elif o.get("contact_email") or o.get("contact_name"):
            source = "buyer_profile"
        else:
            source = None

        row.update(
            {
                "contact_name": contact_name.strip()
                if isinstance(contact_name, str)
                else contact_name,
                "contact_email": (contact_email or "").strip(),
                "contact_phone": (contact_phone or "").strip(),
                "contact_source": source,
                "buyer_contact_name": (o.get("contact_name") or "").strip() if o else "",
                "buyer_contact_email": (o.get("contact_email") or "").strip() if o else "",
                "buyer_contact_phone": (o.get("contact_phone") or "").strip() if o else "",
                "buyer_registry_number": o.get("registry_number"),
                "buyer_vat_number": o.get("vat_number"),
                "buyer_address": o.get("address") or "",
                "buyer_city": o.get("city") or "",
                "buyer_postcode": o.get("postcode") or "",
                "buyer_street": o.get("street") or "",
                "buyer_url": o.get("url") or "",
                "buyer_nuts": o.get("nuts") or "",
            }
        )
        row = apply_status_and_budget(row, t or None)
        enriched.append(row)
    return enriched


def write_outputs(enriched: list[dict[str, Any]], collected_at: str) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)

    with_contact = sum(
        1
        for r in enriched
        if r.get("contact_email") or r.get("contact_phone") or r.get("contact_name")
    )
    with_email = sum(1 for r in enriched if r.get("contact_email"))
    active_n = sum(1 for r in enriched if r.get("is_active"))
    with_en = sum(1 for r in enriched if r.get("title_en"))

    payload = {
        "collected_at": collected_at,
        "enriched_at": datetime.now(timezone.utc).isoformat(),
        "source": "https://app.eop.bg/today",
        "counts": {
            "total": len(enriched),
            "tenders": sum(1 for r in enriched if r["kind"] == "tender"),
            "contracts": sum(1 for r in enriched if r["kind"] == "contract"),
            "with_contact": with_contact,
            "with_email": with_email,
            "active": active_n,
            "with_title_en": with_en,
        },
        "items": enriched,
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    OUT_JSON.write_text(text, encoding="utf-8")
    (PUBLIC / "tech-development-contacts.json").write_text(text, encoding="utf-8")

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
        "buyer_street",
        "buyer_postcode",
        "buyer_url",
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

    contact_rows: dict[str, dict[str, Any]] = {}
    for row in enriched:
        email = (row.get("contact_email") or "").strip().lower()
        name = (row.get("contact_name") or "").strip()
        org = row.get("organization") or ""
        key = email or f"{org}|{name}|{row.get('contact_phone')}"
        if not (email or name or row.get("contact_phone")):
            continue
        prev = contact_rows.get(key)
        entry = {
            "contact_name": name,
            "contact_email": row.get("contact_email") or "",
            "contact_phone": row.get("contact_phone") or "",
            "organization": org,
            "buyer_registry_number": row.get("buyer_registry_number") or "",
            "buyer_address": row.get("buyer_address") or "",
            "buyer_city": row.get("buyer_city") or "",
            "buyer_url": row.get("buyer_url") or "",
            "related_procurements": 1,
            "example_title": row.get("title") or "",
            "example_url": row.get("url") or "",
            "example_special_number": row.get("special_number") or "",
            "max_relevance_score": row.get("relevance_score") or 0,
        }
        if prev:
            prev["related_procurements"] += 1
            if (row.get("relevance_score") or 0) > (prev.get("max_relevance_score") or 0):
                prev["max_relevance_score"] = row.get("relevance_score")
                prev["example_title"] = row.get("title")
                prev["example_url"] = row.get("url")
                prev["example_special_number"] = row.get("special_number")
            for f in (
                "contact_phone",
                "buyer_address",
                "buyer_city",
                "buyer_url",
                "buyer_registry_number",
            ):
                if not prev.get(f) and entry.get(f):
                    prev[f] = entry[f]
        else:
            contact_rows[key] = entry

    contacts = sorted(
        contact_rows.values(),
        key=lambda r: (-(r.get("max_relevance_score") or 0), r.get("organization") or ""),
    )
    contact_fields = [
        "contact_name",
        "contact_email",
        "contact_phone",
        "organization",
        "buyer_registry_number",
        "buyer_address",
        "buyer_city",
        "buyer_url",
        "related_procurements",
        "max_relevance_score",
        "example_special_number",
        "example_title",
        "example_url",
    ]
    with OUT_LIST.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=contact_fields, extrasaction="ignore")
        w.writeheader()
        for row in contacts:
            w.writerow(row)
    (PUBLIC / "contact-list.csv").write_text(OUT_LIST.read_text(encoding="utf-8"), encoding="utf-8")
    (PUBLIC / "tech-development-contacts.csv").write_text(
        OUT_CSV.read_text(encoding="utf-8"), encoding="utf-8"
    )

    md = [
        "# Tech & development — contacts",
        "",
        f"Enriched: `{payload['enriched_at']}`",
        f"Rows: **{len(enriched)}** · with contact: **{with_contact}** · with email: **{with_email}**",
        f"Unique contact people: **{len(contacts)}**",
        "",
        "## Contact list (top 100)",
        "",
        "| Name | Email | Phone | Organization | # related |",
        "| --- | --- | --- | --- | --- |",
    ]
    for c in contacts[:100]:
        md.append(
            f"| {c.get('contact_name') or '—'} | {c.get('contact_email') or '—'} | "
            f"{c.get('contact_phone') or '—'} | {c.get('organization') or '—'} | "
            f"{c.get('related_procurements')} |"
        )
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(
        f"Wrote {OUT_JSON.name} ({len(enriched)} rows, {with_email} emails) "
        f"and {OUT_LIST.name} ({len(contacts)} unique contacts)",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay", type=float, default=0.3)
    parser.add_argument(
        "--tender-limit",
        type=int,
        default=180,
        help="Max unique high-score tenders to fetch tender-specific contacts for",
    )
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--skip-tenders", action="store_true")
    parser.add_argument("--orgs-only", action="store_true", help="Alias for --skip-tenders")
    args = parser.parse_args()
    if args.orgs_only:
        args.skip_tenders = True

    if not INPUT.exists():
        print(f"Missing {INPUT}; run collect.py first", file=sys.stderr)
        return 1

    dataset = json.loads(INPUT.read_text(encoding="utf-8"))
    items = dataset["items"]
    org_ids = sorted({i["organization_id"] for i in items if i.get("organization_id")})

    client = EopClient(delay_s=args.delay, timeout_s=40)
    orgs = fetch_orgs(client, org_ids)

    # Write org-only snapshot immediately so data is usable.
    write_outputs(enrich(items, orgs, {}), dataset.get("collected_at", ""))

    tenders: dict[str, Any] = load_cache(CACHE_DIR / "tender-details.json")
    if not args.skip_tenders:
        selected = prioritize_tender_ids(items, args.tender_limit)
        tenders = fetch_tender_details_parallel(selected, workers=args.workers)
        write_outputs(enrich(items, orgs, tenders), dataset.get("collected_at", ""))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
