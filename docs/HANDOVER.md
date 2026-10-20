# Handover Document

This document provides a complete handover for every figure and table in the evaluation. Each entry contains:
- **File locations** (script, data CSV, output)
- **Rebuild command**
- **What is plotted** (plain words)
- **Exact numbers** (from source files)
- **Protocol section** & **source result file**
- **What it does NOT show**
- **Suggested paper location**

---

## Figure Index

| ID | Title | Script | Data CSV | Output | Protocol | Suggested Location |
|----|-------|--------|----------|--------|----------|-------------------|
| F1 | Precision@5 per condition | `figures/scripts/real_eval_figures.py` | `figures/data/real/fig1_data.csv` | `figures/out/fig1_agreement_levels.{pdf,png}` | 8.30 | Main Results §3.1 |
| F2 | nDCG@5 per condition | `figures/scripts/real_eval_figures.py` | `figures/data/real/fig2_data.csv` | `figures/out/fig2_contrast_forest.{pdf,png}` | 8.30 | Main Results §3.1 |
| F3 | Forest plot of contrasts | `figures/scripts/real_eval_figures.py` | `figures/data/real/fig3_data.csv` | `figures/out/fig3_reference_sensitivity.{pdf,png}` | 8.30 | Main Results §3.2 |
| F4 | Season validity & hard violation | `figures/scripts/n500_figures.py` | `figures/data/n500/Fig_N01_data.csv` | `figures/out/Fig_N01_condition_quality.{pdf,png}` | 8.11 | Main Results §3.3 |
| F5 | Reference sensitivity | `figures/scripts/real_eval_figures.py` | `figures/data/real/fig3_data.csv` | `figures/out/fig3_reference_sensitivity.{pdf,png}` | 8.30 | Main Results §3.2 |
| F6 | Per-district spread | `figures/scripts/n500_figures.py` | `figures/data/n500/Fig_N04_data.csv` | `figures/out/Fig_N04_district_variation.{pdf,png}` | 8.29b | Main Results §3.4 |
| F7 | Per-season Precision@5 | `figures/scripts/real_eval_figures.py` | `figures/data/real/fig1_data.csv` | `figures/out/fig1_agreement_levels.{pdf,png}` | 8.30 | Supplement |
| F8 | OOV share & ceiling | `figures/scripts/real_eval_figures.py` | `figures/data/real/fig1_data.csv` | `figures/out/fig1_agreement_levels.{pdf,png}` | 8.30 | Supplement |
| F9 | S-series Violation@5 | `figures/scripts/s_figures.py` | `figures/data/s/violation_by_set.csv` | `figures/out/violation_by_set.{pdf,png}` | 8.32/8.33 | S-Series §4 |
| F10 | S-series Shift@5 | `figures/scripts/s_figures.py` | `figures/data/s/shift_by_set.csv` | `figures/out/shift_by_set.{pdf,png}` | 8.32/8.33 | S-Series §4 |
| F11 | S-series Stale@5 conditional | `figures/scripts/s_figures.py` | `figures/data/s/stale_by_set.csv` | `figures/out/stale_by_set.{pdf,png}` | 8.32/8.33 | S-Series §4 |
| F12 | Exposure-conditioned retention | `figures/scripts/s_figures.py` | `figures/data/s/retention.csv` | `figures/out/retention.{pdf,png}` | 8.34 | S-Series §5 |
| F13 | Delta-violation | `figures/scripts/s_figures.py` | `figures/data/s/delta_violation.csv` | `figures/out/delta_violation.{pdf,png}` | 8.34 | S-Series §5 |
| F14 | Movement not explained | `figures/scripts/s_figures.py` | `figures/data/s/false_change.csv` | `figures/out/false_change.{pdf,png}` | 8.34 | S-Series §5 |
| F15 | Tool-output overlap | `figures/scripts/s_figures.py` | `figures/data/s/overlap.csv` | `figures/out/overlap.{pdf,png}` | 8.34 | S-Series §5 |
| F16 | Oracle signal | `figures/scripts/s_figures.py` | `figures/data/s/oracle_signal.csv` | `figures/out/oracle_signal.{pdf,png}` | 8.33 | S-Series §3 |
| F17 | S-series contrast forest | `figures/scripts/s_figures.py` | `figures/data/s/contrasts_forest.csv` | `figures/out/contrasts_forest.{pdf,png}` | 8.32/8.33 | S-Series §4 |
| F18 | Tool vs pipeline (B6) | `figures/scripts/n500_figures.py` | `figures/data/n500/Fig_N07_data.csv` | `figures/out/Fig_N07_c2a_vs_c3.{pdf,png}` | 8.34/8.35 | Methods §2.3 |
| F19 | db_v1 vs db_v2 diagnostic | `figures/scripts/n500_figures.py` | `figures/data/n500/dbv2_data.csv` | `figures/out/dbv2_diagnostic.{pdf,png}` | 8.31 | Supplement |
| F20 | Coverage & usable rates | `figures/scripts/n500_figures.py` | `figures/data/n500/coverage_data.csv` | `figures/out/coverage_rates.{pdf,png}` | 8.11 | Supplement |

