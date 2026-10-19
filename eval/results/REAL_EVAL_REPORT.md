# Real-world independent evaluation - results (STEP 5-6)

Pre-registered analysis plan: `eval/PROTOCOL.md` §8.30 (frozen 2026-10-16 05:40 UTC,
before any scoring). This report is generated from frozen inputs only; no model was
called. The measured quantity is **agreement with actual district cropping patterns**,
not accuracy of the system.

Artifacts: `eval/results/real_eval.json`, `eval/results/real_eval_summary.txt`,
figures in `eval/figures/real/`.

## 1. Reference

Source: DES/MoA&FW via India Data Portal (UPAG), `eval/real_data/clean/area_by_district_season_year.csv`
(10,304 rows; 51 districts x 3 seasons x 10 years). See `SOURCES.md`, `QA.md`,
`CIRCULARITY.md`. Headline reference **R_prim** = window 2015-16 .. 2022-23, ranked by
mean area, restricted to the 21-crop registry; top-5.

| reference | cells | mean top-5 len | min | max |
|---|---|---|---|---|
| R_prim (headline) | 153 | 4.51 | 2 | 5 |
| R_full (10y window) | 153 | 4.68 | 2 | 5 |
| R_all (all crops) | 153 | 4.52 | 2 | 5 |
| R_prod (production-ranked) | 153 | 4.51 | 2 | 5 |

Out-of-vocab share of R_all top-5 (mean over cells) = **0.085**. Registry crops with no
real series: **Kodo-Kutki, Watermelon** (`§8.30.3b`). Vocab restriction disclosure per
`CIRCULARITY.md` F3.

## 2. Agreement levels (R_prim, per-protocol, WITH pilot)

Precision@5 and nDCG@5, mean [95% CI] by district-clustered bootstrap (51 districts,
10,000 resamples).

**nemotron-3-ultra (n=500)**

| cond | Precision@5 | nDCG@5 |
|---|---|---|
| C0  | 0.410 [0.378, 0.443] | 0.429 [0.395, 0.463] |
| C0b | 0.493 [0.465, 0.521] | 0.514 [0.484, 0.544] |
| C1a | 0.498 [0.475, 0.520] | 0.495 [0.469, 0.520] |
| C2a | 0.484 [0.457, 0.511] | 0.480 [0.455, 0.506] |
| C2b | **0.622 [0.592, 0.651]** | **0.659 [0.631, 0.685]** |
| C3  | 0.503 [0.478, 0.529] | 0.512 [0.485, 0.539] |

**llama-3.2-11b (n=150)**

| cond | Precision@5 | nDCG@5 |
|---|---|---|
| C0  | 0.273 [0.232, 0.314] | 0.287 [0.244, 0.329] |
| C0b | 0.311 [0.267, 0.351] | 0.316 [0.274, 0.355] |
| C1a | 0.315 [0.268, 0.354] | 0.365 [0.321, 0.403] |
| C2a | **0.506 [0.463, 0.553]** | **0.500 [0.457, 0.546]** |
| C2b | 0.328 [0.287, 0.373] | 0.369 [0.332, 0.409] |
| C3  | 0.525 [0.488, 0.564] | 0.531 [0.494, 0.569] |

## 3. Pre-registered contrasts (R_prim, per-protocol, WITH pilot)

Family = {C2a-C0b, C2a-C1a, C2b-C0b, C2b-C1a, C3-C2b}; centered district-cluster
bootstrap p-values, Holm-Bonferroni within the 5-contrast family.

**nemotron-3-ultra**

| contrast | Δ Precision@5 [95% CI] | Holm | Cliff d | n |
|---|---|---|---|---|
| C2a-C0b | -0.012 [-0.047, +0.025] | 0.74 | -0.029 | 443 |
| C2a-C1a | -0.013 [-0.042, +0.018] | 0.74 | -0.089 | 470 |
| C2b-C0b | **+0.123 [+0.094, +0.151]** | **5e-4** | +0.217 | 437 |
| C2b-C1a | **+0.123 [+0.093, +0.154]** | **5e-4** | +0.225 | 465 |
| C3-C2b | **-0.120 [-0.153, -0.084]** | **5e-4** | -0.321 | 494 |

