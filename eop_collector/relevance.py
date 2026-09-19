"""Score and filter ЕОП results for tech / software development work."""

from __future__ import annotations

import re
from typing import Any

# CPV families strongly tied to software, systems, web, IT services.
IT_CPV_PREFIXES = (
    "48",  # Software package and information systems
    "72",  # IT services: consulting, software development, Internet and support
    "302",  # Computer equipment (secondary — keep only with soft keywords)
    "503",  # Repair/maintenance of computers
)

# Strong development / dashboard / product signals (BG + EN).
STRONG_TERMS = [
    r"софтуер",
    r"software",
    r"информационн\w*\s+систем",
    r"информационн\w*\s+портал",
    r"уеб\s*(-|\s)?\s*(сайт|приложение|портал|платформ)",
    r"website",
    r"web\s*(app|application|portal|platform|dashboard)",
    r"dashboard",
    r"дашборд",
    r"разработк\w*",
    r"development",
    r"мобилн\w*\s+приложение",
    r"mobile\s*app",
    r"\bapi\b",
    r"интеграци",
    r"integration",
    r"crm\b",
    r"erp\b",
    r"\bbi\b",
    r"business\s*intelligence",
    r"аналитичн\w*\s+платформ",
    r"дигитализац",
    r"цифровизац",
    r"електронн\w*\s+(услуг|систем|портал|регистр)",
    r"front[\s-]?end",
    r"back[\s-]?end",
    r"fullstack|full[\s-]?stack",
    r"облачн\w*|cloud\b",
    r"saas\b",
    r"микросервис|microservice",
    r"devops",
    r"ux/?ui|ui/?ux|потребителски\s+интерфейс",
    r"база\s+данни|database",
    r"систем\w*\s+за\s+управлен",
    r"custom\s+software",
    r"portal|портал",
    r"платформ",
    r"platform",
    r"модул\w*\s+за",
    r"надграждане\s+на\s+(систем|софтуер|платформ)",
    r"имплементация\s+на\s+(систем|софтуер)",
    r"изграждане\s+на\s+(систем|портал|платформ|уеб)",
    r"поддръжка\s+на\s+(информационн|софтуер|систем)",
    r"лиценз\w*\s+за\s+софтуер",
    r"визуализац",
    r"monitoring|мониторинг\w*\s+(систем|платформ|dashboard)",
]

WEAK_TERMS = [
    r"хардуер",
    r"сърв\w*",
    r"компют",
    r"принтер",
    r"мрежов",
    r"кабел",
    r"лиценз",
    r"antivirus",
    r"office\s*365|microsoft\s*365",
    r"windows",
    r"it\s*услуг",
    r"икт",
]

NOISE_TERMS = [
    r"доставка\s+на\s+компютърна\s+техника",
    r"консумативи",
    r"тонер",
    r"хартия",
    r"климатик",
    r"почистване",
]


def _blob(item: dict[str, Any]) -> str:
    parts = [
        item.get("TenderName"),
        item.get("TenderDescription"),
        item.get("ContractSubject"),
        item.get("OrganizationName"),
        item.get("TenderMainCpv"),
        item.get("SpecialNumber"),
        item.get("TenderNumber"),
    ]
    return " ".join(str(p) for p in parts if p).lower()


def cpv_boost(cpv: str | None) -> int:
    if not cpv:
        return 0
    code = re.sub(r"\D", "", str(cpv))
    if code.startswith(("722", "720", "721", "723", "724", "725", "726", "48")):
        return 40
    if code.startswith(("72", "48")):
        return 30
    if code.startswith("302"):
        return 5
    return 0


def score_item(item: dict[str, Any]) -> tuple[int, list[str]]:
    text = _blob(item)
    hits: list[str] = []
    score = 0

    for pat in STRONG_TERMS:
        if re.search(pat, text, re.IGNORECASE):
            hits.append(pat)
            score += 15

    for pat in WEAK_TERMS:
        if re.search(pat, text, re.IGNORECASE):
            hits.append(f"weak:{pat}")
            score += 4

    for pat in NOISE_TERMS:
        if re.search(pat, text, re.IGNORECASE):
            score -= 20

    score += cpv_boost(item.get("TenderMainCpv") or item.get("CpvCode"))

    # Prefer true custom/dev wording over pure license/hardware.
    if re.search(r"разработк|development|изграждане|имплементац|интеграци|dashboard|дашборд", text):
        score += 10

    return score, hits


def is_relevant(item: dict[str, Any], min_score: int = 20) -> bool:
    score, _ = score_item(item)
    return score >= min_score