---

## Per-Figure Details

### F1 — Precision@5 per condition (both models)

**Script:** `figures/scripts/real_eval_figures.py` → `fig1_agreement_levels()`
**Data:** `figures/data/real/fig1_data.csv` (from `eval/results/real_eval.json` → `models.nemotron.WITH_pilot.R_prim_pp.levels`, `models.llama.WITH_pilot.R_prim_pp.levels`)
**Rebuild:** `python -m figures.scripts.real_eval_figures`
**What is plotted:** Grouped bars of Precision@5 (R_prim, per-protocol) for each condition (C0, C0b, C1a, C2a, C2b, C3), separate panels for Nemotron (n=500) and Llama (n=150). Error bars = district-clustered 95% bootstrap CIs.
**Exact numbers (Nemotron, R_prim, PP):** C0=0.410, C0b=0.485, C1a=0.492, C2a=0.504, C2b=0.622, C3=0.5035
**Exact numbers (Llama, R_prim, PP):** C0=0.381, C0b=0.412, C1a=0.435, C2a=0.506, C2b=0.468, C3=0.525
**Protocol:** 8.30 (Real-world independent evaluation)
**Source:** `eval/results/real_eval.json` → `models.<model>.WITH_pilot.R_prim_pp.levels`
**Does NOT show:** ITT analysis, R_full/R_all/R_prod sensitivity (see F3/F5)
**Paper location:** Main Results Figure 1

---

### F2 — nDCG@5 per condition (both models)

**Script:** `figures/scripts/real_eval_figures.py` → `fig2_contrast_forest()`
**Data:** `figures/data/real/fig2_data.csv`
**Rebuild:** `python -m figures.scripts.real_eval_figures`
**What is plotted:** Forest plot of registered contrasts (C2a-C0b, C2a-C1a, C2b-C0b, C2b-C1a, C3-C2b) for nDCG@5 on R_prim. Points = paired mean difference, bars = district-clustered 95% bootstrap CI. Holm-significant contrasts marked.
**Exact numbers (Nemotron nDCG@5 contrasts, R_prim, PP):** C2a-C0b=+0.041 [+0.018,+0.064]*, C2a-C1a=+0.038 [+0.015,+0.061]*, C2b-C0b=+0.102 [+0.071,+0.133]*, C2b-C1a=+0.099 [+0.068,+0.130]*, C3-C2b=-0.120 [-0.152,-0.088]*
**Protocol:** 8.30
**Source:** `eval/results/real_eval.json` → `models.<model>.WITH_pilot.R_prim_pp.contrasts`
**Does NOT show:** Precision@5 contrasts (see F1), Recall@5, ITT
**Paper location:** Main Results Figure 2

---

### F3 — Forest plot of registered contrasts

**Script:** `figures/scripts/real_eval_figures.py` → `fig3_reference_sensitivity()`
**Data:** `figures/data/real/fig3_data.csv`
**Rebuild:** `python -m figures.scripts.real_eval_figures`
**What is plotted:** Sensitivity of Precision@5 and nDCG@5 across reference definitions (R_prim, R_full, R_all, R_prod) for each condition. Grouped bars with CIs.
**Protocol:** 8.30
**Source:** `eval/results/real_eval.json` → `models.<model>.WITH_pilot.R_*_pp.levels`
**Does NOT show:** ITT, per-season breakdown
**Paper location:** Main Results Figure 3 (sensitivity)

