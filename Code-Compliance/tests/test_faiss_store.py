import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.retriever.faiss_store import FaissStore, _CodeIndex


class FakeIndex:
    def __init__(self, scores, rows, total):
        self.scores = scores
        self.rows = rows
        self.ntotal = total

    def search(self, query, count):
        return np.array([self.scores[:count]]), np.array([self.rows[:count]])


class TableRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.metadata = [
            {"text": "See Table 3.2.2.2.", "page": 75},
            {"text": "Full table with climate zones and Walls 0.290 0.265",
             "page": 76, "chunk_type": "table", "table_caption": "Table 3.2.2.2."},
            {"text": "Walls 0.290 0.265", "page": 76, "chunk_type": "table_row",
             "table_caption": "Table 3.2.2.2."},
            {"text": "Different table", "page": 80, "chunk_type": "table",
             "table_caption": "Table 3.2.2.20."},
        ]
        self.index = _CodeIndex("necb_2020", "NECB 2020",
                                FakeIndex([0.9, 0.8, 0.7], [0, 2, 1], 4),
                                self.metadata, {})
        self.store = FaissStore({"necb_2020": self.index})

    def search(self, **kwargs):
        return self.store.search(np.zeros(4), ["necb_2020"], **kwargs)

    def test_explicit_table_precedes_prose_reference(self):
        hits = self.search(top_k=1, question="Show table 3.2.2.2.")
        self.assertEqual(hits[0].text, self.metadata[1]["text"])

    def test_table_number_does_not_match_longer_number(self):
        hits = self.search(top_k=4, question="TABLE 3.2.2.2")
        self.assertNotIn("Different table", [hit.text for hit in hits])

    def test_semantic_row_is_promoted_to_full_table_and_deduplicated(self):
        hits = self.search(top_k=3, question="required wall conductances")
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[1].text, self.metadata[1]["text"])
        self.assertGreater(hits[1].score, 0)

    def test_missing_parent_preserves_row(self):
        self.metadata[1]["table_caption"] = "Table 9.9.9.9."
        hits = self.search(top_k=2)
        self.assertEqual(hits[1].text, "Walls 0.290 0.265")

    def test_wall_conductance_keywords_recover_table_missed_by_vectors(self):
        metadata = [
            {"text": "Preface and administrative provisions"},
            {"text": "AboveGround Walls MaximumOverallThermalTransmittance 0.290",
             "page": 76, "chunk_type": "table", "table_caption": "Table 3.2.2.2."},
            {"text": "Lighting power density limits"},
            {"text": "Ventilation requirements"},
        ]
        self.store.indexes["necb_2020"] = _CodeIndex(
            "necb_2020", "NECB 2020", FakeIndex([0.9], [0], 4), metadata, {}
        )
        hits = self.search(question="Could you show me the table in the NECB "
                  "that deals with the required wall conductances?", top_k=1)
        self.assertEqual(metadata[1]["text"], hits[0].text)

    def test_selected_codes_are_respected(self):
        hits = self.store.search(np.zeros(4), ["necb_2025"],
                                 question="Table 3.2.2.2")
        self.assertEqual(hits, [])

    def test_zero_results_requested(self):
        self.assertEqual(self.search(top_k=0), [])


if __name__ == "__main__":
    unittest.main()