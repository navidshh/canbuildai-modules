"""Offline entrypoint: ingest all enabled PDFs from knowledge_bases.json into FAISS indexes.

Usage (from surrogate-app/Code-Compliance/):
    python -m src.ingestion.build_index                    # build all enabled codes
    python -m src.ingestion.build_index --only necb_2020   # rebuild one
    python -m src.ingestion.build_index --upload           # also push to S3 (uses $CODE_ASSISTANT_KB_BUCKET)
    python -m src.ingestion.build_index --no-embed         # dry run (chunk only, skip Bedrock)

Requires AWS credentials with Bedrock InvokeModel permission for the embedding model.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import List

from .embed_and_index import (
    DEFAULT_EMBED_MODEL,
    BedrockEmbedder,
    upload_bundle_to_s3,
    write_index_bundle,
)
from .pdf_chunker import Chunk, chunk_pdf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("build_index")

MODULE_ROOT = Path(__file__).resolve().parents[2]  # surrogate-app/Code-Compliance/
REGISTRY_PATH = MODULE_ROOT / "knowledge_bases.json"
DATA_DIR = MODULE_ROOT / "data"
INDEX_DIR = MODULE_ROOT / "indexes"


def load_registry() -> List[dict]:
    with open(REGISTRY_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)["codes"]


def process_code(entry: dict, do_embed: bool, do_upload: bool, bucket: str | None) -> None:
    code_id = entry["id"]
    pdf_path = DATA_DIR / entry["pdf"]
    label = entry["label"]

    logger.info("=== %s (%s) ===", code_id, label)
    if not pdf_path.exists():
        logger.error("Missing PDF: %s", pdf_path)
        return

    chunks: List[Chunk] = chunk_pdf(pdf_path, source_id=code_id, source_label=label)
    logger.info("Chunk stats: total=%d, mean_len=%d",
                len(chunks),
                (sum(len(c.text) for c in chunks) // max(1, len(chunks))))

    if not do_embed:
        # Dry run: dump chunks only.
        out = INDEX_DIR / code_id
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "metadata.jsonl", "w", encoding="utf-8") as fh:
            for c in chunks:
                fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
        logger.info("Dry-run wrote %s (no embeddings, no FAISS)", out / "metadata.jsonl")
        return

    embedder = BedrockEmbedder()
    logger.info("Embedding %d chunks with %s ...", len(chunks), embedder.model_id)
    vectors = embedder.embed_batch([c.text for c in chunks])

    out = INDEX_DIR / code_id
    write_index_bundle(out, code_id, chunks, vectors, embedder.model_id)

    if do_upload:
        if not bucket:
            logger.error("--upload requested but CODE_ASSISTANT_KB_BUCKET is not set")
            sys.exit(2)
        upload_bundle_to_s3(out, bucket, code_id)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="Process only this code_id (repeatable via commas)", default=None)
    ap.add_argument("--upload", action="store_true", help="Upload built indexes to S3")
    ap.add_argument("--no-embed", action="store_true", help="Chunk only; skip Bedrock calls")
    ap.add_argument("--bucket", default=os.getenv("CODE_ASSISTANT_KB_BUCKET"), help="S3 bucket for indexes")
    args = ap.parse_args()

    only = set(x.strip() for x in args.only.split(",")) if args.only else None
    registry = load_registry()

    for entry in registry:
        if not entry.get("enabled", True):
            continue
        if only and entry["id"] not in only:
            continue
        try:
            process_code(entry, do_embed=not args.no_embed, do_upload=args.upload, bucket=args.bucket)
        except Exception as e:  # noqa: BLE001
            logger.exception("Failed processing %s: %s", entry["id"], e)


if __name__ == "__main__":
    main()