---

### F4 — Season validity & hard violation per condition

**Script:** `figures/scripts/n500_figures.py` → `fig_n01()`
**Data:** `figures/data/n500/Fig_N01_data.csv` (from `eval/results/n500_primary_metrics.json`)
**Rebuild:** `python -m figures.scripts.n500_figures`
**What is plotted:** Two-panel figure. Left: Season validity (strict, PP) per condition with district-clustered CIs. Right: Hard violation (strict, PP) per condition. Nemotron n=500, Llama n=150.
**Exact numbers (Nemotron, strict, PP):** C0=0.551/0.382, C0b=0.646/0.292, C1a=0.665/0.292, C2a=0.803/0.161, C2b=0.772/0.151, C3=0.863/0.104
**Protocol:** 8.11 (primary metrics), 8.23 (n=500)
**Source:** `eval/results/n500_primary_metrics.json`
**Does NOT show:** Lenient, ITT, per-season breakdown (see F7)
**Paper location:** Main Results Figure 4

---

### F5 — Reference-definition sensitivity

**Script:** `figures/scripts/real_eval_figures.py` → `fig3_reference_sensitivity()`
**Data:** `figures/data/real/fig3_data.csv`
**Rebuild:** `python -m figures.scripts.real_eval_figures`
**What is plotted:** Precision@5 and nDCG@5 for R_prim, R_full, R_all, R_prod side by side. Shows robustness of conclusions to reference window and vocabulary restriction.
**Protocol:** 8.30
**Source:** `eval/results/real_eval.json` → `models.<model>.WITH_pilot.R_*_pp.levels`
**Does NOT show:** ITT, individual contrasts
**Paper location:** Main Results Figure 5 (sensitivity)

---

### F6 — Per-district spread of registered effect

**Script:** `figures/scripts/n500_figures.py` → `fig_n04()`
**Data:** `figures/data/n500/Fig_N04_data.csv` (from `eval/results/n500_clustered_inference.json`)
**Rebuild:** `python -m figures.scripts.n500_figures`
**What is plotted:** District-level C2b-C0b season validity effect (51 districts). Mean +0.123, SD 0.134, range [-0.171, +0.400]. Shows the B1/B2 heterogeneity is district-region segmentation.
**Protocol:** 8.29b
**Source:** `eval/results/n500_clustered_inference.json` → `district_effects.C2b-C0b`
**Does NOT show:** Other contrasts, per-season district effects
**Paper location:** Main Results Figure 6 (district variation)

---

### F7 — Per-season Precision@5

**Script:** `figures/scripts/real_eval_figures.py` → `fig1_agreement_levels()` with season filter
**Data:** `figures/data/real/fig1_data.csv` (from `eval/results/real_eval.json` → `per_season_R_prim`)
**Rebuild:** `python -m figures.scripts.real_eval_figures`
**What is plotted:** Precision@5 by season (Kharif/Rabi/Zaid) for each condition. Nemotron n=500, Llama n=150.
**Exact numbers (Nemotron, R_prim, PP):** Kharif: C2b=0.712, C2a=0.587, C3=0.542; Rabi: C2a=0.456, C2b=0.431; Zaid: C2a=0.421, C2b=0.523
**Protocol:** 8.30
**Source:** `eval/results/real_eval.json` → `models.<model>.WITH_pilot.per_season_R_prim`
**Does NOT show:** nDCG@5 per season, ITT
**Paper location:** Supplement

---

### F8 — Out-of-vocabulary share and achievable ceiling

**Script:** `figures/scripts/real_eval_figures.py` (from `real_eval.json` → `out_of_vocab_share_top5_R_all`)
**Data:** `figures/data/real/fig1_data.csv`
**Rebuild:** `python -m figures.scripts.real_eval_figures`
**What is plotted:** Two panels: (left) OOV share of R_all top-5 = 8.5% (mean over cells); (right) achievable ceiling = max Precision@5 if all OOV crops were in vocab.
**Protocol:** 8.30
**Source:** `eval/results/real_eval.json` → `out_of_vocab_share_top5_R_all`, `vocab_crops_with_no_series`
**Does NOT show:** Per-cell breakdown
**Paper location:** Supplement (limitations)

---

### F9 — S-series Violation@5 per condition

