# DB-version study (`db_v2`) - does updating ONLY the crop database improve agreement?

Pre-registration: `eval/PROTOCOL.md` section 8.31 (2026-10-16 06:24 UTC), written
before the held-out test period was scored. Offline study: **no new LLM/API calls.**
Measured quantity is **agreement** between recommendations and real district
cropping - this is not "accuracy".

## What changed (db_v2 vs db_v1)
- db_v1 = `crop_log.csv` (21 crops, sha256 `581852922f42490e6139fc021cc57da728e39e1fb84d3fad3f07f9cbc08ea304`).
- db_v2 = `crop_log_v2.csv` (22 crops, sha256 `dadcb1606b266d239543cdf7695e99aa0a41d49ce820a60685948a160954e6e6`).
- **Added: Linseed** (Rabi oilseed), sourced and cited in `eval/results/DB_V2_DIFF.md`.
- **Excluded: "Other Pulses"** - a DES aggregate residual, not a single sourceable crop.
- **Barley unchanged** (still Rabi): IIWBR EB-53 states barley is a strictly rabi crop;
  the real series' Kharif-barley block (2015-16..2018-19 only) is reported as an anomaly.
- Only the database changed: algorithm, tools, prompts and weights untouched, so the
  C3 (no-LLM) ranking is the clean way to isolate the database effect.

## Primary result (held-out test window 2020-21..2022-23, unrestricted real top-5)
Reference = mean-area top-5 per district-season over the test window, all crops
(canonical names; Linseed now in vocabulary). Analysis set = frozen 500-scenario
subset. db_v1 and db_v2 C3 recomputed over the same 500.

| metric | db_v1 | db_v2 | db_v2 - db_v1 [95% CI] | Cliff d | p | Holm |
|---|---|---|---|---|---|---|
| Precision@5 | 0.4396 | 0.4304 | **-0.0092** [-0.0159, -0.0031] | -0.031 | 5.5e-3 | 9.4e-3 |
| nDCG@5 | 0.4414 | 0.4349 | **-0.0065** [-0.0111, -0.0022] | -0.020 | 4.7e-3 | 9.4e-3 |

Both contrasts are Holm-significant and **negative**: adding Linseed *reduced*
agreement. District-clustered bootstrap (51 districts, seed 42, 10,000 resamples).

## Why (Linseed diagnostic)
Linseed is a genuine local top-5 crop in only **46/500** reference cells, but C3 with
db_v2 recommends Linseed in **69/500** scenarios (**22** true positives, **47** false):

| subset | n | P@5 db_v1 | P@5 db_v2 |
|---|---|---|---|
| db_v2 recommends Linseed | 69 | 0.4290 | 0.3623 |
| elsewhere | 431 | 0.4413 | 0.4413 |

All movement is confined to Rabi; Kharif and Zaid are unchanged:

| season | n | P@5 db_v1 | P@5 db_v2 |
|---|---|---|---|
| Kharif | 190 | 0.362 | 0.362 |
| Rabi | 177 | 0.451 | 0.425 |
| Zaid | 133 | 0.535 | 0.535 |

The scorer ranks Linseed highly across many Rabi scenarios (favourable
temperature/soil/season), so it displaces better-matching crops where Linseed is not
a local top-5 crop. The database addition was correct, but the scoring does not
localise Linseed narrowly enough to convert into agreement.

## Secondary / in-sample / sensitivity (all consistent, all slightly negative)
- Secondary (test restricted to db_v1's 21-crop vocab): P@5 0.5005 -> 0.4805
  (delta -0.0200, p~0); nDCG@5 0.5032 -> 0.4888.
- In-sample (build period, labelled in-sample): P@5 0.4598 -> 0.4534; nDCG 0.4720 -> 0.4677.
- Sensitivity: 2023-24 P@5 0.4380 -> 0.4260 (p=7.0e-4); 2024-25 0.4141 -> 0.4049 (p=7.4e-3).

## Out-of-vocab ceiling
Share of the reference top-5 that is out-of-vocabulary in the given database:
db_v1 **0.0876** -> db_v2 **0.0706** (Linseed removes its 13 reference slots). The
ceiling improved, but this did not translate into agreement.

## Season validity (10,000 C3 outputs, ground truth v1.2)
| variant | db_v1 overall | db_v2 overall | db_v1 hard | db_v2 hard |
|---|---|---|---|---|
| STRICT | 0.83590 | 0.81132 | 0.11464 | 0.11316 |
| LENIENT | 0.83590 | 0.83736 | 0.09459 | 0.09314 |

Under STRICT, Linseed is "unknown" in the ground-truth season table (it was never in
db_v1's vocabulary) and counts against validity, lowering it (Rabi 0.9865 -> 0.9124).
Under LENIENT, unknowns are excluded, so validity edges up (Rabi 0.9865 -> 0.9909).
No ground-truth file was edited to hide this.

## Combined table (all conditions on the SAME test reference)
`eval/results/db_v2_combined_table.{txt,json}`. LLM conditions used db_v1 and were
**not re-run**; C3 recomputed under both databases. On R_test_reg (db_v1 vocab):
nemotron C2b 0.637 best, C3 db_v1 0.500, C3 db_v2 0.480; llama C2a 0.428 best,
C3 db_v1 0.520, C3 db_v2 0.503. db_v2 does not change any LLM condition's ranking.

## Cost to re-run the LLM conditions on db_v2 (NOT executed)
`eval/results/db_v2_cost_estimate.{txt,json}`. C3 is deterministic (no API). Five LLM
conditions x {500 nemotron, 150 llama}, projected from the token/request volumes
actually recorded in the db_v1 runs:
- ~10,630 requests, 10.7M input tokens, 4.34M output tokens, ~17.7 h sequential at ~10 req/min.
- Dollar cost omitted: no citable public per-token price for these NVIDIA-hosted models.

## Conclusion
Under a pre-registered, held-out test window, **updating only the crop database did NOT
improve agreement.** Adding the correctly-sourced Rabi oilseed Linseed lowered
Precision@5 and nDCG@5 against the real test-period top-5 by ~1 point (Holm-significant),
because C3 recommends Linseed too broadly and displaces better-matching crops. The
out-of-vocab ceiling improved but was not converted into agreement. We report this
negative result as pre-registered; no threshold or scenario filtering was tuned after
seeing the test period.

## Reproduce
```
python eval/scripts/build_db_v2.py
python eval/scripts/dbv2_deterministic.py --crop-log crop_log.csv    --out eval/runs/db_v1_recheck --verify
python eval/scripts/dbv2_deterministic.py --crop-log crop_log_v2.csv --out eval/runs/db_v2/deterministic
python eval/scripts/dbv2_metrics.py
python eval/scripts/dbv2_combined_table.py
python eval/scripts/dbv2_cost_estimate.py
```
Artefacts: `eval/results/db_v2_test.{json,txt}`, `db_v2_combined_table.{json,txt}`,
`db_v2_cost_estimate.{json,txt}`, `DB_V2_DIFF.md`, `DB_SCOPE.md`.
