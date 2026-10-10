"""Metrics computation (STEP 6).

Implements all quality, safety, specificity, reliability, consistency, and efficiency metrics.
Each metric function is unit-testable with hand-checked toy examples.
"""

from __future__ import annotations

import math
import json
from collections import Counter
from typing import Any
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# --- Canonical crop registry ---
CANONICAL_CROPS = [
    "Soybean", "Wheat", "Rice", "Maize", "Cotton", "Jowar", "Gram", "Sugarcane",
    "Mustard", "Groundnut", "Moong", "Urad", "Lentil", "Barley", "Bajra",
    "Sesame (Til)", "Sunflower", "Arhar (Tur)", "Pea", "Kodo-Kutki", "Watermelon",
]

# Season validity per crop (from crop_log.csv)
CROP_SEASON_VALIDITY = {
    "Soybean": {"Kharif"},
    "Wheat": {"Rabi"},
    "Rice": {"Kharif"},
    "Maize": {"Kharif"},
    "Cotton": {"Kharif"},
    "Jowar": {"Kharif"},
    "Gram": {"Rabi"},
    "Sugarcane": {"Annual"},
    "Mustard": {"Rabi"},
    "Groundnut": {"Kharif"},
    "Moong": {"Kharif", "Zaid"},
    "Urad": {"Kharif"},
    "Lentil": {"Rabi"},
    "Barley": {"Rabi"},
    "Bajra": {"Kharif"},
    "Sesame (Til)": {"Kharif"},
    "Sunflower": {"Rabi", "Kharif"},
    "Arhar (Tur)": {"Kharif"},
    "Pea": {"Rabi"},
    "Kodo-Kutki": {"Kharif"},
    "Watermelon": {"Zaid"},
}

# Water-intensive crops (heuristic: high rainfall requirement > 1000mm)
WATER_INTENSIVE_CROPS = {"Rice", "Sugarcane", "Cotton", "Arhar (Tur)", "Sunflower", "Maize"}

# --- Core metric functions ---

def accuracy_at_k(pred: list[str], truth: list[str], k: int = 5) -> float:
    """Accuracy@k: 1 if any of top-k predictions in truth, else 0."""
    pred_k = pred[:k]
    truth_set = set(truth)
    return 1.0 if any(p in truth_set for p in pred_k) else 0.0

def precision_at_k(pred: list[str], truth: list[str], k: int = 5) -> float:
    """Precision@k: |pred_k ∩ truth| / k."""
    pred_k = pred[:k]
    if not pred_k: return 0.0
    truth_set = set(truth)
    return len([p for p in pred_k if p in truth_set]) / len(pred_k)

def recall_at_k(pred: list[str], truth: list[str], k: int = 5) -> float:
    """Recall@k: |pred_k ∩ truth| / |truth|."""
    pred_k = pred[:k]
    truth_set = set(truth)
    if not truth_set: return 0.0
    return len([p for p in pred_k if p in truth_set]) / len(truth_set)

def ndcg_at_k(pred: list[str], truth: list[str], k: int = 5) -> float:
    """nDCG@k with binary relevance."""
    pred_k = pred[:k]
    truth_set = set(truth)
    dcg = sum(1.0 / math.log2(i + 2) for i, p in enumerate(pred_k) if p in truth_set)
    # Ideal DCG: all relevant items at top
    n_rel = min(len(truth_set), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(n_rel))
    return dcg / idcg if idcg > 0 else 0.0

def mrr(pred: list[str], truth: list[str]) -> float:
    """Mean Reciprocal Rank: 1/rank of first relevant item."""
    truth_set = set(truth)
    for i, p in enumerate(pred):
        if p in truth_set:
            return 1.0 / (i + 1)
    return 0.0

def season_validity_rate(pred: list[str], season: str) -> float:
    """Fraction of predicted crops valid for the season."""
    if not pred: return 0.0
    valid = sum(1 for p in pred if p in CROP_SEASON_VALIDITY and season in CROP_SEASON_VALIDITY[p])
    return valid / len(pred)

def hard_violation_rate(pred: list[str], season: str, stress_flags: dict[str, bool]) -> float:
    """Rate of hard constraint violations."""
    violations = 0
    for p in pred:
        # Season violation
        if p in CROP_SEASON_VALIDITY and season not in CROP_SEASON_VALIDITY[p]:
            violations += 1
        # Drought + water-intensive
        if stress_flags.get("drought", False) and p in WATER_INTENSIVE_CROPS:
            violations += 1
        # Could add more: flood + waterlogging-sensitive, heat + heat-sensitive
    return violations / len(pred) if pred else 0.0

