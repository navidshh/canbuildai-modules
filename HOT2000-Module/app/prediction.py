"""CPU-only cluster inference for the deployed HOT2000 model."""

from functools import lru_cache
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from . import custom_transformers
from .config import MODEL_DIR


# The fitted pickle was created when this module had a top-level import path.
sys.modules.setdefault("custom_transformers", custom_transformers)


@lru_cache(maxsize=1)
def load_artifacts(model_dir=None):
    """Load the fitted preprocessor and K=1000 cluster centres."""
    artifact_dir = Path(model_dir) if model_dir else MODEL_DIR
    preprocessor = joblib.load(artifact_dir / "preprocessor_pipeline.pkl")
    cluster_centers = np.load(artifact_dir / "cluster_centers.npy")
    return preprocessor, cluster_centers


def predict_cluster(input_data: dict, model_dir=None) -> int:
    """Return the nearest model cluster for one building description."""
    preprocessor, cluster_centers = load_artifacts(model_dir)
    transformed = preprocessor.transform(pd.DataFrame([input_data])).astype(
        np.float32
    )
    distances = np.linalg.norm(cluster_centers - transformed, axis=1)
    return int(np.argmin(distances))