**Script:** `figures/scripts/s_figures.py` → `violation_by_set()`
**Data:** `figures/data/s/violation_by_set.csv` (from `eval/results/s_scores.json`)
**Rebuild:** `python -m figures.scripts.s_figures`
**What is plotted:** Violation@5 (as-scored, 0-filled) for each condition × perturbation set, both models, pp and ITT. Higher = worse.
**Protocol:** 8.32/8.33 (S-series), 8.34 (follow-up)
**Source:** `eval/results/s_scores.json` → `results.<model>.<set>.<cond>.violation`
**Does NOT show:** Conditional |D|>0 version (see F11), Stale@5
**Paper location:** S-Series Figure 1

---

### F10 — S-series Shift@5 per condition

**Script:** `figures/scripts/s_figures.py` → `shift_by_set()`
**Data:** `figures/data/s/shift_by_set.csv`
**Rebuild:** `python -m figures.scripts.s_figures`
**What is plotted:** Shift@5 = 1 - Jaccard(base, shifted) per condition per perturbation set. Shows which conditions change recommendations under perturbation.
**Protocol:** 8.32/8.33
**Source:** `eval/results/s_scores.json` → `results.<model>.<set>.<cond>.shift`
**Does NOT show:** Stale@5, Violation@5
**Paper location:** S-Series Figure 2

---

### F11 — S-series Stale@5 conditional (|D|>0)

**Script:** `figures/scripts/s_figures.py` → `stale_by_set()`
**Data:** `figures/data/s/stale_by_set.csv` (from `eval/results/s_scores_conditional.json`)
**Rebuild:** `python -m figures.scripts.s_figures`
**What is plotted:** Stale@5 conditional on |D|>0 (exposed cells only), with n_exposed shown. Primary S-series metric per PROTOCOL 8.34 follow-up.
**Protocol:** 8.32/8.33/8.34
**Source:** `eval/results/s_scores_conditional.json` → `results.<model>.<set>.<cond>.stale`
**Does NOT show:** As-scored 0-filled version (sensitivity)
**Paper location:** S-Series Figure 3 (primary)

---

### F12 — Exposure-conditioned retention

**Script:** `figures/scripts/s_figures.py` → `retention()`
**Data:** `figures/data/s/retention.csv` (from `eval/results/s_followup.json` → `retention`)
**Rebuild:** `python -m figures.scripts.s_figures`
**What is plotted:** Retention = \|base_top5 ∩ D ∩ shifted_top5\| / \|base_top5 ∩ D\| over exposed cells, with district-clustered CIs. Per condition × model, strict/lenient, pp/ITT.
**Protocol:** 8.34 (exploratory follow-up)
**Source:** `eval/results/s_followup.json` → `retention`
**Does NOT show:** C0/C0b (reused by design), delta-violation
**Paper location:** S-Series Figure 4 (exploratory)

---

### F13 — Delta-violation

**Script:** `figures/scripts/s_figures.py` → `delta_violation()`
**Data:** `figures/data/s/delta_violation.csv` (from `eval/results/s_followup.json` → `delta_violation`)
**Rebuild:** `python -m figures.scripts.s_figures`
**What is plotted:** Violation@5(shift) - Violation@5(baseline) per cell, pooled over signal cells (|D|>0) and all cells. Per condition, strict/lenient, pp/ITT.
**Protocol:** 8.34
**Source:** `eval/results/s_followup.json` → `delta_violation`
**Does NOT show:** Stale@5, retention
**Paper location:** S-Series Figure 5 (exploratory)

---

### F14 — Movement not explained by hard constraints

**Script:** `figures/scripts/s_figures.py` → `false_change()`
**Data:** `figures/data/s/false_change.csv` (from `eval/results/s_scores.json` → `false_change`)
**Rebuild:** `python -m figures.scripts.s_figures`
**What is plotted:** P(Shift@5 > 0 \| |D|=0) per perturbation set and condition. "Higher = worse" — movement where oracle says no hard constraint changed.
**Protocol:** 8.34 (renamed from "false-change")
**Source:** `eval/results/s_scores.json` → `results.<model>.<set>.<cond>.false_change`
**Does NOT show:** Conditional |D|>0, delta-violation
**Paper location:** S-Series Figure 6

---

### F15 — Tool-output overlap (crop_score echo)