nDCG@5 shows the same direction, stronger for C2b (C2b-C1a +0.162 Holm 5e-4; C3-C2b
-0.147 Holm 5e-4). C2a/C1a/C0b are statistically indistinguishable on this metric.

**llama-3.2-11b**

| contrast | Δ Precision@5 [95% CI] | Holm | Cliff d | n |
|---|---|---|---|---|
| C2a-C0b | **+0.188 [+0.119, +0.262]** | **5e-4** | +0.530 | 127 |
| C2a-C1a | **+0.185 [+0.127, +0.253]** | **5e-4** | +0.549 | 127 |
| C2b-C0b | -0.011 [-0.067, +0.054] | 1.00 | -0.008 | 85 |
| C2b-C1a | +0.002 [-0.052, +0.065] | 1.00 | +0.044 | 85 |
| C3-C2b | **+0.181 [+0.113, +0.251]** | **5e-4** | +0.541 | 85 |

## 4. Robustness

- **WITHOUT the 40 pilot_union scenarios.** Nemotron precision levels: C0 .409, C0b .489,
  C1a .498, C2a .481, C2b .624, C3 .503 - unchanged. Llama: C0 .266, C0b .310, C1a .313,
  C2a .503, C2b .323, C3 .525 - unchanged. The pilot scenarios do not drive any result.
- **Reference sensitivity (Precision@5, WITH pilot).**

| ref | nemotron C2b | nemotron C2a | llama C2a | llama C2b |
|---|---|---|---|---|
| R_prim | 0.622 | 0.484 | 0.506 | 0.328 |
| R_full (10y) | 0.619 | 0.500 | 0.494 | 0.329 |
| R_prod | 0.617 | 0.496 | 0.498 | 0.338 |
| R_all (all crops) | 0.550 | 0.437 | 0.353 | 0.317 |

  R_all lowers every condition (the vocab restriction removes part of the reference),
  but the model/condition ordering is stable. See `fig3_reference_sensitivity`.
- **Per-season (R_prim, Precision@5).** Nemotron C2b is best in all three seasons
  (Kharif .504, Rabi .705, Zaid .523). Llama C2a leads in Rabi (.577) and Zaid (.481);
  in Kharif llama C1a/C2b are similar (.48/.45). For both models, agreement is highest
  in Rabi and lowest in Kharif/Zaid - see `real_eval.json` `per_season_R_prim`.

## 5. The UNVERIFIED rows (descriptive; `§8.30.6`)

Real MP DES series, compared over the full available window 2015-16 .. 2024-25 (and the
headline 8-year window 2015-16 .. 2022-23):

| claim | years with nonzero area | total area | headline-window (8y) mean | verdict |
|---|---|---|---|---|
| Rice / Rabi | 1 (2024-25) | 53,000 ha | 0.0 | ambiguous (recent only) |
| Maize / Rabi | 1 (2024-25) | 222,000 ha | 0.0 | ambiguous (recent only) |
| Jowar / Rabi | 0 | 0 ha | 0.0 | **contradicted** |
| Barley / Rabi | 6 (2019-20 .. 2024-25) | 138,307 ha | 738.8 | supported |
| Arhar (Tur) / Rabi | 0 | 0 ha | 0.0 | **contradicted** |

Only Jowar/Rabi and Arhar/Rabi are contradicted (zero in every year). Rice/Rabi and
Maize/Rabi appear only in the latest year (2024-25) and cannot be confirmed or refuted
by the primary window. See `§11` for the resulting v1.2 table and the recomputed
season-validity; the constraint rows (drought/flood) cannot be adjudicated from area
data. No v1.1 ground-truth file was edited.

