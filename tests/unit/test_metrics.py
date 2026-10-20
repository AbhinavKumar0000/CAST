"""Unit tests for evaluation metrics and utilities."""

import pytest
import numpy as np
from eval.metrics import (
    accuracy_at_k,
    precision_at_k,
    recall_at_k,
    ndcg_at_k,
    jaccard_similarity,
    season_validity_rate,
    hallucination_rate,
    mrr,
)


class TestMetrics:
    """Test core metric functions."""

    def test_accuracy_at_k_perfect(self):
        pred = ["Wheat", "Rice", "Maize", "Soybean", "Cotton"]
        ref = ["Wheat", "Rice", "Maize", "Soybean", "Cotton"]
        assert accuracy_at_k(pred, ref, k=5) == 1.0

    def test_accuracy_at_k_zero(self):
        pred = ["Wheat", "Rice", "Maize", "Soybean", "Cotton"]
        ref = ["Barley", "Pea", "Gram", "Sunflower", "Mustard"]
        assert accuracy_at_k(pred, ref, k=5) == 0.0

    def test_precision_at_k(self):
        pred = ["Wheat", "Rice", "Maize", "Soybean", "Cotton"]
        ref = ["Wheat", "Rice", "Barley", "Pea", "Gram"]
        assert precision_at_k(pred, ref, k=5) == 0.4

    def test_recall_at_k(self):
        pred = ["Wheat", "Rice", "Maize", "Soybean", "Cotton"]
        ref = ["Wheat", "Rice", "Barley", "Pea", "Gram"]
        assert recall_at_k(pred, ref, k=5) == 0.4

    def test_ndcg_at_k_perfect(self):
        pred = ["Wheat", "Rice", "Maize", "Soybean", "Cotton"]
        ref = ["Wheat", "Rice", "Maize", "Soybean", "Cotton"]
        assert ndcg_at_k(pred, ref, k=5) == 1.0

    def test_ndcg_at_k_partial(self):
        pred = ["Wheat", "Rice", "Barley", "Pea", "Gram"]
        ref = ["Wheat", "Rice", "Maize", "Soybean", "Cotton"]
        ndcg = ndcg_at_k(pred, ref, k=5)
        assert 0 < ndcg < 1

    def test_jaccard_similarity(self):
        a = ["Wheat", "Rice", "Maize"]
        b = ["Wheat", "Rice", "Soybean"]
        assert jaccard_similarity(a, b) == 2 / 4  # 2 intersection, 4 union

    def test_season_validity_rate(self):
        # CROP_SEASON_VALIDITY is a dict crop -> set of valid seasons
        pred = ["Wheat", "Rice", "Maize", "Soybean", "Cotton"]
        # Wheat=Rabi, Rice=Kharif, Maize=Kharif, Soybean=Kharif, Cotton=Kharif
        assert season_validity_rate(pred, "Kharif") == 0.8  # 4/5
        assert season_validity_rate(pred, "Rabi") == 0.2  # 1/5

    def test_hallucination_rate(self):
        pred = [["Wheat", "Rice", "FakeCrop", "Soybean", "Cotton"]]
        assert hallucination_rate(pred) == 0.2  # 1/5

    def test_mrr(self):
        pred = ["Fake", "Wheat", "Rice", "Maize", "Soybean"]
        ref = ["Wheat", "Rice", "Maize", "Soybean", "Cotton"]
        mrr_val = mrr(pred, ref)
        assert mrr_val == 0.5  # First relevant at rank 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])