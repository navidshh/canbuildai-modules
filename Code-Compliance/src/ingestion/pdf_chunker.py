"""PDF text extraction and section-aware chunking for NECB-style code documents.

Strategy:
- Extract text page-by-page with pdfplumber (falls back to pypdf).
- On each page, also extract *tables* with pdfplumber ``find_tables()`` and render
  them as GitHub-flavored Markdown; emit one chunk per table plus one chunk per
  row for large tables (prefixed with the caption + column headers) so single-row
  retrieval (e.g. "Zone 4 wall U-value") lands on the right cell.
- Detect section headings (regex on lines like ``3.2.2.4 Some Title``).
- Emit ~1000-character text chunks with ~200-character overlap, carrying page
  number and the most recent detected section as metadata. Words that fall
  inside a table bounding box are excluded from the surrounding text so the
  flat-text chunks don't duplicate the table as a jumbled string.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Matches typical NECB section prefixes: "1.1.1.1", "3.2.2", "8.4.4.9.", possibly followed by a title on the same line.
_SECTION_RE = re.compile(r"^\s*(\d+(?:\.\d+){1,4})\.?\s+([A-Z][^\n]{2,120})?\s*$")
# Matches part / division headings ("Part 3", "Division B")
_PART_RE = re.compile(r"^\s*(Part|Division|Section|Chapter|Annex|Appendix)\s+([A-Z0-9]+)([^\n]*)$", re.IGNORECASE)
# Matches an NECB table caption line, e.g. "Table 3.2.2.2." or "Table 3.2.2.2. Maximum Overall Thermal Transmittance…"
_TABLE_CAPTION_RE = re.compile(r"^\s*(Table\s+[A-Z]?\d+(?:\.\d+){0,4}\.?)(\s+.+)?$", re.IGNORECASE)

# Emit a row-per-chunk for tables with at least this many data rows. Small tables
# (title block, 2-column summary) stay as one chunk to preserve their structure.
_ROW_CHUNK_MIN_ROWS = 3
# Cap how much of the table caption + column header block we prepend to each row
# chunk so the row-chunk stays focused.
_ROW_CHUNK_HEADER_MAX_CHARS = 600


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
    # "text" for prose, "table" for a full rendered Markdown table, "table_row"
    # for a single-row chunk carrying the caption + column headers + one row.
    chunk_type: str = "text"
    table_caption: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _Table:
    page: int
    bbox: Tuple[float, float, float, float]  # (x0, top, x1, bottom)
    rows: List[List[str]]                    # first row = headers if header_row_index==0
    header_row_index: int
    caption: Optional[str]                   # nearest "Table X.Y.Z." line above the table


@dataclass
class _PageContent:
    page: int
    text: str                                # flat text with table regions removed
    tables: List[_Table]



def _extract_pages(pdf_path: Path) -> List[_PageContent]:
    """Extract text + tables per page.

    Uses pdfplumber's ``extract_words()`` (not ``extract_text()``) because NECB PDFs
    are tightly kerned and ``extract_text`` frequently drops inter-word spaces.
    Also uses ``find_tables()`` to pull structured tables and remove their words
    from the surrounding text so tables aren't duplicated as jumbled strings.
    Falls back to pypdf (text-only, no tables) if pdfplumber is unavailable.
    """
    pages: List[_PageContent] = []
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(str(pdf_path)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                tables = _extract_tables(page, page_num=i)
                text = _page_text_from_words(page, exclude_bboxes=[t.bbox for t in tables])
                # Attach the nearest "Table X.Y.Z." caption sitting just above each table.
                _attach_captions(tables, text)
                pages.append(_PageContent(page=i, text=text, tables=tables))
        n_tables = sum(len(p.tables) for p in pages)
        logger.info(
            "pdfplumber extracted %d pages and %d tables from %s",
            len(pages), n_tables, pdf_path.name,
        )
        return pages
    except ImportError:
        logger.info("pdfplumber not available; falling back to pypdf (no tables)")
    except Exception as e:  # noqa: BLE001
        logger.warning("pdfplumber failed (%s); falling back to pypdf (no tables)", e)

    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(str(pdf_path))
    for i, page in enumerate(reader.pages, start=1):
        try:
            pages.append(_PageContent(page=i, text=page.extract_text() or "", tables=[]))
        except Exception as e:  # noqa: BLE001
            logger.warning("pypdf failed on page %d: %s", i, e)
            pages.append(_PageContent(page=i, text="", tables=[]))
    logger.info("pypdf extracted %d pages from %s", len(pages), pdf_path.name)
    return pages


def _extract_tables(page, page_num: int) -> List[_Table]:
    """Return the tables found on ``page`` as ``_Table`` objects (empty on failure)."""
    try:
        found = page.find_tables()
    except Exception as e:  # noqa: BLE001
        logger.debug("find_tables() failed on page %d: %s", page_num, e)
        return []
    tables: List[_Table] = []
    for t in found:
        try:
            rows = t.extract()
        except Exception as e:  # noqa: BLE001
            logger.debug("table.extract() failed on page %d: %s", page_num, e)
            continue
        if not rows:
            continue
        cleaned = _clean_table_rows(rows)
        cleaned = _split_multiline_cells(cleaned)
        if not cleaned or len(cleaned) < 2:
            # Not really a table (single row or nothing after cleaning).
            continue
        tables.append(_Table(
            page=page_num,
            bbox=tuple(float(v) for v in t.bbox),  # (x0, top, x1, bottom)
            rows=cleaned,
            header_row_index=0,  # pdfplumber returns header first for most NECB tables
            caption=None,
        ))
    return tables


def _clean_table_rows(rows: List[List[Optional[str]]]) -> List[List[str]]:
    """Normalize a table extracted by pdfplumber: drop empty rows/cols, collapse whitespace.

    Preserves newlines inside cells so ``_split_multiline_cells`` can later split
    cells whose visual content is actually several stacked rows (a common NECB
    pattern where the first-column label is "Walls\\nRoofs\\nFloors" and the
    value columns are "0.290\\n0.164\\n0.193").
    """
    norm: List[List[str]] = []
    for row in rows:
        clean_row: List[str] = []
        for c in row:
            s = c or ""
            # Collapse runs of spaces/tabs but keep newlines as row separators.
            s = re.sub(r"[ \t]+", " ", s).strip()
            # Also collapse multiple consecutive newlines to one.
            s = re.sub(r"\n{2,}", "\n", s)
            clean_row.append(s)
        norm.append(clean_row)
    # Drop rows that are entirely empty.
    norm = [r for r in norm if any(cell for cell in r)]
    if not norm:
        return []
    # Pad ragged rows and drop trailing all-empty columns.
    ncols = max(len(r) for r in norm)
    norm = [r + [""] * (ncols - len(r)) for r in norm]
    keep = [any(row[c] for row in norm) for c in range(ncols)]
    norm = [[cell for cell, k in zip(row, keep) if k] for row in norm]
    return norm


def _split_multiline_cells(rows: List[List[str]]) -> List[List[str]]:
    """Split rows whose cells contain internal newlines into multiple rows.

    NECB PDFs frequently render a single "row" whose visual content is a stack
    of labels (e.g. ``Walls\\nRoofs\\nFloors``) with matching value columns
    (``0.290\\n0.164\\n0.193``). pdfplumber returns those as one cell each. This
    step detects that case and expands it into distinct rows so per-row chunks
    become useful.

    Rules:
    - Only split rows where at least two cells contain a newline (a single cell
      with a newline is usually wrapped text, not stacked rows).
    - The target sub-row count is decided by *majority vote* among cells that
      have more than one line — this handles the case where the label column is
      over-segmented (e.g. "Vertical\\nfenestration\\nSkylights" is really 2
      rows because the value columns only have 2 values).
    - Cells with count == 1 are replicated across every sub-row (shared label /
      footnote applies to each).
    - Cells with count > target are merged with a space so no data is lost.
    - Cells with count < target are padded with empty strings.
    """
    out: List[List[str]] = []
    for row in rows:
        parts_per_cell: List[List[str]] = [
            [p.strip() for p in c.split("\n")] if "\n" in c else [c]
            for c in row
        ]
        multi_counts = [len(p) for p in parts_per_cell if len(p) > 1]
        if len(multi_counts) < 2:
            # 0 or 1 multi-line cells: probably just wrapped text; keep as one row.
            out.append([c.replace("\n", " ").strip() for c in row])
            continue

        # Majority target: pick the most common count among multi-line cells.
        # Ties break to the smaller count (fewer splits — safer against over-splitting).
        counter: dict[int, int] = {}
        for n in multi_counts:
            counter[n] = counter.get(n, 0) + 1
        target = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

        for i in range(target):
            sub: List[str] = []
            for parts in parts_per_cell:
                if len(parts) == 1:
                    sub.append(parts[0])
                elif len(parts) == target:
                    sub.append(parts[i])
                elif len(parts) > target:
                    # Over-split (e.g. 3-line label vs. 2 value rows) — usually a
                    # word-wrapped label. Merge the extra leading parts into the
                    # first sub-row: NECB tables typically wrap the longer
                    # multi-word label first ("Vertical\\nfenestration") followed
                    # by shorter singletons ("Skylights").
                    extras = len(parts) - target
                    if i == 0:
                        sub.append(" ".join(parts[: extras + 1]).strip())
                    else:
                        sub.append(parts[i + extras])
                else:
                    # Under-split (fewer lines than target): pad short.
                    sub.append(parts[i] if i < len(parts) else "")
            out.append(sub)
    return out


def _attach_captions(tables: List[_Table], page_text: str) -> None:
    """Best-effort: find the nearest ``Table X.Y.Z. …`` caption line above each table.

    We can't reliably read positional captions from ``page_text`` (which has table
    words removed and lines re-flowed), so we scan the whole page text for any
    ``Table …`` line and assign captions to tables in order of appearance.
    Falls back to ``None`` when no captions are found.
    """
    captions: List[str] = []
    for line in page_text.splitlines():
        m = _TABLE_CAPTION_RE.match(line.strip())
        if m:
            label = m.group(1).strip()
            title = (m.group(2) or "").strip()
            captions.append(f"{label} {title}".strip())
    # Pair captions to tables in order; if counts don't match, still assign what we can.
    for i, t in enumerate(tables):
        if i < len(captions):
            t.caption = captions[i]


def _page_text_from_words(page, exclude_bboxes: Sequence[Tuple[float, float, float, float]] = ()) -> str:
    """Reassemble a page's text from ``extract_words`` output.

    Words with an upright ``upright`` flag and unrotated orientation are kept;
    words are grouped into lines by their vertical midpoint (``top``), then joined
    left-to-right. This preserves spacing that ``extract_text()`` loses on tightly
    kerned NECB pages, and it drops the rotated copyright watermarks that would
    otherwise appear as reversed strings.

    Words whose center falls inside any ``exclude_bboxes`` rectangle are omitted
    so the flat-text chunks don't duplicate content that's already emitted as a
    structured table chunk.
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
    if exclude_bboxes:
        words = [w for w in words if not _word_in_any_bbox(w, exclude_bboxes)]
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


