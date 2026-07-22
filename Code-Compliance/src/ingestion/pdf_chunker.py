"""PDF text extraction and section-aware chunking for NECB-style code documents.

Strategy:
- Extract text page-by-page with pdfplumber (falls back to pypdf).
- Detect section headings (regex on lines like `3.2.2.4 Some Title`).
- Emit ~1000-character chunks with ~200-character overlap, carrying page number
  and the most recent detected section as metadata.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)

# Matches typical NECB section prefixes: "1.1.1.1", "3.2.2", "8.4.4.9.", possibly followed by a title on the same line.
_SECTION_RE = re.compile(r"^\s*(\d+(?:\.\d+){1,4})\.?\s+([A-Z][^\n]{2,120})?\s*$")
# Matches part / division headings ("Part 3", "Division B")
_PART_RE = re.compile(r"^\s*(Part|Division|Section|Chapter|Annex|Appendix)\s+([A-Z0-9]+)([^\n]*)$", re.IGNORECASE)


@dataclass
class Chunk:
    """A retrievable unit of text with citation metadata."""
    text: str
    page: int
    section: Optional[str] = None
    section_title: Optional[str] = None
    part: Optional[str] = None
    source_id: str = ""
    source_label: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _PageText:
    page: int
    text: str


def _extract_pages(pdf_path: Path) -> List[_PageText]:
    """Extract text per page.

    Uses pdfplumber's ``extract_words()`` (not ``extract_text()``) because NECB PDFs
    are tightly kerned and ``extract_text`` frequently drops inter-word spaces.
    Rebuilding the page from positioned words yields much cleaner tokenization.
    Falls back to pypdf if pdfplumber is unavailable.
    """
    pages: List[_PageText] = []
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(str(pdf_path)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                pages.append(_PageText(page=i, text=_page_text_from_words(page)))
        logger.info("pdfplumber extracted %d pages from %s", len(pages), pdf_path.name)
        return pages
    except ImportError:
        logger.info("pdfplumber not available; falling back to pypdf")
    except Exception as e:  # noqa: BLE001
        logger.warning("pdfplumber failed (%s); falling back to pypdf", e)

    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(str(pdf_path))
    for i, page in enumerate(reader.pages, start=1):
        try:
            pages.append(_PageText(page=i, text=page.extract_text() or ""))
        except Exception as e:  # noqa: BLE001
            logger.warning("pypdf failed on page %d: %s", i, e)
            pages.append(_PageText(page=i, text=""))
    logger.info("pypdf extracted %d pages from %s", len(pages), pdf_path.name)
    return pages


def _page_text_from_words(page) -> str:
    """Reassemble a page's text from ``extract_words`` output.

    Words with an upright ``upright`` flag and unrotated orientation are kept;
    words are grouped into lines by their vertical midpoint (``top``), then joined
    left-to-right. This preserves spacing that ``extract_text()`` loses on tightly
    kerned NECB pages, and it drops the rotated copyright watermarks that would
    otherwise appear as reversed strings.
    """
    try:
        words = page.extract_words(
            x_tolerance=2,
            y_tolerance=3,
            keep_blank_chars=False,
            use_text_flow=True,
            extra_attrs=["upright"],
        )
    except Exception:
        # Some pages (mostly image-only) have no extractable text.
        return page.extract_text() or ""

    # Drop rotated / non-upright glyphs (typically watermarks & margin notices).
    words = [w for w in words if w.get("upright", True)]
    if not words:
        return ""

    # Group into lines by the vertical midpoint of each word.
    lines: list[list[dict]] = []
    line_y_tol = 3.0
    for w in words:
        y = (float(w["top"]) + float(w["bottom"])) / 2.0
        placed = False
        for line in lines:
            ly = (float(line[0]["top"]) + float(line[0]["bottom"])) / 2.0
            if abs(ly - y) <= line_y_tol:
                line.append(w)
                placed = True
                break
        if not placed:
            lines.append([w])

    # Sort lines top-to-bottom, then each line left-to-right.
    lines.sort(key=lambda ln: min(float(w["top"]) for w in ln))
    out_lines: list[str] = []
    for ln in lines:
        ln.sort(key=lambda w: float(w["x0"]))
        out_lines.append(" ".join(w["text"] for w in ln))
    return "\n".join(out_lines)


# Heuristic: reject chunks that look like OCR garbage (mostly non-letters, or the
# reversed / rotated watermark text that sometimes leaks through despite the
# upright filter).
def _looks_like_text(s: str) -> bool:
    if len(s) < 80:
        return False
    letters = sum(1 for c in s if c.isalpha())
    if letters / max(1, len(s)) < 0.55:
        return False
    # Detect chunks dominated by very short "words" (typical of rotated/reversed
    # extraction: "5202\n,adanaC\nud\nsehcrehcer\n...").
    tokens = [t for t in re.split(r"\s+", s) if t]
    if not tokens:
        return False
    short = sum(1 for t in tokens if len(t) <= 2)
    if short / len(tokens) > 0.55:
        return False
    return True


def _iter_chunks(
    pages: List[_PageText],
    chunk_size: int,
    overlap: int,
) -> Iterable[Chunk]:
    """Convert page text into overlapping chunks, tracking the current section / part."""
    current_section: Optional[str] = None
    current_section_title: Optional[str] = None
    current_part: Optional[str] = None

    for pt in pages:
        # Sniff the top of the page for section / part markers before chunking.
        for line in pt.text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            m_part = _PART_RE.match(stripped)
            if m_part:
                current_part = " ".join(x for x in (m_part.group(1), m_part.group(2), m_part.group(3)) if x).strip()
                continue
            m_sec = _SECTION_RE.match(stripped)
            if m_sec:
                current_section = m_sec.group(1)
                current_section_title = (m_sec.group(2) or "").strip() or None

        text = re.sub(r"[ \t]+", " ", pt.text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if not text:
            continue

        # Split into overlapping windows.
        start = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            # Try to break on paragraph or sentence boundary within the last 20% of the window.
            if end < len(text):
                window_start = max(start + int(chunk_size * 0.8), start + 1)
                break_at = text.rfind("\n\n", window_start, end)
                if break_at == -1:
                    break_at = text.rfind(". ", window_start, end)
                    if break_at != -1:
                        break_at += 1  # keep the period
                if break_at != -1:
                    end = break_at
            chunk_text = text[start:end].strip()
            if len(chunk_text) >= 80 and _looks_like_text(chunk_text):
                yield Chunk(
                    text=chunk_text,
                    page=pt.page,
                    section=current_section,
                    section_title=current_section_title,
                    part=current_part,
                )
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)


def chunk_pdf(
    pdf_path: Path,
    source_id: str,
    source_label: str,
    chunk_size: int = 1000,
    overlap: int = 200,
) -> List[Chunk]:
    """Extract and chunk a single PDF. Returns a list of ``Chunk`` with citation metadata."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    pages = _extract_pages(pdf_path)
    chunks = list(_iter_chunks(pages, chunk_size=chunk_size, overlap=overlap))
    for c in chunks:
        c.source_id = source_id
        c.source_label = source_label
    logger.info("Produced %d chunks from %s", len(chunks), pdf_path.name)
    return chunks
