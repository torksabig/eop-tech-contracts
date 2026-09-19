"""Active status + currency / budget helpers for EOP tenders & contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# NX1 CurrencyType (common mapping used by ЦАИС ЕОП / NX1)
CURRENCY_CODE = {
    0: None,
    1: "EUR",
    2: "USD",
    3: "BGN",
    4: "GBP",
    5: "CHF",
    6: "JPY",
    7: "CAD",
    8: "AUD",
    9: "NOK",
    10: "SEK",
    11: "DKK",
    12: "RON",
    13: "TRY",
    14: "RUB",
}

# PublishedTenderParticipationStatus
PARTICIPATION_OPEN = 1
PARTICIPATION_CLOSED = 2


def map_currency(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        text = value.strip().upper()
        if text in {"EUR", "BGN", "USD", "GBP", "CHF"}:
            return text
        if text.isdigit():
            return CURRENCY_CODE.get(int(text))
        return text[:8] or None
    try:
        return CURRENCY_CODE.get(int(value))
    except (TypeError, ValueError):
        return None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_amount(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(num - round(num)) < 1e-9:
        return f"{int(round(num)):,}".replace(",", " ")
    return f"{num:,.2f}".replace(",", " ")


def budget_for_item(
    item: dict[str, Any], details: dict[str, Any] | None = None
) -> dict[str, Any]:
    details = details or {}
    kind = item.get("kind")
    currency = map_currency(
        item.get("currency")
        if item.get("currency") not in (None, "")
        else details.get("currency_type")
    )
    estimated = details.get("estimated_value")
    if estimated is None:
        estimated = item.get("estimated_value")

    if kind == "contract":
        amount = item.get("contract_value")
        if amount is None:
            amount = estimated
        label = "Contract value"
    else:
        amount = item.get("amount")
        if amount is None:
            amount = estimated
        label = "Estimated value"

    amount_fmt = format_amount(amount)
    if amount_fmt and currency:
        budget_scope = f"{label}: {amount_fmt} {currency}"
    elif amount_fmt:
        budget_scope = f"{label}: {amount_fmt}"
    else:
        budget_scope = "Budget unknown"

    return {
        "estimated_value": estimated,
        "budget_amount": amount,
        "currency_code": currency,
        "budget_scope": budget_scope,
    }


def determine_status(
    item: dict[str, Any],
    details: dict[str, Any] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return status / is_active / status_label for a tender or contract row."""
    now = now or datetime.now(timezone.utc)
    details = details or {}
    kind = item.get("kind")

    if kind == "contract":
        return {
            "status": "awarded",
            "is_active": False,
            "status_label": "Awarded",
            "status_reason": "awarded_contract",
        }

    participation = details.get("participation_status")
    if participation is None:
        participation = item.get("published_tender_participation_status")
    tender_status = details.get("published_tender_status")
    if tender_status is None:
        tender_status = item.get("tender_status") or item.get("published_tender_status")

    deadline = (
        details.get("offer_phase_end")
        or item.get("offer_phase_end")
        or item.get("deadline")
        or item.get("offers_receiving_deadline")
    )
    deadline_dt = _parse_dt(deadline if isinstance(deadline, str) else None)

    if participation == PARTICIPATION_OPEN:
        if deadline_dt and deadline_dt < now:
            return {
                "status": "closed",
                "is_active": False,
                "status_label": "Closed",
                "status_reason": "deadline_passed",
            }
        return {
            "status": "active",
            "is_active": True,
            "status_label": "Active",
            "status_reason": "participation_open",
        }

    if participation == PARTICIPATION_CLOSED:
        return {
            "status": "closed",
            "is_active": False,
            "status_label": "Closed",
            "status_reason": "participation_closed",
        }

    if deadline_dt is not None:
        if deadline_dt >= now:
            return {
                "status": "active",
                "is_active": True,
                "status_label": "Active",
                "status_reason": "deadline_open",
            }
        return {
            "status": "closed",
            "is_active": False,
            "status_label": "Closed",
            "status_reason": "deadline_passed",
        }

    # PublishedTenderStatus / TenderStatus == 1 often means published / open.
    if tender_status == 1:
        return {
            "status": "active",
            "is_active": True,
            "status_label": "Active",
            "status_reason": "tender_status_open",
        }

    if tender_status in {3, 4, 5, 6}:
        return {
            "status": "closed",
            "is_active": False,
            "status_label": "Closed",
            "status_reason": f"tender_status_{tender_status}",
        }

    return {
        "status": "unknown",
        "is_active": False,
        "status_label": "Unknown",
        "status_reason": "insufficient_data",
    }


def apply_status_and_budget(
    item: dict[str, Any], details: dict[str, Any] | None = None
) -> dict[str, Any]:
    row = dict(item)
    if details:
        if details.get("estimated_value") is not None and row.get("estimated_value") is None:
            row["estimated_value"] = details.get("estimated_value")
        if details.get("offer_phase_end") and not row.get("offer_phase_end"):
            row["offer_phase_end"] = details.get("offer_phase_end")
        if details.get("participation_status") is not None:
            row["published_tender_participation_status"] = details.get("participation_status")
        if details.get("published_tender_status") is not None:
            row["published_tender_status"] = details.get("published_tender_status")
        if details.get("currency_type") is not None and row.get("currency") in (None, ""):
            row["currency"] = details.get("currency_type")
        if details.get("tender_description") and not row.get("description"):
            row["description"] = details.get("tender_description")
    row.update(determine_status(row, details))
    row.update(budget_for_item(row, details))
    return row
