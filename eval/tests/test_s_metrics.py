"""Unit tests for S-series metrics (STEP BEFORE 3).

Imports the metric functions directly from eval/scripts/score_s.py so the tests
exercise the exact code the scorer uses.

Metrics (PROTOCOL 8.32.4 / S_ORACLE.md 3):
- Stale@5     = |top5 ∩ D| / |D|, D = F0 \\ F1; 0 when |D| == 0
- Violation@5 = |top5 ∩ (U \\ F1)| / min(5, |top5|); 0 when top5 empty
- Shift@5     = 1 - Jaccard(top5_base, top5); 0 when both empty
- Drop-faithful = 1 - Stale@5
- false-change  = Shift@5 > 0 on cells where |D| == 0 (computed in scorer)

Hand-built cases plus edge cases: empty top-5, <5 crops, unknown crop names,
crops outside the oracle universe, |D| == 0.
"""
import importlib.util
import math
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "score_s",
    Path(__file__).resolve().parent.parent / "scripts" / "score_s.py",
)
score_s = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(score_s)

stale_at5 = score_s.stale_at5
violation_at5 = score_s.violation_at5
shift_at5 = score_s.shift_at5
drop_at5 = score_s.drop_at5
jaccard = score_s.jaccard
worst_value = score_s.worst_value
cluster_stats = score_s.cluster_stats
holm = score_s.holm


def test_stale_basic():
    F0 = {"Wheat", "Gram", "Pea", "Barley", "Sunflower"}
    F1 = {"Gram", "Pea", "Barley", "Sunflower"}          # D = {Wheat}
    assert math.isclose(stale_at5(["Wheat", "Gram"], F0, F1), 1.0)
    assert math.isclose(stale_at5(["Gram", "Pea"], F0, F1), 0.0)
    assert math.isclose(drop_at5(["Wheat", "Gram"], F0, F1), 0.0)
    assert math.isclose(drop_at5(["Gram", "Pea"], F0, F1), 1.0)


def test_stale_two_of_three():
    F0 = {"A", "B", "C", "D"}
    F1 = {"D"}                                             # D = {A,B,C}
    top5 = ["A", "B", "D", "E", "F"]                       # keeps 2 of 3
    assert math.isclose(stale_at5(top5, F0, F1), 2 / 3)
    assert math.isclose(drop_at5(top5, F0, F1), 1 / 3)


def test_violation():
    F1 = {"Gram", "Pea"}
    assert math.isclose(violation_at5(["Wheat", "Gram", "Pea", "Barley", "Sunflower"],
                                      F1), 3 / 5)
    assert math.isclose(violation_at5(["Wheat", "Gram"], F1), 0.5)
    assert violation_at5([], F1) == 0.0
    assert violation_at5(["Wheat"], {"Wheat"}) == 0.0


def test_violation_unknown_and_universe_crops():
    F1 = {"Wheat"}
    # unknown crop name counts as not-feasible
    assert math.isclose(violation_at5(["UnknownCrop", "Wheat", "Another"], F1),
                        2 / 3)
    # a crop outside the oracle universe is never in F1 -> counts as violation
    assert violation_at5(["Z"], F1) == 1.0


def test_shift():
    a = ["Wheat", "Gram", "Pea"]
    assert shift_at5(a, ["Wheat", "Gram", "Pea"]) == 0.0
    assert shift_at5(a, ["Pea", "Gram", "Wheat"]) == 0.0      # order-free
    b = ["Rice", "Gram", "Pea"]
    j = len({"Wheat", "Gram", "Pea"} & {"Rice", "Gram", "Pea"}) / 4
    assert math.isclose(shift_at5(a, b), 1.0 - j)
    assert shift_at5([], []) == 0.0
    assert math.isclose(shift_at5(["A"], []), 1.0)


def test_edge_cases_empty_D_and_short_lists():
    F0 = F1 = {"A"}
    assert stale_at5(["A"], F0, F1) == 0.0
    assert stale_at5([], F0, F1) == 0.0
    assert drop_at5(["A"], F0, F1) == 1.0        # registered identity drop = 1 - stale
    F1 = {"A", "B", "C"}
    assert math.isclose(violation_at5(["A", "B", "X"], F1), 1 / 3)   # len 3 < 5
    assert math.isclose(violation_at5(["A"] * 7, {"A"}), 0.0)        # >5 clipped


def test_metric_value_dispatch():
    F0, F1 = {"A", "B"}, {"B"}
    top5, base = ["A", "C"], ["B", "C"]
    assert math.isclose(score_s.metric_value("stale", top5, base, F0, F1), 1.0)
    assert math.isclose(score_s.metric_value("violation", top5, base, F0, F1),
                        2 / 2)
    assert math.isclose(score_s.metric_value("shift", top5, base, F0, F1),
                        1.0 - 1 / 3)
    assert math.isclose(score_s.metric_value("drop", top5, base, F0, F1), 0.0)


def test_itt_worst_values():
    assert worst_value("stale", True) == 1.0
    assert worst_value("stale", False) == 0.0     # |D|==0: nothing can be stale
    assert worst_value("drop", True) == 0.0
    assert worst_value("drop", False) == 1.0
    assert worst_value("violation", False) == 1.0
    assert worst_value("shift", False) == 1.0


def test_cluster_stats_centered_p_and_ci():
    by = {"d1": [1.0, 1.0], "d2": [0.0, 0.0], "d3": [1.0, 0.0]}
    st = cluster_stats(by)
    assert math.isclose(st["mean"], 0.5)
    assert st["n"] == 6 and st["k"] == 3
    assert 0.0 <= st["lo"] <= st["mean"] <= st["hi"] <= 1.0
    assert 0.0 < st["p"] <= 1.0
    empty = cluster_stats({})
    assert empty == {"mean": 0.0, "lo": 0.0, "hi": 0.0, "p": 1.0, "n": 0, "k": 0}
    # deterministic: same input -> same output (seed 42, cached indices)
    assert cluster_stats(by) == st


def test_cluster_stats_detects_shift():
    by = {"d1": [1.0] * 10, "d2": [1.0] * 10}
    st = cluster_stats(by)
    assert st["mean"] == 1.0
    assert st["p"] <= 0.01          # far from centred null at 0


def test_holm_monotone_and_bounded():
    adj = holm([0.01, 0.04, 0.03, 0.99])
    assert all(0.0 <= a <= 1.0 for a in adj)
    # adjusted p-values are non-decreasing in raw p order
    raw = [0.01, 0.04, 0.03, 0.99]
    pairs = sorted(zip(raw, adj))
    for (r1, a1), (r2, a2) in zip(pairs, pairs[1:]):
        assert a2 >= a1 - 1e-12
    assert adj[0] == pytest.approx(0.04)
