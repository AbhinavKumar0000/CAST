"""Statistical analysis (STEP 7).

Bootstrap CIs, paired tests (Wilcoxon, McNemar), Holm-Bonferroni correction,
effect sizes (Cliff's delta, Cohen's d), stratified results.
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
import json

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# --- Bootstrap confidence intervals ---

def bootstrap_ci(data: list[float], n_resamples: int = 10000, ci: float = 0.95, 
                 statistic: callable = np.mean, seed: int = 42) -> tuple[float, float, float]:
    """Bootstrap confidence interval for a statistic.
    
    Returns: (point_estimate, ci_lower, ci_upper)
    """
    rng = np.random.default_rng(seed)
    data_arr = np.array(data)
    point = statistic(data_arr)
    
    if len(data_arr) < 2:
        return point, point, point
    
    boot_stats = []
    for _ in range(n_resamples):
        sample = rng.choice(data_arr, size=len(data_arr), replace=True)
        boot_stats.append(statistic(sample))
    
    alpha = (1 - ci) / 2
    lower = np.percentile(boot_stats, 100 * alpha)
    upper = np.percentile(boot_stats, 100 * (1 - alpha))
    
    return float(point), float(lower), float(upper)

def bootstrap_ci_ratio(num: list[float], den: list[float], n_resamples: int = 10000, 
                       ci: float = 0.95, seed: int = 42) -> tuple[float, float, float]:
    """Bootstrap CI for ratio of means (e.g., rate)."""
    rng = np.random.default_rng(seed)
    num_arr = np.array(num)
    den_arr = np.array(den)
    
    if len(num_arr) == 0 or den_arr.sum() == 0:
        return 0.0, 0.0, 0.0
    
    point = num_arr.sum() / den_arr.sum()
    
    boot_ratios = []
    for _ in range(n_resamples):
        idx = rng.choice(len(num_arr), size=len(num_arr), replace=True)
        n_sum = num_arr[idx].sum()
        d_sum = den_arr[idx].sum()
        boot_ratios.append(n_sum / d_sum if d_sum > 0 else 0.0)
    
    alpha = (1 - ci) / 2
    lower = np.percentile(boot_ratios, 100 * alpha)
    upper = np.percentile(boot_ratios, 100 * (1 - alpha))
    
    return float(point), float(lower), float(upper)

# --- Paired tests ---

def wilcoxon_paired(x: list[float], y: list[float]) -> tuple[float, float]:
    """Wilcoxon signed-rank test for paired continuous data.
    
    Returns: (statistic, p-value)
    """
    x_arr = np.array(x)
    y_arr = np.array(y)
    diff = x_arr - y_arr
    # Remove zero differences
    diff = diff[diff != 0]
    if len(diff) < 2:
        return 0.0, 1.0
    stat, p = stats.wilcoxon(diff, alternative='two-sided', zero_method='zsplit')
    return float(stat), float(p)

def mcnemar_paired(x: list[int], y: list[int]) -> tuple[float, float]:
    """McNemar test for paired binary data.
    
    Args:
        x, y: Binary outcomes (0/1) for each scenario
    Returns: (statistic, p-value)
    """
    x_arr = np.array(x)
    y_arr = np.array(y)
    
    # Contingency table: (x=0,y=0), (x=0,y=1), (x=1,y=0), (x=1,y=1)
    n00 = np.sum((x_arr == 0) & (y_arr == 0))
    n01 = np.sum((x_arr == 0) & (y_arr == 1))
    n10 = np.sum((x_arr == 1) & (y_arr == 0))
    n11 = np.sum((x_arr == 1) & (y_arr == 1))
    
    # McNemar uses discordant pairs n01 and n10
    # With continuity correction: (|n01 - n10| - 1)^2 / (n01 + n10)
    n_discordant = n01 + n10
    if n_discordant == 0:
        return 0.0, 1.0
    
    stat = (abs(n01 - n10) - 1) ** 2 / n_discordant
    p = 1 - stats.chi2.cdf(stat, df=1)
    
    return float(stat), float(p)

# --- Multiple comparison correction ---

def holm_bonferroni(p_values: list[float]) -> list[float]:
    """Holm-Bonferroni correction for multiple comparisons.
    
    Returns adjusted p-values in the same order as input.
    """
    m = len(p_values)
    if m == 0:
        return []
    
    # Pair with original indices
    indexed = list(enumerate(p_values))
    indexed.sort(key=lambda x: x[1])  # Sort by p-value
    
    adjusted = [0.0] * m
    for i, (orig_idx, p) in enumerate(indexed):
        adj_p = p * (m - i)
        if i > 0:
            adj_p = max(adj_p, adjusted[indexed[i-1][0]])
        adjusted[orig_idx] = min(adj_p, 1.0)
    
    return adjusted

# --- Effect sizes ---

def cliffs_delta(x: list[float], y: list[float]) -> float:
    """Cliff's delta (non-parametric effect size).
    
    Range: -1 to 1. 
    |delta| < 0.147: negligible, < 0.33: small, < 0.474: medium, >= 0.474: large
    """
    x_arr = np.array(x)
    y_arr = np.array(y)
    
    n_x, n_y = len(x_arr), len(y_arr)
    if n_x == 0 or n_y == 0:
        return 0.0
    
    # Count pairwise comparisons
    greater = np.sum(x_arr[:, None] > y_arr[None, :])
    less = np.sum(x_arr[:, None] < y_arr[None, :])
    
    delta = (greater - less) / (n_x * n_y)
    return float(delta)

def cohens_d(x: list[float], y: list[float]) -> float:
    """Cohen's d for paired samples.
    
    d = mean_diff / std_diff
    """
    x_arr = np.array(x)
    y_arr = np.array(y)
    diff = x_arr - y_arr
    
    if len(diff) < 2:
        return 0.0
    
    mean_diff = np.mean(diff)
    std_diff = np.std(diff, ddof=1)
    
    if std_diff == 0:
        return 0.0
    
    return float(mean_diff / std_diff)

# --- Stratified analysis ---

def stratified_bootstrap(data_by_stratum: dict[str, list[float]], 
                         n_resamples: int = 10000, ci: float = 0.95,
                         seed: int = 42) -> dict[str, tuple[float, float, float]]:
    """Compute bootstrap CI per stratum."""
    results = {}
    for stratum, values in data_by_stratum.items():
        results[stratum] = bootstrap_ci(values, n_resamples, ci, seed=seed)
    return results

def aggregate_stratified(stratified_results: dict[str, tuple[float, float, float]],
                         weights: dict[str, float] | None = None) -> tuple[float, float, float]:
    """Aggregate stratified results with optional weighting."""
    if not stratified_results:
        return 0.0, 0.0, 0.0
    
    if weights is None:
        weights = {k: 1.0 for k in stratified_results}
    
    total_weight = sum(weights.values())
    weighted_point = sum(stratified_results[k][0] * weights.get(k, 1.0) for k in stratified_results) / total_weight
    
    # For CI, we'd need to bootstrap the combined data
    # Simplified: use widest CI
    all_lowers = [v[1] for v in stratified_results.values()]
    all_uppers = [v[2] for v in stratified_results.values()]
    
    return weighted_point, min(all_lowers), max(all_uppers)

# --- Per-scenario paired comparison ---

def compare_conditions(scenario_results: dict[str, dict[str, Any]],
                       condition_a: str, condition_b: str,
                       metric_fn: callable,
                       ground_truth: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Compare two conditions on per-scenario metric values."""
    
    vals_a = []
    vals_b = []
    paired = []
    
    for sid, res in scenario_results.items():
        pred_a = res.get(condition_a, {}).get("top5", [])
        pred_b = res.get(condition_b, {}).get("top5", [])
        
        if ground_truth and sid in ground_truth:
            truth = ground_truth[sid]
        else:
            truth = []
        
        m_a = metric_fn(pred_a, truth) if truth else metric_fn(pred_a, [])
        m_b = metric_fn(pred_b, truth) if truth else metric_fn(pred_b, [])
        
        vals_a.append(m_a)
        vals_b.append(m_b)
        paired.append((m_a, m_b))
    
    # Continuous metric -> Wilcoxon
    stat, p = wilcoxon_paired(vals_a, vals_b)
    delta = cliffs_delta(vals_a, vals_b)
    d = cohens_d(vals_a, vals_b)
    
    return {
        "condition_a": condition_a,
        "condition_b": condition_b,
        "n": len(paired),
        "mean_a": np.mean(vals_a),
        "mean_b": np.mean(vals_b),
        "wilcoxon_stat": stat,
        "wilcoxon_p": p,
        "cliffs_delta": delta,
        "cohens_d": d,
        "paired_values": paired,
    }