## 6. Figures

- `fig1_agreement_levels.{pdf,png}` - Precision@5 and nDCG@5 per condition, both models.
- `fig2_contrast_forest.{pdf,png}` - pre-registered contrasts; filled = Holm-significant.
- `fig3_reference_sensitivity.{pdf,png}` - Precision@5 across reference definitions.
- Data CSVs under `eval/figures/real/data/`.

## 7. Summary

- Against actual MP district cropping, **the tool-use condition without the deterministic
  scorer (C2b) is the strongest configuration for nemotron** (Precision@5 0.622), clearly
  above both LLM-only baselines and above the deterministic scorer alone (C3 0.503).
  For nemotron the deterministic scorer, whether alone (C3) or inside the tool set (C2a),
  does not improve real-world agreement.
- For **llama, the condition with the scorer (C2a) is the strongest** (0.506); C2b gives
  no gain over the LLM-only baselines. The two models therefore disagree on which
  configuration transfers, which is reported as-is rather than pooled.
- The pilot scenarios and the reference-definition choice do not change these orderings.

## 8. Limitations (declared)

- Systems under test may have seen DES-derived figures during pretraining (contamination,
  `CIRCULARITY.md` F5); this cannot be removed and is disclosed.
- The registry restricts R_prim/R_prod to 21 crops (out-of-vocab share 8.5% in R_all);
  two registry crops (Kodo-Kutki, Watermelon) have no real series.
- The DES UPAG series contains a known discontinuity (MP Wheat Rabi ~9.8M ha 2022-23 to
  ~7.5M ha 2023-24); no adjustment is applied (recorded in `QA.md`).
- Reported scorer limitation: the rainfall channel is inert for Rabi (`PROTOCOL.md` §8.14).
- Llama C2b has lower usable coverage (n=85 of 150) than the other llama conditions; its
  contrasts are correspondingly less precise.
- Cluster bootstrap yields a p-value floor of 1e-4 (10,000 resamples); "5e-4" after Holm
  is the minimum achievable value.

## 9. Disclosure: bug log (STEP 5 scoring code)

Both bugs were in the new analysis code (`eval/scripts/real_eval.py`), not in any frozen
input. Both were found and fixed during STEP 5 on 2026-10-16, before this report was
written and before any external review.

| # | found | fixed | what was wrong | effect on results |
|---|---|---|---|---|
| A | STEP 5 first run, 2026-10-16 ~05:48 UTC | same pass | `R_all` out-of-vocab share tested raw DES `source_crop` names ("Tur", "Sesamum", ...) against the 21-crop registry instead of the STEP-2 crop->vocab mapping, so mapped crops were mis-flagged | descriptive statistic only: R_all out-of-vocab share 0.225 -> 0.085. No reference, level or contrast changed |
| B | STEP 5 verification pass, 2026-10-16 ~05:49 UTC | same pass | each model was scored over the global 500-scenario list, so llama's C3 (deterministic, available for all 500) was evaluated on 500 scenarios instead of llama's own 150, giving a level identical to nemotron's C3 | one reported level: llama C3 0.503 (n=500) -> 0.525 (n=150). Paired contrasts (e.g. C3-C2b) were already restricted to scenarios where both conditions were usable, so unchanged |

**Conclusion impact: none.** Neither bug altered any pre-registered contrast, any
significance call, or the qualitative results in `§2`-`§4` and `§7`. The only changes
were one descriptive statistic (Bug A) and one condition level (Bug B). The headline
figures were regenerated from the corrected `real_eval.json`.

## 10. Nemotron final answer vs the scorer tool's ranking (report only)

The `crop_score` tool's returned payload is not stored in the run logs (only an
`output_hash`), so the deterministic scorer ranking (`C3 = archive_v2 full_repo top5`,
the same scorer) is used as the scorer's top-5. Against the headline reference R_prim:

