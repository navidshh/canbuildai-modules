"""Sync pre-built FAISS bundles from S3 to a local directory at service startup."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_BUNDLE_FILES = ("index.faiss", "metadata.jsonl", "manifest.json")


def download_bundles(
    bucket: str,
    code_ids: Iterable[str],
    local_root: Path,
    region: str | None = None,
    prefix: str = "kb",
) -> list[str]:
    """Download each ``kb/<code_id>/*`` bundle from S3 into ``local_root/<code_id>/``.

    Returns the list of code_ids that were successfully downloaded (fully or partially).
    """
    region = region or os.getenv("AWS_REGION", "ca-central-1")
    s3 = boto3.client("s3", region_name=region)
    local_root = Path(local_root)
    local_root.mkdir(parents=True, exist_ok=True)

    downloaded: list[str] = []
    for code_id in code_ids:
        target = local_root / code_id
        target.mkdir(parents=True, exist_ok=True)
        ok = True
        for name in _BUNDLE_FILES:
            key = f"{prefix}/{code_id}/{name}"
            dest = target / name
            try:
                s3.download_file(bucket, key, str(dest))
                logger.info("Downloaded s3://%s/%s -> %s", bucket, key, dest)
            except ClientError as e:
                logger.warning("Skipping s3://%s/%s: %s", bucket, key, e.response.get("Error", {}).get("Code"))
                if name in ("index.faiss", "metadata.jsonl"):
                    ok = False
        if ok:
            downloaded.append(code_id)
    return downloaded