**Script:** `figures/scripts/s_figures.py` → `overlap()`
**Data:** `figures/data/s/overlap.csv` (from `eval/results/s_scores.json` → `overlap`)
**Rebuild:** `python -m figures.scripts.s_figures`
**What is plotted:** Fraction of C2a top-5 that matches stored `crop_score` tool output. Measures how much C2a echoes the tool vs independent reasoning.
**Protocol:** 8.34 (exploratory)
**Source:** `eval/results/s_scores.json` → `results.<model>.<set>.C2a.overlap`
**Does NOT show:** C3 overlap, other conditions
**Paper location:** Supplement / Methods

---

### F16 — Oracle signal per perturbation set

**Script:** `figures/scripts/s_figures.py` → `oracle_signal()`
**Data:** `figures/data/s/oracle_signal.csv` (from `eval/results/s_oracle_signal.json`)
**Rebuild:** `python -m figures.scripts.s_figures`
**What is plotted:** Number of cells with |D|>0 per perturbation set, strict vs lenient oracle. Shows which arms have signal.
**Protocol:** 8.33 (pre-run audit)
**Source:** `eval/results/s_oracle_signal.json`
**Does NOT show:** Model results, Stale@5 values
**Paper location:** S-Series Figure 2 (design validation)

---

### F17 — S-series contrast forest

**Script:** `figures/scripts/s_figures.py` → `contrasts_forest()`
**Data:** `figures/data/s/contrasts_forest.csv` (from `eval/results/s_scores.json` + `s_scores_conditional.json`)
**Rebuild:** `python -m figures.scripts.s_figures`
**What is plotted:** Forest plot of 4 registered contrasts (C2a-C0b, C2b-C0b, C2a-C1a, C3-C2b) on Stale@5, pp and ITT, strict/lenient. Holm p-values annotated.
**Protocol:** 8.32/8.33/8.34
**Source:** `eval/results/s_scores.json`, `eval/results/s_scores_conditional.json`
**Does NOT show:** Shift@5, Violation@5 contrasts
**Paper location:** S-Series Figure 7

---

### F18 — Tool vs pipeline top-5 agreement (B6 cause)

**Script:** `figures/scripts/n500_figures.py` → `fig_n07()`
**Data:** `figures/data/n500/Fig_N07_data.csv` (from `eval/results/n500_clustered_inference.json` + `c3t_correction_analysis.json`)
**Rebuild:** `python -m figures.scripts.n500_figures`
**What is plotted:** C2a vs C3 (registered) match/beat/lose + C2a vs C3t (corrected) match/beat/lose + stored bundle `crop_score` agreement. Shows B6 instrument correction effect.
**Exact numbers (Nemotron, strict PP sv):** C2a vs C3: match=361 (72.2%), beat=13 (2.6%), lose=126 (25.2%); C2a vs C3t: [TBD]; C2a vs stored tool: 100% match on base 40.
**Protocol:** 8.34/8.35
**Source:** `eval/results/n500_clustered_inference.json`, `eval/results/c3t_correction_analysis.json`
**Does NOT show:** Llama (n=150 only), lenient/ITT
**Paper location:** Methods Figure 2 (instrument validation)

---

### F19 — db_v1 vs db_v2 (Linseed) diagnostic

**Script:** `figures/scripts/n500_figures.py` (new function `fig_dbv2()`)
**Data:** `figures/data/n500/dbv2_data.csv` (from `eval/results/db_v2_test.json`)
**Rebuild:** `python -m figures.scripts.n500_figures`
**What is plotted:** P@5 and nDCG@5 for C3 db_v1 vs C3 db_v2 on test window (2020-21..2022-23). Shows Linseed false positives in Rabi (69 recommended vs 46 reference cells).
**Exact numbers:** C3 db_v1 P@5=0.4396, C3 db_v2 P@5=0.4304, delta=-0.0092* [Holm 9.4e-3]
**Protocol:** 8.31
**Source:** `eval/results/db_v2_test.json`
**Does NOT show:** LLM conditions (not re-run), in-sample results
**Paper location:** Supplement

---

### F20 — Coverage and usable-run rates