| condition | n | ordered identical to scorer | set identical | mean Jaccard | mean identical positions (of 5) | Precision@5 scorer alone | Precision@5 final |
|---|---|---|---|---|---|---|---|
| C2a | 492 | 0.516 | 0.581 | 0.831 | 3.34 | 0.503 | 0.482 |
| C2b | 494 | 0.000 | 0.000 | 0.272 | 0.54 | 0.503 | 0.622 |

Scorer alone over all 500 scenarios: Precision@5 = 0.5035. (n is slightly below the
`§2` counts because a few scenarios have no deterministic top-5 to compare against.)
Report only; no interpretation. Full output:
`eval/results/real_eval_scorer_vs_final.{json,txt}`.

## 11. Ground-truth v1.2 and season-validity recomputation (old vs new)

`eval/data/ground_truth/crop_season_table_v1.2.csv` (v1.1 untouched) retracts the two
season rows the real data contradicts (Jowar/Rabi, Arhar/Rabi -> status `contradicted`)
and annotates Rice/Rabi and Maize/Rabi with the 2024-25-only evidence (status stays
`unverified`). See `CHANGELOG.md`. `contradicted` is a determinate negative (invalid
under both STRICT and LENIENT).

C3 season-validity recomputed over the 10,000 deterministic scenarios
(`eval/scripts/recompute_season_validity_v1_2.py`):

| table / mode | overall | stress | normal | Kharif | Rabi | Zaid | hard-violation rate |
|---|---|---|---|---|---|---|---|
| v1.1 strict  | 0.83590 | 0.71220 | 0.92592 | 0.98936 | 0.98650 | 0.52929 | 0.11464 |
| v1.2 strict  | 0.83590 | 0.71220 | 0.92592 | 0.98936 | 0.98650 | 0.52929 | 0.11464 |
| v1.1 lenient | 0.83608 | 0.71256 | 0.92597 | 0.98936 | 0.98704 | 0.52929 | 0.09459 |
| v1.2 lenient | 0.83590 | 0.71220 | 0.92592 | 0.98936 | 0.98650 | 0.52929 | 0.09459 |

STRICT is unchanged (a contradicted row was already counted in STRICT while unverified).
LENIENT overall 0.83608 -> 0.83590; Rabi 0.98704 -> 0.98650, because Jowar/Arhar only
rarely enter the C3 Rabi top-5. Hard-violation rate is unchanged. The v1.1 recomputation
matches the frozen `c3_season_validity_cited_v2.json` exactly (cross-check).

Out-of-scope observation (flagged, not changed): Barley has nonzero Kharif area in MP in
2015-16..2018-19 (369,098 ha), in tension with the v1.1 `Barley/Kharif` and
`Barley/Zaid` hard constraints. Those rows are `cited-v1.1`, not `unverified`, so they
are outside this correction.

## 12. The two out-of-vocabulary measures (28.1% vs 8.5%)

Two different quantities are in circulation; they are not comparable:

- **28.1% = cell-level, 10-year window.** Fraction of the 153 district x season cells
  whose *all-crop* real top-5 contains **at least one** crop outside the 21-crop registry,
  using the 10-year window 2015-16..2024-25 (the `CIRCULARITY.md` F3 figure). Mean 0.31
  out-of-vocab crops per cell.
- **8.5% = crop-level, 8-year window.** Mean over the 153 cells of the per-cell **share**
  of crops that are out-of-vocab within the R_all top-5 (`OOV crops / min(5, list length)`),
  using the pre-registered 8-year window 2015-16..2022-23 (this report, `§1`).

They differ on two axes: the unit (cells vs crops within a cell) and the window (10y vs
8y). A cell with a single out-of-vocab crop counts fully in the cell metric but
contributes only 1/5 in the crop metric. On matched windows the numbers are: 8-year
cell-level = 36.6%; 10-year crop-share = 6.3%.
