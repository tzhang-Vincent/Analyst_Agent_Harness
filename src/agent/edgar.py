"""Thin, deterministic client for SEC EDGAR XBRL data.

No LLM is involved here: this module is the source of truth. Every request
carries the SEC-required ``User-Agent``, is rate-limited, and is cached to
``data/cache`` so a number is reproducible offline and re-fetchable.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

DEFAULT_USER_AGENT = "financial-research-agent/0.1 (contact: set SEC_USER_AGENT)"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
XBRL_BASE = "https://data.sec.gov/api/xbrl"


def filing_index_url(cik: str, accession_number: str) -> str:
    """Link to the filing index page for an accession number.

    SEC URLs are ``/Archives/edgar/data/<cik>/<accn-no-dashes>/<accn>-index.htm``.
    """
    accn_no_dash = accession_number.replace("-", "")
    cik_int = str(int(cik))
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
        f"{accn_no_dash}/{accession_number}-index.htm"
    )


class EdgarClient:
    def __init__(
        self,
        cache_dir: str | os.PathLike = "data/cache",
        rate_limit: float = 0.2,
        user_agent: str | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._rate_limit = rate_limit
        self._last_request = 0.0
        self._user_agent = (
            user_agent or os.environ.get("SEC_USER_AGENT") or DEFAULT_USER_AGENT
        )
        self._client = httpx.Client(
            headers={"User-Agent": self._user_agent}, timeout=30.0
        )
        self._ticker_map: dict | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "EdgarClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _get(self, url: str) -> dict:
        now = time.monotonic()
        wait = self._last_request + self._rate_limit - now
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()
        resp = self._client.get(url)
        resp.raise_for_status()
        return resp.json()

    def _cached_get(self, key: str, url: str) -> dict:
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text())
        data = self._get(url)
        tmp = cache_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(cache_file)
        return data

    def ticker_to_cik(self, ticker: str) -> str:
        """Map a ticker to its 10-digit CIK, caching the SEC ticker index."""
        ticker = ticker.upper()
        if self._ticker_map is None:
            self._ticker_map = self._cached_get("company_tickers", COMPANY_TICKERS_URL)
        for entry in self._ticker_map.values():
            if entry.get("ticker") == ticker:
                return str(entry["cik_str"]).zfill(10)
        raise KeyError(f"Unknown ticker: {ticker}")

    def get_company_facts(self, cik: str) -> dict:
        """Return the full companyfacts XBRL JSON for a CIK (all concepts)."""
        return self._cached_get(f"facts_{cik}", f"{XBRL_BASE}/companyfacts/CIK{cik}.json")

    def get_concept(self, cik: str, tag: str, taxonomy: str = "us-gaap") -> dict:
        """Return the companyconcept JSON for a single XBRL tag."""
        url = f"{XBRL_BASE}/companyconcept/CIK{cik}/{taxonomy}/{tag}.json"
        return self._cached_get(f"concept_{cik}_{taxonomy}_{tag}", url)