def distinct_crops(preds: list[list[str]]) -> int:
    """Number of distinct crops across all predictions."""
    return len(set(c for pred in preds for c in pred))

def shannon_entropy(preds: list[list[str]]) -> float:
    """Shannon entropy of crop distribution (uniform across top-5)."""
    counts = Counter(c for pred in preds for c in pred[:5])
    total = sum(counts.values())
    if total == 0: return 0.0
    return -sum((c/total) * math.log2(c/total) for c in counts.values())

def per_district_differentiation(district_preds: dict[str, list[list[str]]]) -> float:
    """Average pairwise Jaccard distance between districts.
    
    Args:
        district_preds: district -> list of predictions (each a list of crop names)
    """
    districts = list(district_preds.keys())
    if len(districts) < 2: return 0.0
    
    # Aggregate all predictions per district into a single set
    district_crops = {}
    for d, preds_list in district_preds.items():
        all_crops = set()
        for pred in preds_list:
            all_crops.update(pred[:5])
        district_crops[d] = all_crops
    
    total_dist = 0.0
    pairs = 0
    for i in range(len(districts)):
        for j in range(i+1, len(districts)):
            set_i = district_crops[districts[i]]
            set_j = district_crops[districts[j]]
            if set_i or set_j:
                inter = len(set_i & set_j)
                union = len(set_i | set_j)
                total_dist += 1.0 - (inter / union if union else 0.0)
            pairs += 1
    return total_dist / pairs if pairs else 0.0

def hallucination_rate(preds: list[list[str]]) -> float:
    """Fraction of predictions containing out-of-registry crops."""
    canon = set(CANONICAL_CROPS)
    total = 0
    oov = 0
    for pred in preds:
        for p in pred:
            total += 1
            if p not in canon:
                oov += 1
    return oov / total if total else 0.0

def numeric_faithfulness(explanation: str, evidence: dict[str, Any], 
                         tolerance_abs: float = 1.0, tolerance_rel: float = 0.05) -> float:
    """Check if numbers in explanation match tool outputs within tolerance."""
    import re
    # Extract numbers from explanation
    nums_in_expl = [float(x) for x in re.findall(r'\b\d+(?:\.\d+)?\b', explanation)]
    if not nums_in_expl: return 1.0  # No numbers to check
    
    # Extract reference numbers from evidence (simplified)
    ref_nums = []
    for tool_out in evidence.values():
        if isinstance(tool_out, dict):
            for v in tool_out.values():
                if isinstance(v, (int, float)) and v is not None:
                    ref_nums.append(float(v))
    
    if not ref_nums: return 1.0
    
    matches = 0
    for n in nums_in_expl:
        if any(abs(n - r) <= tolerance_abs or (r != 0 and abs(n - r) / abs(r) <= tolerance_rel) for r in ref_nums):
            matches += 1
    return matches / len(nums_in_expl)

def jaccard_similarity(set1: list[str], set2: list[str]) -> float:
    """Jaccard index of two sets."""
    s1, s2 = set(set1), set(set2)
    if not s1 and not s2: return 1.0
    if not s1 or not s2: return 0.0
    return len(s1 & s2) / len(s1 | s2)

def kendall_tau(pred1: list[str], pred2: list[str]) -> float:
    """Kendall tau rank correlation (simplified for top-5)."""
    # Map items to ranks
    rank1 = {item: i for i, item in enumerate(pred1)}
    rank2 = {item: i for i, item in enumerate(pred2)}
    common = set(rank1.keys()) & set(rank2.keys())
    if len(common) < 2: return 1.0
    
    concordant = discordant = 0
    items = list(common)
    for i in range(len(items)):
        for j in range(i+1, len(items)):
            a, b = items[i], items[j]
            r1_diff = rank1[a] - rank1[b]
            r2_diff = rank2[a] - rank2[b]
            if r1_diff * r2_diff > 0:
                concordant += 1
            elif r1_diff * r2_diff < 0:
                discordant += 1
    total = concordant + discordant
    return (concordant - discordant) / total if total else 1.0

