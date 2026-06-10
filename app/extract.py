"""Extract plain text from uploaded documents and web sources."""
import io
import re
import zipfile

import httpx
from bs4 import BeautifulSoup

MAX_CHARS_PER_SOURCE = 12_000
MAX_CHARS_TOTAL = 30_000

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".csv"}


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
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "SlopStudy/1.0"})
        resp.raise_for_status()
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