def _word_in_any_bbox(word: dict, bboxes: Sequence[Tuple[float, float, float, float]]) -> bool:
    cx = (float(word["x0"]) + float(word["x1"])) / 2.0
    cy = (float(word["top"]) + float(word["bottom"])) / 2.0
    for (x0, top, x1, bottom) in bboxes:
        if x0 <= cx <= x1 and top <= cy <= bottom:
            return True
    return False


# --------------------------------------------------------------------- table rendering


def _render_table_markdown(table: _Table) -> str:
    """Render a ``_Table`` as a GitHub-flavored Markdown table.

    Includes the caption (if any) as a leading heading so the LLM sees a title,
    the column headers as a proper header row, and cells with pipes/newlines
    escaped so the Markdown parses cleanly.
    """
    rows = table.rows
    if not rows:
        return ""
    if len(rows) == 1:
        # No separator possible; render as a bullet list of cell values.
        cells = [_escape_md_cell(c) for c in rows[0]]
        return (f"**{table.caption}** (page {table.page})\n\n" if table.caption else "") + "- " + " | ".join(cells)

    header = rows[table.header_row_index]
    data_rows = [r for i, r in enumerate(rows) if i != table.header_row_index]
    ncols = len(header)
    md_lines: List[str] = []
    if table.caption:
        md_lines.append(f"**{table.caption}** (page {table.page})")
        md_lines.append("")
    md_lines.append("| " + " | ".join(_escape_md_cell(c) or " " for c in header) + " |")
    md_lines.append("|" + "|".join(["---"] * ncols) + "|")
    for r in data_rows:
        r = r + [""] * (ncols - len(r))
        md_lines.append("| " + " | ".join(_escape_md_cell(c) or " " for c in r) + " |")
    return "\n".join(md_lines)


