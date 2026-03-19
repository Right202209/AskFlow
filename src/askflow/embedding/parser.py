from __future__ import annotations

from pathlib import Path

from askflow.core.logging import get_logger

logger = get_logger(__name__)


def parse_file(file_path: str, content_bytes: bytes | None = None) -> str:
    suffix = Path(file_path).suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(file_path, content_bytes)
    elif suffix == ".docx":
        return _parse_docx(content_bytes or Path(file_path).read_bytes())
    elif suffix == ".md":
        return _parse_markdown(content_bytes or Path(file_path).read_bytes())
    elif suffix in (".html", ".htm"):
        return _parse_html(content_bytes or Path(file_path).read_bytes())
    elif suffix == ".txt":
        return (content_bytes or Path(file_path).read_bytes()).decode("utf-8")
    else:
        logger.warning("unsupported_file_type", suffix=suffix)
        return (content_bytes or Path(file_path).read_bytes()).decode("utf-8", errors="replace")


def _parse_pdf(file_path: str, content_bytes: bytes | None) -> str:
    import fitz
    if content_bytes:
        doc = fitz.open(stream=content_bytes, filetype="pdf")
    else:
        doc = fitz.open(file_path)
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()
    return "\n".join(text_parts)


def _parse_docx(content_bytes: bytes) -> str:
    import io
    from docx import Document
    doc = Document(io.BytesIO(content_bytes))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _parse_markdown(content_bytes: bytes) -> str:
    return content_bytes.decode("utf-8")


def _parse_html(content_bytes: bytes) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content_bytes, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)
