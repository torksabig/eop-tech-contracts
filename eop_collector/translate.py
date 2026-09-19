"""Translate BG → EN with caching (MyMemory free API, optional LibreTranslate / OpenAI)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data" / "cache" / "translations.json"

# MyMemory free tier: keep chunks short; pause between calls.
CHUNK_SIZE = 450
DEFAULT_DELAY_S = 0.35


def _cache_key(text: str, *, source: str = "bg", target: str = "en") -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:20]
    return f"{source}|{target}|{digest}"


def load_cache(path: Path = CACHE_PATH) -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_cache(cache: dict[str, Any], path: Path = CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def looks_mostly_english(text: str) -> bool:
    letters = re.findall(r"[A-Za-zА-Яа-яЁё]", text)
    if not letters:
        return True
    latin = sum(1 for ch in letters if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    return (latin / len(letters)) >= 0.85


def _chunks(text: str, size: int = CHUNK_SIZE) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    parts: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= size:
            parts.append(remaining)
            break
        cut = remaining.rfind(" ", 0, size)
        if cut < size // 3:
            cut = size
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return [p for p in parts if p]


def _http_json(url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None, timeout: float = 45.0) -> dict[str, Any]:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def translate_mymemory(text: str, *, email: str | None = None) -> str | None:
    params = {"q": text, "langpair": "bg|en"}
    if email:
        params["de"] = email
    url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(params)
    try:
        data = _http_json(url)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    if int(data.get("responseStatus") or 0) != 200:
        return None
    translated = (data.get("responseData") or {}).get("translatedText")
    if not translated:
        return None
    # MyMemory sometimes echoes "QUERY LENGTH LIMIT EXCEEDED" etc.
    if "QUERY LENGTH LIMIT" in translated.upper():
        return None
    return translated.strip()


def translate_libre(text: str, *, endpoint: str | None = None) -> str | None:
    base = (endpoint or os.environ.get("LIBRETRANSLATE_URL") or "https://libretranslate.com").rstrip("/")
    payload = json.dumps(
        {"q": text, "source": "bg", "target": "en", "format": "text"}
    ).encode("utf-8")
    try:
        data = _http_json(
            f"{base}/translate",
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, urllib.error.HTTPError):
        return None
    out = data.get("translatedText")
    return out.strip() if isinstance(out, str) and out.strip() else None


def translate_openai(text: str, *, api_key: str | None = None) -> str | None:
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    payload = json.dumps(
        {
            "model": os.environ.get("OPENAI_TRANSLATE_MODEL", "gpt-4o-mini"),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Translate Bulgarian public-procurement text to clear English. "
                        "Keep official names, CPV codes, and numbers unchanged. "
                        "Return only the translation."
                    ),
                },
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
        }
    ).encode("utf-8")
    try:
        data = _http_json(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, urllib.error.HTTPError):
        return None
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        return None


def translate_text(
    text: str | None,
    *,
    cache: dict[str, Any] | None = None,
    delay_s: float = DEFAULT_DELAY_S,
    prefer: str | None = None,
) -> tuple[str | None, str]:
    """
    Translate BG→EN. Returns (translated_or_none, provider).
    provider: cache | passthrough | openai | mymemory | libretranslate | none
    """
    if text is None:
        return None, "none"
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if not cleaned:
        return "", "none"
    if looks_mostly_english(cleaned):
        return cleaned, "passthrough"

    store = cache if cache is not None else load_cache()
    key = _cache_key(cleaned)
    hit = store.get(key)
    if isinstance(hit, dict) and hit.get("text"):
        return hit["text"], "cache"
    if isinstance(hit, str) and hit:
        return hit, "cache"

    providers = []
    preferred = (prefer or os.environ.get("TRANSLATE_PROVIDER") or "").lower().strip()
    if preferred == "openai" or os.environ.get("OPENAI_API_KEY"):
        providers.append("openai")
    if preferred == "libre":
        providers.append("libre")
    providers.extend(["mymemory", "libre", "openai"])
    # unique preserve order
    seen: set[str] = set()
    ordered = []
    for p in providers:
        if p not in seen:
            seen.add(p)
            ordered.append(p)

    email = os.environ.get("MYMEMORY_EMAIL")
    libre_url = os.environ.get("LIBRETRANSLATE_URL")

    pieces = _chunks(cleaned)
    translated_parts: list[str] = []
    used = "none"
    for piece in pieces:
        part_out: str | None = None
        for provider in ordered:
            if provider == "openai":
                part_out = translate_openai(piece)
            elif provider == "mymemory":
                part_out = translate_mymemory(piece, email=email)
            elif provider == "libre":
                part_out = translate_libre(piece, endpoint=libre_url)
            if part_out:
                used = provider
                break
            time.sleep(delay_s)
        if not part_out:
            return None, "none"
        translated_parts.append(part_out)
        time.sleep(delay_s)

    result = " ".join(translated_parts).strip()
    result = result.strip().strip('"').strip("'").strip()
    store[key] = {"text": result, "provider": used, "source_len": len(cleaned)}
    if cache is None:
        save_cache(store)
    return result, used


def prioritize_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Active + high score first, then the rest."""
    return sorted(
        items,
        key=lambda i: (
            0 if i.get("is_active") else 1,
            0 if i.get("status") == "active" else 1,
            -(i.get("relevance_score") or 0),
            -(i.get("budget_amount") or i.get("amount") or i.get("contract_value") or 0),
        ),
    )


def enrich_translations(
    items: list[dict[str, Any]],
    *,
    limit: int | None = None,
    delay_s: float = DEFAULT_DELAY_S,
    max_desc_chars: int = 900,
    save_every: int = 15,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    cache = load_cache()
    stats = {"translated": 0, "cached": 0, "passthrough": 0, "failed": 0, "skipped": 0}
    ordered = prioritize_items(items)
    if limit is not None:
        ordered = ordered[:limit]

    updates: dict[int, dict[str, Any]] = {}
    done = 0

    for item in ordered:
        row = dict(item)
        # Always try title; descriptions only for active / high-score / high-budget rows.
        want_desc = bool(
            row.get("is_active")
            or (row.get("relevance_score") or 0) >= 60
            or (row.get("budget_amount") or 0) >= 100_000
        )
        fields = [("title", "title_en", None)]
        if want_desc:
            fields.append(("description", "description_en", max_desc_chars))
            fields.append(("contract_subject", "contract_subject_en", max_desc_chars))
        any_new = False
        for src, dst, maxlen in fields:
            src_val = row.get(src)
            if not src_val:
                continue
            if row.get(dst):
                stats["skipped"] += 1
                continue
            text = str(src_val)
            if maxlen and len(text) > maxlen:
                text = text[:maxlen].rsplit(" ", 1)[0] + "…"
            translated, provider = translate_text(text, cache=cache, delay_s=delay_s)
            if translated:
                row[dst] = translated
                row[f"{dst}_provider"] = provider
                if provider == "cache":
                    stats["cached"] += 1
                elif provider == "passthrough":
                    stats["passthrough"] += 1
                else:
                    stats["translated"] += 1
                    any_new = True
            else:
                stats["failed"] += 1
                row["translation_note"] = (
                    "EN translation unavailable; showing Bulgarian source text"
                )
        updates[id(item)] = row
        done += 1
        if done % save_every == 0:
            save_cache(cache)
            print(f"  translations {done}/{len(ordered)} (cache size {len(cache)})", flush=True)

    save_cache(cache)
    out: list[dict[str, Any]] = []
    for item in items:
        out.append(updates.get(id(item), item))
    return out, stats
