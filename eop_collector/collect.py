#!/usr/bin/env python3
"""Collect tech / dashboard / development tenders & contracts from ЦАИС ЕОП."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from client import EopClient, parse_dotnet_date, tender_url
from relevance import score_item

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

KEYWORDS = [
    "софтуер",
    "разработка на софтуер",
    "уебсайт",
    "уеб портал",
    "уеб приложение",
    "портал",
    "платформа",
    "dashboard",
    "дашборд",
    "мобилно приложение",
    "интеграция на системи",
    "дигитализация",
    "електронна услуга",
    "CRM",
    "ERP",
    "business intelligence",
    "информационна система",
    "надграждане на система",
    "изграждане на система",
    "custom software",
]

# Software + IT services CPV roots (comma-separated accepted by API).
CPV_QUERIES = [
    "72200000",  # Software programming and consultancy
    "72230000",  # Custom software development services
    "72260000",  # Software-related services
    "72000000",  # IT services
    "72400000",  # Internet services
    "48000000",  # Software package and information systems
    "48800000",  # Information systems and servers
    "72300000",  # Data services
]


def normalize_tender(
    raw: dict[str, Any], source: str, query: str, score: int, hits: list[str]
) -> dict[str, Any]:
    tender_id = raw.get("TenderId")
    return {
        "kind": "tender",
        "source": source,
        "query": query,
        "relevance_score": score,
        "relevance_hits": hits[:12],
        "tender_id": tender_id,
        "published_tender_id": raw.get("PublishedTenderId"),
        "special_number": raw.get("SpecialNumber") or raw.get("TenderNumber"),
        "title": raw.get("TenderName"),
        "description": raw.get("TenderDescription"),
        "organization": raw.get("OrganizationName"),
        "organization_id": raw.get("OrganizationId"),
        "amount": raw.get("TenderAmount"),
        "currency": raw.get("TenderCurrency"),
        "cpv": raw.get("TenderMainCpv"),
        "publication_date": parse_dotnet_date(raw.get("PublicationDate")),
        "deadline": parse_dotnet_date(raw.get("Deadline") or raw.get("OffersReceivingDeadline")),
        "procedure_type": raw.get("ProcedureType"),
        "url": tender_url(tender_id),
        "raw": raw,
    }


def normalize_contract(
    raw: dict[str, Any], source: str, query: str, score: int, hits: list[str]
) -> dict[str, Any]:
    tender_id = raw.get("TenderId")
    return {
        "kind": "contract",
        "source": source,
        "query": query,
        "relevance_score": score,
        "relevance_hits": hits[:12],
        "contract_id": raw.get("ContractId"),
        "contract_number": raw.get("ContractNumber"),
        "contract_subject": raw.get("ContractSubject"),
        "contract_value": raw.get("ContractValue"),
        "currency": raw.get("Currency"),
        "contract_date": parse_dotnet_date(raw.get("ContractDate")),
        "supplier": raw.get("SupplierName"),
        "supplier_registry": raw.get("SupplierRegisterNumber"),
        "tender_id": tender_id,
        "published_tender_id": raw.get("PublishedTenderId"),
        "special_number": raw.get("TenderNumber"),
        "title": raw.get("TenderName") or raw.get("ContractSubject"),
        "description": raw.get("ContractSubject"),
        "organization": raw.get("OrganizationName"),
        "organization_id": raw.get("OrganizationId"),
        "cpv": raw.get("TenderMainCpv"),
        "publication_date": parse_dotnet_date(raw.get("PublicationDate")),
        "url": tender_url(tender_id),
        "raw": raw,
    }


def dedupe_key(item: dict[str, Any]) -> str:
    if item["kind"] == "contract":
        return f"contract:{item.get('contract_id') or item.get('contract_number')}"
    return f"tender:{item.get('tender_id') or item.get('published_tender_id')}"


def collect(client: EopClient, page_size: int, max_pages: int) -> list[dict[str, Any]]:
    bucket: dict[str, dict[str, Any]] = {}

    def add_tender(raw: dict[str, Any], source: str, query: str) -> None:
        scored = dict(raw)
        if source.endswith("_cpv") and not scored.get("TenderMainCpv"):
            scored["TenderMainCpv"] = query
        score, hits = score_item(scored)
        # CPV IT families are already development-relevant even with thin titles.
        if source.endswith("_cpv") and score < 20:
            score = max(score, 25)
            hits = [*hits, f"cpv:{query}"]
        if score < 20:
            return
        item = normalize_tender(scored, source, query, score, hits)
        key = dedupe_key(item)
        prev = bucket.get(key)
        if prev is None or item["relevance_score"] > prev["relevance_score"]:
            bucket[key] = item

    def add_contract(raw: dict[str, Any], source: str, query: str) -> None:
        scored = dict(raw)
        if source.endswith("_cpv") and not scored.get("TenderMainCpv"):
            scored["TenderMainCpv"] = query
        score, hits = score_item(scored)
        if source.endswith("_cpv") and score < 20:
            score = max(score, 25)
            hits = [*hits, f"cpv:{query}"]
        if score < 20:
            return
        item = normalize_contract(scored, source, query, score, hits)
        key = dedupe_key(item)
        prev = bucket.get(key)
        if prev is None or item["relevance_score"] > prev["relevance_score"]:
            bucket[key] = item

    print(f"Quick keyword searches ({len(KEYWORDS)})…", flush=True)
    for kw in KEYWORDS:
        rows, total = client.paginate(
            "GetQuickSearchResult",
            {"Keywords": kw},
            page_size=page_size,
            max_pages=max_pages,
            order_column="PublicationDate",
        )
        print(f"  quick '{kw}': {len(rows)}/{total}", flush=True)
        for raw in rows:
            add_tender(raw, "quick_search", kw)

    print(f"Advanced tenders by CPV ({len(CPV_QUERIES)})…", flush=True)
    for cpv in CPV_QUERIES:
        rows, total = client.paginate(
            "GetPublishedTendersAdvancedSearchResult",
            {"CpvCode": cpv},
            page_size=page_size,
            max_pages=max_pages,
            order_column="PublicationDate",
        )
        print(f"  tenders CPV {cpv}: {len(rows)}/{total}", flush=True)
        for raw in rows:
            add_tender(raw, "advanced_tenders_cpv", cpv)

    print(f"Contracts by keyword ({len(KEYWORDS)})…", flush=True)
    for kw in KEYWORDS:
        rows, total = client.paginate(
            "GetContractsAdvancedSearchResult",
            {"ContractSubject": kw},
            page_size=page_size,
            max_pages=max_pages,
            order_column="ContractDate",
        )
        print(f"  contracts '{kw}': {len(rows)}/{total}", flush=True)
        for raw in rows:
            add_contract(raw, "contracts_subject", kw)

    print(f"Contracts by CPV ({len(CPV_QUERIES)})…", flush=True)
    for cpv in CPV_QUERIES:
        rows, total = client.paginate(
            "GetContractsAdvancedSearchResult",
            {"CpvCode": cpv},
            page_size=page_size,
            max_pages=max_pages,
            order_column="ContractDate",
        )
        print(f"  contracts CPV {cpv}: {len(rows)}/{total}", flush=True)
        for raw in rows:
            add_contract(raw, "contracts_cpv", cpv)

    return sorted(
        bucket.values(),
        key=lambda x: (
            -(x.get("relevance_score") or 0),
            -datetime_key(x.get("publication_date") or x.get("contract_date")),
        ),
    )


def datetime_key(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def write_outputs(items: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    public_dir = ROOT / "web" / "public" / "data"
    public_dir.mkdir(parents=True, exist_ok=True)

    tenders = [i for i in items if i["kind"] == "tender"]
    contracts = [i for i in items if i["kind"] == "contract"]
    collected_at = datetime.now(timezone.utc).isoformat()

    def slim(item: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in item.items() if k != "raw"}
        return out

    slim_items = [slim(i) for i in items]
    payload = {
        "collected_at": collected_at,
        "source": "https://app.eop.bg/today",
        "search": "https://app.eop.bg/today/reporting/search",
        "counts": {
            "total": len(slim_items),
            "tenders": len(tenders),
            "contracts": len(contracts),
        },
        "items": slim_items,
    }

    for path in (DATA_DIR / "tech-development.json", public_dir / "tech-development.json"):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # CSV without raw
    csv_path = DATA_DIR / "tech-development.csv"
    fields = [
        "kind",
        "relevance_score",
        "title",
        "organization",
        "supplier",
        "amount",
        "contract_value",
        "currency",
        "cpv",
        "special_number",
        "publication_date",
        "contract_date",
        "deadline",
        "url",
        "query",
        "source",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in slim_items:
            writer.writerow(row)

    # Markdown digest (top 80)
    md_lines = [
        "# Tech & development procurements (ЦАИС ЕОП)",
        "",
        f"Collected: `{collected_at}`",
        f"Total curated: **{len(slim_items)}** ({len(tenders)} tenders, {len(contracts)} contracts)",
        "",
        "Source: [app.eop.bg/today](https://app.eop.bg/today) · Search: [reporting/search](https://app.eop.bg/today/reporting/search)",
        "",
        "## Top matches",
        "",
    ]
    for item in slim_items[:80]:
        title = item.get("title") or "(untitled)"
        url = item.get("url") or "#"
        md_lines.append(
            f"- **[{title}]({url})** · {item.get('kind')} · score {item.get('relevance_score')} · "
            f"{item.get('organization') or '—'} · "
            f"{item.get('special_number') or ''} · "
            f"{item.get('publication_date') or item.get('contract_date') or ''}"
        )
        if item.get("contract_subject") and item["kind"] == "contract":
            md_lines.append(f"  - Contract: {item['contract_subject'][:180]}")
            if item.get("supplier"):
                md_lines.append(f"  - Supplier: {item['supplier']} · value {item.get('contract_value')}")
        elif item.get("description"):
            md_lines.append(f"  - {(item['description'] or '')[:180]}")
    (DATA_DIR / "tech-development.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"Wrote {csv_path}")
    print(f"Wrote {DATA_DIR / 'tech-development.json'} ({len(slim_items)} items)")
    print(f"Wrote {DATA_DIR / 'tech-development.md'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--max-pages", type=int, default=4, help="Pages per query (50 rows each)")
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    client = EopClient(delay_s=args.delay)
    items = collect(client, page_size=args.page_size, max_pages=args.max_pages)
    write_outputs(items)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
