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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)


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
    ) -> List[RetrievedChunk]:
        """Search the requested code indexes and return merged top-k results."""
        if query_vec.ndim == 1:
            query_vec = query_vec.reshape(1, -1)

        all_hits: List[RetrievedChunk] = []
        for code_id in codes:
            idx = self.indexes.get(code_id)
            if idx is None:
                logger.debug("Requested code_id %s not loaded; skipping", code_id)
                continue
            k = min(top_k, idx.faiss_index.ntotal)
            if k == 0:
                continue
            scores, ids = idx.faiss_index.search(query_vec.astype("float32"), k)
            for score, row in zip(scores[0].tolist(), ids[0].tolist()):
                if row < 0 or row >= len(idx.metadata):
                    continue
                m = idx.metadata[row]
                all_hits.append(RetrievedChunk(
                    text=m["text"],
                    page=int(m.get("page", 0)),
                    section=m.get("section"),
                    section_title=m.get("section_title"),
                    part=m.get("part"),
                    source_id=m.get("source_id", code_id),
                    source_label=m.get("source_label", idx.label),
                    score=float(score),
                ))
        all_hits.sort(key=lambda h: h.score, reverse=True)
        return all_hits[:top_k]