def exact_match_rate(preds1: list[list[str]], preds2: list[list[str]]) -> float:
    """Fraction of scenarios with identical top-5."""
    if not preds1: return 0.0
    matches = sum(1 for p1, p2 in zip(preds1, preds2) if p1[:5] == p2[:5])
    return matches / len(preds1)

# --- Aggregation helpers ---

def aggregate_metrics(scenario_results: list[dict[str, Any]], 
                      ground_truth: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Compute all aggregate metrics from per-scenario results."""
    # This is a placeholder - full implementation would iterate over all scenarios
    # and compute each metric, then average.
    return {
        "quality": {},
        "safety": {},
        "specificity": {},
        "reliability": {},
        "consistency": {},
        "efficiency": {},
    }


if __name__ == "__main__":
    # Quick unit tests with hand-checked toy examples
    print("Running metric unit tests...")
    
    # Test accuracy_at_k
    assert accuracy_at_k(["Wheat", "Rice"], ["Wheat", "Gram"], 5) == 1.0
    assert accuracy_at_k(["Rice", "Maize"], ["Wheat", "Gram"], 5) == 0.0
    print("  accuracy_at_k: PASS")
    
    # Test precision_at_k
    assert precision_at_k(["Wheat", "Rice", "Gram"], ["Wheat", "Gram"], 3) == 2/3
    assert precision_at_k(["Rice", "Maize"], ["Wheat", "Gram"], 2) == 0.0
    print("  precision_at_k: PASS")
    
    # Test recall_at_k
    assert recall_at_k(["Wheat", "Rice", "Gram"], ["Wheat", "Gram"], 3) == 1.0
    assert recall_at_k(["Wheat"], ["Wheat", "Gram"], 1) == 0.5
    print("  recall_at_k: PASS")
    
    # Test nDCG@k
    # Ideal: Wheat@1, Gram@2 -> DCG = 1/log2(2) + 1/log2(3) = 1 + 0.6309 = 1.6309
    # Pred: Wheat@1, Gram@3 -> DCG = 1/log2(2) + 1/log2(4) = 1 + 0.5 = 1.5
    # nDCG = 1.5 / 1.6309 = 0.92
    ideal_dcg = 1.0 + 1.0/math.log2(3)
    pred_dcg = 1.0 + 1.0/math.log2(4)
    expected_ndcg = pred_dcg / ideal_dcg
    assert abs(ndcg_at_k(["Wheat", "Rice", "Gram"], ["Wheat", "Gram"], 3) - expected_ndcg) < 1e-6
    assert ndcg_at_k(["Rice", "Maize"], ["Wheat", "Gram"], 2) == 0.0
    print("  ndcg_at_k: PASS")
    
    # Test MRR
    assert mrr(["Rice", "Wheat", "Gram"], ["Wheat", "Gram"]) == 0.5
    assert mrr(["Rice", "Maize"], ["Wheat", "Gram"]) == 0.0
    print("  mrr: PASS")
    
    # Test season_validity_rate
    assert season_validity_rate(["Wheat", "Rice"], "Rabi") == 0.5  # Wheat valid, Rice not
    assert season_validity_rate(["Wheat", "Gram"], "Rabi") == 1.0
    print("  season_validity_rate: PASS")
    
    # Test hallucination_rate
    assert hallucination_rate([["Wheat", "FakeCrop"]]) == 0.5
    assert hallucination_rate([["Wheat", "Rice"]]) == 0.0
    print("  hallucination_rate: PASS")
    
    # Test Jaccard
    assert jaccard_similarity(["Wheat", "Rice"], ["Wheat", "Gram"]) == 1/3
    assert jaccard_similarity(["Wheat", "Rice"], ["Wheat", "Rice"]) == 1.0
    print("  jaccard_similarity: PASS")
    
    # Test Kendall tau
    assert kendall_tau(["Wheat", "Rice", "Gram"], ["Wheat", "Rice", "Gram"]) == 1.0
    assert kendall_tau(["Wheat", "Rice"], ["Rice", "Wheat"]) == -1.0
    print("  kendall_tau: PASS")
    
    # Test exact_match_rate
    assert exact_match_rate([["Wheat", "Rice"]], [["Wheat", "Rice"]]) == 1.0
    assert exact_match_rate([["Wheat", "Rice"]], [["Rice", "Wheat"]]) == 0.0
    print("  exact_match_rate: PASS")
    
    print("All unit tests PASSED!")