**Script:** `figures/scripts/n500_figures.py` (new function `fig_coverage()`)
**Data:** `figures/data/n500/coverage_data.csv` (from `eval/results/n500_primary_metrics.json`)
**Rebuild:** `python -m figures.scripts.n500_figures`
**What is plotted:** Per-condition usable scenario counts (PP) vs planned (ITT) for Nemotron (n=500) and Llama (n=150). Shows truncation (C1a 30/500) and invalid JSON rates.
**Exact numbers (Nemotron, PP usable):** C0=451, C0b=442, C1a=470, C2a=500, C2b=494, C3=500
**Protocol:** 8.11/8.23
**Source:** `eval/results/n500_primary_metrics.json` → `coverage`
**Does NOT show:** Per-scenario error breakdown
**Paper location:** Supplement (reliability)

---

## Table Index

| ID | Title | Source File | Protocol | Suggested Location |
|----|-------|-------------|----------|-------------------|
| T1 | Primary metrics (n=500) | `eval/results/n500_primary_metrics.json` | 8.11/8.23 | Main Results Table 1 |
| T2 | Registered contrasts | `eval/results/n500_primary_metrics.json` | 8.11/8.23 | Main Results Table 2 |
| T3 | Real-data P@5/nDCG@5 | `eval/results/real_eval.json` | 8.30 | Main Results Table 3 |
| T4 | S-series Stale@5/Violation@5 | `eval/results/s_scores.json` | 8.32/8.33 | S-Series Table 1 |
| T5 | S-series contrasts | `eval/results/s_scores.json` + `s_scores_conditional.json` | 8.32/8.33/8.34 | S-Series Table 2 |
| T6 | Instrument correction summary | `eval/results/c3t_correction_summary.json` | 8.35 | Methods Table 1 |
| T7 | db_v2 test window | `eval/results/db_v2_test.json` | 8.31 | Supplement Table 1 |
| T8 | Season validity v1.2 vs v1.1 | `eval/results/c3_season_validity_v1.2_vs_v1.1.json` | 8.5 | Methods Table 2 |
| T9 | Heterogeneity by season | `eval/results/n500_heterogeneity_season.json` | 8.26 | Supplement Table 2 |

---

## Rebuild All Figures

```bash
# From repository root
make figures
# Or individually:
python -m figures.scripts.generate_figures
python -m figures.scripts.n500_figures
python -m figures.scripts.real_eval_figures
python -m figures.scripts.s_figures
python -m figures.scripts.analyze_cross_model
```

All figures are **offline** — they read only from `eval/results/*.json` and write to `figures/out/` + `figures/data/`. No API calls.

---

## Key Numbers Ledger

| Number | Value | Source File | Version |
|--------|-------|-------------|---------|
| C3 season validity (strict, 10k) | 0.83590 | `c3_season_validity_v1.2_vs_v1.1.json` | v1.2 |
| C3 hard violation (strict, 10k) | 0.11464 | `c3_season_validity_v1.2_vs_v1.1.json` | v1.2 |
| C3t season validity (strict, 10k) | 0.7900 | `c3t_correction_analysis.json` | C3t |
| C3t hard violation (strict, 10k) | 0.1615 | `c3t_correction_analysis.json` | C3t |
| Nemotron C2b P@5 (R_prim) | 0.622 | `real_eval.json` | nemotron |
| Llama C2a P@5 (R_prim) | 0.506 | `real_eval.json` | llama |
| C2a-C0b sv contrast (nemotron) | +0.161* | `n500_primary_metrics.json` | n=500 |
| C2b-C0b sv contrast (nemotron) | +0.128* | `n500_primary_metrics.json` | n=500 |
| db_v2 P@5 delta | -0.0092* | `db_v2_test.json` | db_v2 |
| S-series llama C2a-C0b Stale@5 | +0.032* | `s_scores.json` | llama |

*Holm-significant at α=0.05

---

## Open Decisions

1. **C3t S-series integration** — Full Stale@5/Violation@5 conditional tables need S_FOLLOWUP oracle integration
2. **C2a vs C3t match/beat/lose** — Recompute with C3t instrument
3. **db_v2 LLM re-run cost** — ~10,630 requests estimated, not executed
4. **GLM-5.3 inclusion** — Dropped from primary analysis (endpoint degraded)
5. **Consistency repeats** — Still running (launched 2026-10-15)
5. **Figure F19/F20** — Need new figure functions in n500_figures.py