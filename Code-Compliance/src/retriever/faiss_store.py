"""FAISS-based retrieval over pre-built code indexes.

At service boot, indexes are downloaded from S3 (see ``s3_sync.load_all``) into
a local directory, then each ``code_id`` is loaded into memory. Query time:

    store = FaissStore.load_dir(local_dir, registry)
    hits = store.search("What is the minimum RSI for wall assemblies in Zone 7?",
                        codes=["necb_2020", "necb_2025"], top_k=6)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

_TABLE_NUMBER_RE = re.compile(
    r"\btable\s+([A-Z]?\d+(?:\.\d+)*(?:\.?-[A-Z])?)", re.IGNORECASE
)
_STOP_WORDS = set(
    "a an and are as at be by can code could deals do does for from how i in is it "
    "me necb nbc of on or please required requirements show table tables that the "
    "their them there these this to under using was what which with would you".split()
)
_TERM_ALIASES = {
    "walls": "wall", "roofs": "roof", "floors": "floor",
    "conductance": "transmittance", "conductances": "transmittance",
    "uvalue": "transmittance", "uvalues": "transmittance",
}


def _search_tokens(text: str) -> List[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"\bu[ -]values?\b", "transmittance", text, flags=re.IGNORECASE)
    return [
        _TERM_ALIASES.get(token, token)
        for token in re.findall(r"[^\W_]+", text.lower())
        if token not in _STOP_WORDS
    ]


@dataclass
class RetrievedChunk:
    text: str
    page: int
    section: Optional[str]
    section_title: Optional[str]
    part: Optional[str]
    source_id: str
    source_label: str
    score: float

    def citation(self) -> str:
        bits = [self.source_label]
        if self.section:
            bits.append(f"§{self.section}")
            if self.section_title:
                bits[-1] += f" {self.section_title}"
        bits.append(f"p.{self.page}")
        return ", ".join(bits)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "page": self.page,
            "section": self.section,
            "section_title": self.section_title,
            "part": self.part,
            "source_id": self.source_id,
            "source_label": self.source_label,
            "score": float(self.score),
            "citation": self.citation(),
        }


@dataclass
class _CodeIndex:
    code_id: str
    label: str
    faiss_index: object   # faiss.Index
    metadata: List[dict]  # aligned to FAISS rows
    manifest: dict
    lexical_index: Optional[BM25Okapi] = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        corpus = [_search_tokens(metadata["text"]) for metadata in self.metadata]
        if any(corpus):
            self.lexical_index = BM25Okapi(corpus)


@dataclass
class FaissStore:
    indexes: Dict[str, _CodeIndex] = field(default_factory=dict)

    # ---------------------------------------------------------------- loading
    @classmethod
    def load_dir(cls, root: Path, registry: List[dict]) -> "FaissStore":
        import faiss  # type: ignore

        root = Path(root)
        store = cls()
        for entry in registry:
            if not entry.get("enabled", True):
                continue
            code_id = entry["id"]
            bundle = root / code_id
            idx_file = bundle / "index.faiss"
            meta_file = bundle / "metadata.jsonl"
            manifest_file = bundle / "manifest.json"
            if not idx_file.exists() or not meta_file.exists():
                logger.warning("Skipping %s: missing bundle at %s", code_id, bundle)
                continue
            index = faiss.read_index(str(idx_file))
            with open(meta_file, "r", encoding="utf-8") as fh:
                metadata = [json.loads(line) for line in fh if line.strip()]
            manifest = json.loads(manifest_file.read_text(encoding="utf-8")) if manifest_file.exists() else {}
            if index.ntotal != len(metadata):
                logger.warning("Index/metadata mismatch for %s (%d vs %d)", code_id, index.ntotal, len(metadata))
            store.indexes[code_id] = _CodeIndex(
                code_id=code_id,
                label=entry["label"],
                faiss_index=index,
                metadata=metadata,
                manifest=manifest,
            )
            logger.info("Loaded %s: %d vectors", code_id, index.ntotal)
        return store

    # ---------------------------------------------------------------- search
    def available_codes(self) -> List[str]:
        return list(self.indexes.keys())

    def search(
        self,
        query_vec: np.ndarray,
        codes: Sequence[str],
        top_k: int = 6,
        question: str = "",
    ) -> List[RetrievedChunk]:
        """Merge semantic and exact-table hits, preserving full table headers."""
        if top_k <= 0:
            return []
        table_numbers = {number.upper() for number in _TABLE_NUMBER_RE.findall(question)}
        wants_table = bool(re.search(r"\btables?\b", question, re.IGNORECASE))
        if query_vec.ndim == 1:
            query_vec = query_vec.reshape(1, -1)

        all_hits: List[RetrievedChunk] = []
        for code_id in codes:
            idx = self.indexes.get(code_id)
            if idx is None:
                logger.debug("Requested code_id %s not loaded; skipping", code_id)
                continue
            k = min(max(top_k * 4, 24), idx.faiss_index.ntotal)
            if k == 0:
                continue
            scores, ids = idx.faiss_index.search(query_vec.astype("float32"), k)
            candidates = {
                row: 1.0 / (60 + rank)
                for rank, row in enumerate(ids[0].tolist(), start=1)
            }
            tokens = _search_tokens(question)
            if tokens and idx.lexical_index is not None:
                lexical_scores = idx.lexical_index.get_scores(tokens)
                if wants_table:
                    table_scores = np.array([
                        score if metadata.get("chunk_type") == "table" else 0.0
                        for score, metadata in zip(lexical_scores, idx.metadata)
                    ])
                    if np.any(table_scores > 0):
                        lexical_scores = table_scores
                ranked_rows = np.argsort(-lexical_scores, kind="stable")[:k]
                for rank, row in enumerate(ranked_rows.tolist(), start=1):
                    if lexical_scores[row] > 0:
                        weight = 2.0 if wants_table else 1.0
                        candidates[row] = candidates.get(row, 0.0) + weight / (60 + rank)
            table_rows: dict[tuple, int] = {}
            for row, metadata in enumerate(idx.metadata):
                if metadata.get("chunk_type") != "table":
                    continue
                caption = metadata.get("table_caption") or ""
                if caption:
                    table_rows[(metadata.get("page"), caption)] = row
                numbers = {number.upper() for number in _TABLE_NUMBER_RE.findall(caption)}
                if table_numbers & numbers:
                    candidates[row] = 2.0

            promoted: dict[int, float] = {}
            for row, score in candidates.items():
                if row < 0 or row >= len(idx.metadata):
                    continue
                metadata = idx.metadata[row]
                if metadata.get("chunk_type") == "table_row":
                    row = table_rows.get(
                        (metadata.get("page"), metadata.get("table_caption")), row
                    )
                promoted[row] = max(score, promoted.get(row, float("-inf")))

            for row, score in promoted.items():
                metadata = idx.metadata[row]
                all_hits.append(RetrievedChunk(
                    text=metadata["text"],
                    page=int(metadata.get("page", 0)),
                    section=metadata.get("section"),
                    section_title=metadata.get("section_title"),
                    part=metadata.get("part"),
                    source_id=metadata.get("source_id", code_id),
                    source_label=metadata.get("source_label", idx.label),
                    score=float(score),
                ))
        all_hits.sort(key=lambda h: h.score, reverse=True)
        return all_hits[:top_k]
