import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.main import BuildingInput, app
from app.prediction import load_artifacts, predict_cluster


class ResidentialInputTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "houseregion": "Ontario",
            "clientpcode": "N1H",
            "typeofhouse": "Single Detached",
            "storeys": "Two storeys",
            "footprint": 79.5,
            "furnacefuel": "Natural Gas",
            "furnacetype": "Condensing furnace",
            "pdhwfuel": "Natural Gas",
            "pdhwtype": "Conventional tank",
            "aircondtype": "Not installed",
        }

    def test_schema_requires_only_ten_inputs(self):
        schema = BuildingInput.model_json_schema()
        self.assertEqual(set(schema["required"]), set(self.payload))
        self.assertEqual(set(schema["properties"]), set(self.payload))
        self.assertEqual(BuildingInput(**self.payload).model_dump(), self.payload)

    def test_legacy_foundation_input_is_ignored(self):
        building = BuildingInput(**self.payload, fndtype="B1;C1;F1")
        self.assertEqual(building.model_dump(), self.payload)

    def test_ten_input_request_returns_downloadable_model(self):
        with TemporaryDirectory() as directory:
            with patch("app.main.DOWNLOADS_DIR", Path(directory)), TestClient(app) as client:
                response = client.post("/api/predict", json=self.payload)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertIn("eui", result)
                self.assertTrue((Path(directory) / result["filename"]).is_file())
                download = client.get(result["download_path"])
                self.assertEqual(download.status_code, 200)
                self.assertTrue(download.content)

    def test_missing_matching_input_is_rejected(self):
        payload = self.payload.copy()
        del payload["furnacefuel"]
        with TestClient(app) as client:
            response = client.post("/api/predict", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_predictions_match_legacy_pipeline(self):
        features = {name.upper(): value for name, value in self.payload.items()}
        preprocessor, cluster_centers = load_artifacts()
        actual_cluster = predict_cluster(features)
        reference = preprocessor.transform(
            pd.DataFrame([{**features, "FNDTYPE": ""}])
        ).astype(np.float32)

        for foundation in ("", "B1", "C1;F1", "B1;B2;P1"):
            with self.subTest(foundation=foundation):
                transformed = preprocessor.transform(
                    pd.DataFrame([{**features, "FNDTYPE": foundation}])
                ).astype(np.float32)
                np.testing.assert_array_equal(transformed, reference)
                expected_cluster = int(
                    np.argmin(np.linalg.norm(cluster_centers - transformed, axis=1))
                )
                self.assertEqual(actual_cluster, expected_cluster)


if __name__ == "__main__":
    unittest.main()