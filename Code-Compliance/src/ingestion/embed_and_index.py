"""Embed text chunks with Amazon Titan (Bedrock) and build a FAISS index per code.

Output layout (per code_id, e.g. ``necb_2020``):
    indexes/necb_2020/index.faiss
    indexes/necb_2020/metadata.jsonl   # one JSON per line, aligned to FAISS row order
    indexes/necb_2020/manifest.json    # {code_id, embed_model, dim, num_chunks, built_at}

Uploaded to S3 as: s3://<KB_BUCKET>/kb/<code_id>/{index.faiss,metadata.jsonl,manifest.json}
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Sequence

import boto3
import numpy as np

from .pdf_chunker import Chunk

logger = logging.getLogger(__name__)

DEFAULT_EMBED_MODEL = os.getenv("BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
DEFAULT_EMBED_DIM = int(os.getenv("BEDROCK_EMBED_DIM", "1024"))
DEFAULT_REGION = os.getenv("AWS_REGION", "ca-central-1")


class BedrockEmbedder:
    """Thin wrapper around Bedrock ``InvokeModel`` for Titan text embeddings."""

    def __init__(
        self,
        model_id: str = DEFAULT_EMBED_MODEL,
        dim: int = DEFAULT_EMBED_DIM,
        region: str = DEFAULT_REGION,
        client=None,
    ):
        self.model_id = model_id
        self.dim = dim
        self.region = region
        self.client = client or boto3.client("bedrock-runtime", region_name=region)

    def embed(self, text: str) -> np.ndarray:
        body = json.dumps({
            "inputText": text[:8000],  # Titan v2 accepts up to ~8k tokens; truncate defensively
            "dimensions": self.dim,
            "normalize": True,
        })
        resp = self.client.invoke_model(
            modelId=self.model_id,
            contentType="application/json",
            accept="application/json",
            body=body,
        )
        payload = json.loads(resp["body"].read())
        vec = np.asarray(payload["embedding"], dtype="float32")
        if vec.shape[0] != self.dim:
            raise RuntimeError(f"Expected embedding dim {self.dim}, got {vec.shape[0]}")
        return vec

    def embed_batch(self, texts: Sequence[str], sleep_between: float = 0.0) -> np.ndarray:
        """Titan does not batch server-side; loop with light retry."""
        out = np.zeros((len(texts), self.dim), dtype="float32")
        for i, t in enumerate(texts):
            for attempt in range(4):
                try:
                    out[i] = self.embed(t)
                    break
                except Exception as e:  # noqa: BLE001
                    wait = 2 ** attempt
                    logger.warning("Embed failed (%s); retrying in %ss", e, wait)
                    time.sleep(wait)
            else:
                raise RuntimeError(f"Failed to embed chunk {i} after retries")
            if sleep_between:
                time.sleep(sleep_between)
            if (i + 1) % 50 == 0:
                logger.info("  embedded %d / %d", i + 1, len(texts))
        return out


def build_faiss_index(vectors: np.ndarray):
    """Build a cosine-similarity FAISS index. Titan v2 embeddings are already L2-normalized."""
    import faiss  # type: ignore

    dim = vectors.shape[1]
    index = faiss.IndexFlatIP(dim)  # inner product == cosine on normalized vectors
    index.add(vectors)
    return index


def write_index_bundle(
    out_dir: Path,
    code_id: str,
    chunks: List[Chunk],
    vectors: np.ndarray,
    embed_model: str,
) -> None:
    import faiss  # type: ignore

    out_dir.mkdir(parents=True, exist_ok=True)

    index = build_faiss_index(vectors)
    faiss.write_index(index, str(out_dir / "index.faiss"))

    with open(out_dir / "metadata.jsonl", "w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")

    manifest = {
        "code_id": code_id,
        "embed_model": embed_model,
        "dim": int(vectors.shape[1]),
        "num_chunks": len(chunks),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("Wrote index bundle for %s: %d chunks -> %s", code_id, len(chunks), out_dir)


def upload_bundle_to_s3(local_dir: Path, bucket: str, code_id: str, region: str = DEFAULT_REGION) -> None:
    s3 = boto3.client("s3", region_name=region)
    for name in ("index.faiss", "metadata.jsonl", "manifest.json"):
        p = local_dir / name
        key = f"kb/{code_id}/{name}"
        logger.info("Uploading s3://%s/%s", bucket, key)
        s3.upload_file(str(p), bucket, key)