# --- Results formatting ---

def format_ci(mean: float, lower: float, upper: float, decimals: int = 3) -> str:
    """Format as mean [lower, upper]."""
    return f"{mean:.{decimals}f} [{lower:.{decimals}f}, {upper:.{decimals}f}]"

def format_pvalue(p: float) -> str:
    """Format p-value."""
    if p < 0.001:
        return "<0.001"
    return f"{p:.4f}"

def format_effect_size(delta: float, d: float) -> str:
    """Format effect sizes."""
    cliffs_interp = "negligible"
    if abs(delta) >= 0.474: cliffs_interp = "large"
    elif abs(delta) >= 0.33: cliffs_interp = "medium"
    elif abs(delta) >= 0.147: cliffs_interp = "small"
    
    cohens_interp = "negligible"
    if abs(d) >= 0.8: cohens_interp = "large"
    elif abs(d) >= 0.5: cohens_interp = "medium"
    elif abs(d) >= 0.2: cohens_interp = "small"
    
    return f"Cliff's δ={delta:.3f} ({cliffs_interp}), Cohen's d={d:.3f} ({cohens_interp})"


if __name__ == "__main__":
    # Quick unit tests
    print("Running statistics unit tests...")
    
    # Test bootstrap CI
    data = [1.0, 2.0, 3.0, 4.0, 5.0] * 10
    mean, lo, hi = bootstrap_ci(data, n_resamples=1000, seed=42)
    assert 2.5 <= mean <= 3.5
    assert lo < mean < hi
    print("  bootstrap_ci: PASS")
    
    # Test Wilcoxon
    x = list(range(1, 21))
    y = [i + 1 for i in x]
    stat, p = wilcoxon_paired(x, y)
    assert p < 0.05  # Should be significant with n=20
    print("  wilcoxon_paired: PASS")
    
    # Test McNemar
    x = [1, 0, 1, 0, 1]
    y = [0, 1, 0, 1, 0]
    stat, p = mcnemar_paired(x, y)
    print(f"  mcnemar_paired: stat={stat:.3f}, p={p:.4f}")
    
    # Test Holm-Bonferroni
    pvals = [0.01, 0.02, 0.03, 0.04, 0.05]
    adj = holm_bonferroni(pvals)
    assert all(a >= p for a, p in zip(adj, pvals))
    print("  holm_bonferroni: PASS")
    
    # Test Cliff's delta
    x = [1, 2, 3, 4, 5] * 10
    y = [10, 11, 12, 13, 14] * 10
    delta = cliffs_delta(x, y)
    assert delta < -0.9  # Large negative effect
    print(f"  cliffs_delta: {delta:.3f} PASS")
    
    # Test Cohen's d
    x = [1, 2, 3, 4, 5] * 10
    y = [2, 4, 6, 8, 10] * 10  # Different variance
    d = cohens_d(x, y)
    assert d < -1.0  # Large negative effect
    print(f"  cohens_d: {d:.3f} PASS")
    
    print("All statistics unit tests PASSED!")