def _escape_md_cell(cell: str) -> str:
    return (cell or "").replace("|", "\\|").replace("\n", " ").strip()


def _render_row_chunk(table: _Table, row_idx: int) -> Optional[str]:
    """Render a single data row of a table as a self-contained chunk.

    Includes the caption + column headers + the row values as key-value pairs
    (``Header: Value``) so an embedding for e.g. "Zone 4 wall U-value" hits this
    row directly instead of the flattened multi-row jumble.
    """
    if row_idx == table.header_row_index or row_idx >= len(table.rows):
        return None
    header = table.rows[table.header_row_index]
    row = table.rows[row_idx]
    if not any(cell.strip() for cell in row):
        return None
    lines: List[str] = []
    caption = table.caption or f"Table (page {table.page})"
    lines.append(f"[Row from: {caption} — page {table.page}]")
    lines.append("")
    # Key-value form: "Header cell: value cell" per column.
    for i, cell in enumerate(row):
        col_header = header[i] if i < len(header) else f"col_{i+1}"
        col_header = col_header.strip() or f"col_{i+1}"
        cell = cell.strip()
        if not cell:
            continue
        lines.append(f"- {col_header}: {cell}")
    body = "\n".join(lines)
    # Cap the leading caption/headers block if it grew huge (rare, but defensive).
    if len(body) > _ROW_CHUNK_HEADER_MAX_CHARS + 2000:
        body = body[: _ROW_CHUNK_HEADER_MAX_CHARS + 2000]
    return body


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
    pages: List[_PageContent],
    chunk_size: int,
    overlap: int,
) -> Iterable[Chunk]:
    """Convert page text into overlapping chunks, tracking the current section / part.

    Also emits table chunks (one per table) and per-row chunks for tables with
    at least ``_ROW_CHUNK_MIN_ROWS`` data rows.
    """
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

        # -------- 1) surrounding prose (tables already stripped out of pt.text)
        text = re.sub(r"[ \t]+", " ", pt.text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if text:
            start = 0
            while start < len(text):
                end = min(len(text), start + chunk_size)
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
                        chunk_type="text",
                    )
                if end >= len(text):
                    break
                start = max(end - overlap, start + 1)

        # -------- 2) tables on this page
        for tbl in pt.tables:
            md = _render_table_markdown(tbl)
            if md:
                yield Chunk(
                    text=md,
                    page=pt.page,
                    section=current_section,
                    section_title=current_section_title,
                    part=current_part,
                    chunk_type="table",
                    table_caption=tbl.caption,
                )
            # Per-row chunks: only for tables large enough that a single row can
            # get lost inside a whole-table chunk.
            data_row_count = sum(
                1 for i, r in enumerate(tbl.rows)
                if i != tbl.header_row_index and any(c.strip() for c in r)
            )
            if data_row_count >= _ROW_CHUNK_MIN_ROWS:
                for i in range(len(tbl.rows)):
                    row_text = _render_row_chunk(tbl, i)
                    if row_text:
                        yield Chunk(
                            text=row_text,
                            page=pt.page,
                            section=current_section,
                            section_title=current_section_title,
                            part=current_part,
                            chunk_type="table_row",
                            table_caption=tbl.caption,
                        )



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
