"""Runtime paths for the standalone HOT2000 module."""

import os
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = Path(os.getenv("HOT2000_MODEL_DIR", MODULE_ROOT / "model"))
REPRESENTATIVES_DIR = Path(
    os.getenv("HOT2000_H2K_DIR", MODULE_ROOT / "representatives")
)
MANIFEST_PATH = Path(
    os.getenv("HOT2000_H2K_MANIFEST", REPRESENTATIVES_DIR / "manifest.csv")
)
RESULTS_PATH = Path(
    os.getenv("HOT2000_RESULTS_PATH", REPRESENTATIVES_DIR / "results.csv")
)
DOWNLOADS_DIR = Path(
    os.getenv("HOT2000_DOWNLOADS_DIR", MODULE_ROOT / "runtime" / "downloads")
)