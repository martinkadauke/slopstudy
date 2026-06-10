"""Web search for source discovery.

Primary engine: a SearXNG instance (set SEARXNG_URL), which gives clean JSON
meta-search results from a self-hosted service. Falls back to DuckDuckGo's HTML
endpoint and finally the Wikipedia API, so search keeps working without any
configuration or API keys. Results are title/url/snippet dicts handed to the
LLM, which picks the best ones to cite.
"""
import asyncio
import logging
import os
import re
import urllib.parse

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger("flashdeck.websearch")

SEARXNG_URL = os.environ.get("SEARXNG_URL", "").rstrip("/")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Accept-Language": "en-US,en;q=0.8,de;q=0.6",
}
# One search at a time, with a pause — polite to public engines, and SearXNG
# instances often rate-limit bursts too.
_throttle = asyncio.Lock()
SEARCH_DELAY = 1.0

# Domains that rarely make good study citations.
SKIP_DOMAINS = ("duckduckgo.com", "pinterest.", "facebook.", "tiktok.", "instagram.")


async def search(query: str, max_results: int = 6) -> list[dict]:
    """Return [{title, url, snippet}] — empty list on any failure (never raises)."""
    async with _throttle:
        results = []
        engines = []
        if SEARXNG_URL:
            engines.append(("searxng", _searxng))
        engines += [("ddg", _ddg), ("wikipedia", _wikipedia)]
        for name, fn in engines:
            try:
                results = await fn(query, max_results)
            except Exception as e:
                log.warning("%s search failed for %r: %s", name, query[:60], e)
                results = []
            if results:
                break
        await asyncio.sleep(SEARCH_DELAY)
        return results


def _usable(url: str) -> bool:
    return url.startswith("http") and not any(d in url for d in SKIP_DOMAINS)


async def _searxng(query: str, max_results: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(
            SEARXNG_URL + "/search",
            params={"q": query, "format": "json", "safesearch": 1},
            headers=HEADERS,
        )
        resp.raise_for_status()
    out = []
    for r in resp.json().get("results", []):
        url = str(r.get("url", ""))
        if not _usable(url):
            continue
        out.append({
            "title": str(r.get("title", ""))[:150],
            "url": url[:500],
            "snippet": str(r.get("content", ""))[:300],
        })
        if len(out) >= max_results:
            break
    return out


def _clean_ddg_url(href: str) -> str:
    # DDG wraps results: //duckduckgo.com/l/?uddg=<encoded-url>&rut=...
    if "uddg=" in href:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        if qs.get("uddg"):
            return qs["uddg"][0]
    if href.startswith("//"):
        return "https:" + href
    return href


async def _ddg(query: str, max_results: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query, "kl": "wt-wt"},
            headers=HEADERS,
        )
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    out = []
    for res in soup.select(".result"):
        link = res.select_one(".result__a")
        if not link or not link.get("href"):
            continue
        url = _clean_ddg_url(link["href"])
        if not _usable(url):
            continue
        snippet_el = res.select_one(".result__snippet")
        out.append({
            "title": link.get_text(" ", strip=True)[:150],
            "url": url[:500],
            "snippet": (snippet_el.get_text(" ", strip=True) if snippet_el else "")[:300],
        })
        if len(out) >= max_results:
            break
    return out


async def _wikipedia(query: str, max_results: int) -> list[dict]:
    lang = "de" if re.search(r"[äöüß]", query.lower()) else "en"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={"action": "opensearch", "search": query[:200], "limit": max_results,
                    "format": "json"},
            headers=HEADERS,
        )
        resp.raise_for_status()
    data = resp.json()
    return [
        {"title": title, "url": url, "snippet": desc}
        for title, desc, url in zip(data[1], data[2], data[3])
    ]
