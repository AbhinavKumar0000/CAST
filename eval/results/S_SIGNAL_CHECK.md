# S-series pre-run signal audit (harness build step)

No model call was made. This note records what the (already pre-registered, PROTOCOL §8.32)
oracle does under each perturbation, computed offline from the real tools over the frozen
base set of 40 scenarios (`eval/results/s_base_set.json`).

## How this was produced
- `eval/s_series/perturbations.py` — 13 named transforms on a COPY of the per-district weather
  date-map (`W1/W2/W3`, `R1/R2/R3`, `O1/O2`, `H1`, `C1`, `N0`, `N1`, `NE15`).
- `eval/s_series/builder.py` — `PerturbedTimeAnchoredBuilder` subclasses the existing
  `TimeAnchoredBuilder`; runs the REAL six tools under a perturbed weather map. `mcp_server/`
  untouched. `S·N0` (identity) reproduces `eval/runs/archive_v2/evidence/*.json` exactly
  (flag changes = 0), so the pipeline is faithful.
- `eval/scripts/build_s_evidence.py` — built perturbed evidence bundles for all 13 sets x 40
  scenarios (520 bundles) into `eval/runs/s_evidence/<set>/<sid>.json` and computed the oracle
  shift (`D = F0 \ F1`) in both STRICT and LENIENT modes.

## Result: the oracle barely moves

`|D|tot` = total newly-infeasible crop-instances across the 40 scenarios; `sig` = scenarios with `|D|>0`.

| set | STRICT sig/|D|tot | LENIENT sig/|D|tot | note |
|-----|------------------|-------------------|------|
| W1 (+1.0C)  | 0 / 0 | 0 / 0 | no drought/flood change |
| W2 (+2.0C)  | 0 / 0 | 0 / 0 | no drought/flood change |
| W3 (+3.0C)  | 0 / 0 | 0 / 0 | no drought/flood change |
| H1 (sowing heat) | 0 / 0 | 0 / 0 | no drought/flood change |
| R1 (x0.80)  | 0 / 0 | 0 / 0 | SPI invariant (see below) |
| R2 (x0.60)  | 0 / 0 | 0 / 0 | SPI invariant |
| R3 (x1.30)  | 0 / 0 | 3 / 6 | near-threshold noise only |
| C1 (hot+dry)| 0 / 0 | 0 / 0 | SPI invariant |
| N1 (cool+wet)| 0 / 0 | 2 / 4 | near-threshold noise only |
| O1 (onset +14d) | 1 / 1 | 2 / 6 | real signal (phase change) |
| O2 (onset +28d) | 2 / 2 | 3 / 12 | real signal (phase change) |
| NE15 (year=2015) | 7 / 7 | 8 / 32 | real signal (year substitution) |
| N0 (identity) | 0 / 0 | 0 / 0 | control: correctly zero |

## Root cause (two independent problems)

1. **Temperature perturbations cannot move the oracle.** The pre-registered oracle's only
   weather-driven constraints are `flood_prob>=0.40` and `drought_z<=-1.5`. Temperature affects
   `heatwave_probability` (max |Delta| = 0.44 under +2C) but the oracle has NO heatwave term.
   So the entire warming arm (W1/W2/W3/H1) has `D = {}` and **Stale@5 (the primary outcome) is
   undefined** for it.

2. **Uniform precipitation multipliers are scale-invariant for the drought index.** `risk_tool`
   fits a gamma distribution to the archive monthly totals and scores the observed 30-day total
   against it (`_calculate_spi_1`). Scaling the WHOLE series by k scales both the fitting sample
   and the observation, so the CDF is unchanged. Measured: `max |Delta drought_z| (base vs x1.30)
   = 0.00` across all 40 scenarios. Flood uses ABSOLUTE mm thresholds and does move a little
   (max `Delta = 0.18`) but not enough to cross 0.40 on the Kharif/Urad scenarios. So R1/R2/R3/C1
   are near-no-ops for the oracle.

Only perturbations that change the SHAPE/PHASE of the series (onset shift O1/O2; year
substitution NE15) move the standardized index.

## Consequence for the pre-registered plan
Running Tier A as-is would produce a primary outcome (Stale@5) that is **undefined for 8 of 11
run sets** (all of W1/W2/W3/H1/R1/R2/R3/C1) and defined only on a handful of scenarios for
O1/O2/NE15. The model-facing evidence DOES change under every arm (weather/crop_score/heatwave),
so the secondary "did advice move" (Shift@5) is still measurable — but the "did it move
CORRECTLY" oracle is starved for the headline warming arm.

## Options (need user decision before any model call)
1. **Amend the oracle to add a temperature/heatwave constraint** (e.g. heatwave_probability-based
   block) so the warming arm has an oracle — requires a NEW pre-registration timestamp.
2. **Replace the uniform precip multipliers with shape/intensity perturbations** that move SPI and
   flood (e.g. a "30-day dry spell" and an "extreme-wet week" arm) — requires a NEW pre-registration.
3. **Do both 1 and 2**, re-registered, then run.
4. **Keep §8.32 exactly as pre-registered**, run, and report the warming/multiplier arms as
   "primary undefined (|D|=0)"; rely on Shift@5 / Violation@5 descriptively.

## Resolution (user chose option 1: amend oracle + perturbations, re-register)
Done, pre-run, no model call:
- Oracle amended with a sourced **heatwave** term (`S_ORACLE_V2.md`,
  `eval/data/series/s_heatwave_constraints_v1.0.csv`).
- Uniform rain multipliers replaced by **shape/intensity** arms (`S_PERTURBATIONS_V2.md`):
  S-D1/S-D2 (dry spells), S-WET1/S-WET2 (heavy/extreme-rain weeks); S-N1 is now cooling-only.
- New pre-registration **PROTOCOL §8.33** (2026-10-16 08:53 UTC).
- Re-audited offline: every arm now moves the oracle in the correct direction
  (`eval/results/s_oracle_signal.json`; summary table in `S_PERTURBATIONS_V2.md`).
- Bug fixed during this work: `oracle.feasible_set` now takes a single `flags` mapping
  (`oracle.flags_of(bundle)`), removing a flood/drought positional swap in the first audit pass.
