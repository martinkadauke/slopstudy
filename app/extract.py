"""Extract plain text from uploaded documents and web sources."""
import io
import ipaddress
import re
import socket
import zipfile
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

MAX_CHARS_PER_SOURCE = 12_000
MAX_CHARS_TOTAL = 30_000
MAX_REDIRECTS = 5

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".csv"}


class UrlNotAllowed(Exception):
    """A user-supplied URL resolves to a non-public address (SSRF guard)."""


def _ip_blocked(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
            or ip.is_multicast or ip.is_unspecified)


def _assert_public_url(url: str):
    """Reject URLs that point at private/internal/loopback addresses.

    Resolves the host and checks every returned A/AAAA record, so a public
    hostname that resolves to a LAN IP (or a redirect to one) is blocked too.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UrlNotAllowed(f"Unsupported URL scheme: {parsed.scheme or '(none)'}")
    host = parsed.hostname
    if not host:
        raise UrlNotAllowed("URL has no host")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UrlNotAllowed(f"Cannot resolve host: {host}") from e
    for info in infos:
        if _ip_blocked(info[4][0]):
            raise UrlNotAllowed(f"URL points to a private/internal address ({host})")


def _clip(text: str, limit: int = MAX_CHARS_PER_SOURCE) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:limit]


def extract_file(filename: str, data: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _clip(_extract_pdf(data))
    if lower.endswith(".docx"):
        return _clip(_extract_docx(data))
    # txt / md / csv — best-effort decode
    return _clip(data.decode("utf-8", errors="replace"))


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages[:80]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _extract_docx(data: bytes) -> str:
    # A .docx is a zip; paragraph text lives in word/document.xml.
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    return text


async def fetch_url(url: str) -> str:
    if not re.match(r"^https?://", url):
        raise ValueError(f"Invalid URL: {url}")
    # Follow redirects manually so every hop is SSRF-checked (a public URL can
    # 302 to an internal one). httpx auto-redirect would bypass per-hop checks.
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        current = url
        for _ in range(MAX_REDIRECTS):
            _assert_public_url(current)
            resp = await client.get(current, headers={"User-Agent": "SlopStudy/1.0"})
            if resp.is_redirect and resp.headers.get("location"):
                current = urljoin(current, resp.headers["location"])
                continue
            break
        else:
            raise UrlNotAllowed("Too many redirects")
        resp.raise_for_status()
    url = current
    content_type = resp.headers.get("content-type", "")
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        return _clip(_extract_pdf(resp.content))
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return _clip(main.get_text(separator="\n"))


def combine_sources(sources: list[dict]) -> str:
    """Merge extracted source texts into one bounded context block."""
    if not sources:
        return ""
    budget = MAX_CHARS_TOTAL
    per_source = max(2000, budget // len(sources))
    parts = []
    for src in sources:
        text = (src.get("content_text") or "")[:per_source]
        if text.strip():
            parts.append(f"=== SOURCE: {src['name']} ===\n{text}")
    return "\n\n".join(parts)[:budget]
