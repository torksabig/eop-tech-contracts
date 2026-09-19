"""Minimal client for ЦАИС ЕОП (app.eop.bg) public NX1 JSON service."""

from __future__ import annotations

import http.client
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

SERVICE_BASE = "https://service.eop.bg/NX1Service.svc"
APP_BASE = "https://app.eop.bg"

HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "Accept": "application/json",
    "Origin": APP_BASE,
    "Referer": f"{APP_BASE}/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Connection": "close",
}

DOTNET_DATE_RE = re.compile(r"/Date\((-?\d+)([+-]\d{4})?\)/")

RETRYABLE = (
    TimeoutError,
    urllib.error.URLError,
    ConnectionError,
    OSError,
    http.client.RemoteDisconnected,
    http.client.IncompleteRead,
    http.client.BadStatusLine,
)


def parse_dotnet_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()
    if not isinstance(value, str):
        return str(value)
    m = DOTNET_DATE_RE.search(value)
    if not m:
        return value
    ms = int(m.group(1))
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def tender_url(tender_id: int | None) -> str | None:
    if not tender_id:
        return None
    return f"{APP_BASE}/today/tenders/{tender_id}"


class EopClient:
    def __init__(self, delay_s: float = 0.5, timeout_s: float = 90.0):
        self.delay_s = delay_s
        self.timeout_s = timeout_s
        self._last_call = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.delay_s:
            time.sleep(self.delay_s - elapsed)

    def call(self, method: str, request: dict[str, Any], *, retries: int = 6) -> dict[str, Any]:
        return self.call_raw(method, {"request": request}, retries=retries)

    def call_raw(self, method: str, body: dict[str, Any], *, retries: int = 6) -> dict[str, Any]:
        url = f"{SERVICE_BASE}/{method}"
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        last_err: Exception | None = None
        for attempt in range(retries):
            self._throttle()
            req = urllib.request.Request(url, data=payload, headers=HEADERS, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    raw = resp.read().decode("utf-8")
                self._last_call = time.monotonic()
                return json.loads(raw)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                self._last_call = time.monotonic()
                last_err = RuntimeError(f"{method} HTTP {exc.code}: {detail}")
                if exc.code in {403, 408, 429, 500, 502, 503, 504} and attempt < retries - 1:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                raise last_err from exc
            except RETRYABLE as exc:
                self._last_call = time.monotonic()
                last_err = exc
                time.sleep(2.0 * (attempt + 1))
                continue
        raise RuntimeError(f"{method} failed after {retries} retries: {last_err}")

    def paginate(
        self,
        method: str,
        base_request: dict[str, Any],
        *,
        page_size: int = 50,
        max_pages: int = 8,
        order_column: str | None = None,
        order_ascending: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        results: list[dict[str, Any]] = []
        total = 0
        for page in range(max_pages):
            start = page * page_size + 1
            end = start + page_size - 1
            request = {
                **base_request,
                "StartIndex": start,
                "EndIndex": end,
                "OrderAscending": order_ascending,
            }
            if order_column:
                request["OrderColumn"] = order_column
            try:
                data = self.call(method, request)
            except Exception as exc:  # noqa: BLE001 — keep collecting other queries
                print(f"    ! page {page+1} failed: {exc}", flush=True)
                break
            total = int(data.get("ResultsCount") or 0)
            page_rows = data.get("CurrentPageResults") or []
            results.extend(page_rows)
            if not page_rows or len(results) >= total:
                break
        return results, total
