import io

import httpx
from bs4 import BeautifulSoup

_PDF_MAX = 100_000
_URL_MAX = 50_000


async def extract_from_pdf(file_bytes: bytes) -> str:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text[:_PDF_MAX]


async def extract_from_docx(file_bytes: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(file_bytes))
    return "\n".join(para.text for para in doc.paragraphs)


async def extract_from_text(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8")


async def extract_from_url(url: str) -> str:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["nav", "footer", "header", "aside", "script", "style", "noscript"]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.find("body")
    text = main.get_text(separator="\n", strip=True) if main else soup.get_text(separator="\n", strip=True)
    return text[:_URL_MAX]
