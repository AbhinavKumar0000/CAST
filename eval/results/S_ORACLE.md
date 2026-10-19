# S-series offline oracle (STEP 3)

Scope: define, OFFLINE, the agronomic feasibility oracle used to score the "simulated scenario"
runs, and demonstrate it is independent of the system under test. No model/LLM call is made here.

## 1. Inputs (frozen, not edited)
- `eval/data/ground_truth/hard_constraints_v1.1.csv` — infeasible crop/condition pairs.
  - `season` rows: all `cited` (SLBC-MP-2020 / evikas-MP / IIWBR).
  - `flood` rows (threshold `flood_prob >= 0.40`): `Urad` is `cited` (agritech-TNAU-2013);
    `Moong`, `Sesame (Til)`, `Groundnut`, `Watermelon` are `unverified`.
  - `drought` rows (threshold `drought_z <= -1.5`): `Rice`, `Sugarcane`, both `unverified`.
- `eval/data/ground_truth/crop_season_table_v1.2.csv` — crop × season validity. Statuses:
  `cited`, `unverified`, and `contradicted` (Jowar/Rabi and Arhar/Rabi are **contradicted** and
  are therefore treated as INVALID seasons, not valid).

These two tables are the ONLY oracle inputs. They are agronomic documents, not model output.

## 2. Oracle definition
For a scenario `s` with season `k` (from `season_tool.MONTH_TO_SEASON` on `s.as_of_date`) and the
risk indicators the replayed tool produces, `flood_prob(s)` and `drought_z(s)`:

```
SeasonValid(c, k)  :=  (c, k) in season_table and status in ALLOWED
ConstraintOK(c, s) :=  not ( c in FLOOD_BLOCKED  and flood_prob(s)  >= 0.40 )
                    and not ( c in DROUGHT_BLOCKED and drought_z(s)   <= -1.5 )
Feasible(c, s)     :=  SeasonValid(c, k) and ConstraintOK(c, s)
```

Two oracle variants are reported, fixed in advance:
- **STRICT** (primary): `ALLOWED = {cited}` and blocked-crop lists use only `cited` rows
  → FLOOD_BLOCKED = {Urad}; DROUGHT_BLOCKED = {}.
- **LENIENT** (secondary): `ALLOWED = {cited, unverified}` and the full blocked lists
  → FLOOD_BLOCKED = {Urad, Moong, Sesame (Til), Groundnut, Watermelon};
  DROUGHT_BLOCKED = {Rice, Sugarcane}.

`contradicted` rows are excluded from `ALLOWED` in both variants.

Per perturbation set `p` (S_SCOPE / S_PERTURBATIONS) the oracle yields:
- `F0(s)` base feasible set (unperturbed scenario), and `F1(s,p)` perturbed feasible set.
- **Newly infeasible** `D(s,p) = F0(s) \ F1(s,p)` — crops planted validly at base that the
  perturbation makes infeasible. Because the season table is static, `D` is driven by the risk
  block via the replayed weather; `S·O1/O2` can additionally move `k` across a MONTH_TO_SEASON
  boundary, which also changes `SeasonValid`.

## 3. Scoring (formalised in PROTOCOL §8.32)
`top5(c, s, p)` = the condition's recommended crops for scenario `s` under set `p`.
- **Stale@5** = `| top5 ∩ D | / |D|`  — share of newly-infeasible crops the system keeps.
- **Violation@5** = `| top5 ∩ (crops \ F1) | / min(5, |top5|)` — share of recommendations invalid
  under the perturbed oracle.
- **Shift@5** = `1 - Jaccard(top5(c,s,base), top5(c,s,p))` — how much advice moved.
- **Drop-faithful** = `| D \ top5(c,s,p) | / |D|` — newly-infeasible crops correctly removed
  (= 1 - Stale@5).
- Primary contrasts (per-protocol, district-clustered bootstrap, Holm): `C2a−C0b`, `C2b−C0b`,
  `C2a−C1a`, `C3−C2b` on **Stale@5** (primary) and Violation@5 (secondary).
- Controls: `S·N0` must give `Shift@5 = 0`, `Stale@5` equal to base; `S·N1` must reverse direction
  of the warm/dry arms.

## 4. Independence from the system under test (circularity)
- The oracle reads ONLY `hard_constraints_v1.1.csv` + `crop_season_table_v1.2.csv`. The scorer
  (`mcp_server/crop_score_tool.py`) ranks from `crop_log.csv`'s hand-authored requirement ranges.
  The two share **no numeric provenance** (constraint/season tables are SLBC-MP / evikas-MP /
  IIWBR agronomic documents; `crop_log.csv` is hand-authored). This is the same separation
  documented for the real-world reference in `eval/real_data/CIRCULARITY.md` (F1, F4).
- Risk indicators (`flood_prob`, `drought_z`) come from the replayed tool (`eval/tools/eval_risk_tool.py`
  over the weather cache), i.e. from the scenario's weather, not from any model output.
- The perturbation changes ONLY the weather copy + `as_of_date`. The model is never shown the
  oracle, `D`, or the constraint tables.
- Residual risk (unchanged): LLM training contamination (CIRCULARITY F5) — disclosed, not
  resolvable in-repo; Stale@5 is defined against a rule set, so training knowledge of MP crop
  seasons could help a no-tool model on the SEASON part but cannot help it on the weather-driven
  risk part (which it cannot observe without the tool).

## 5. Deliverable
This note + PROTOCOL §8.32 (pre-registration, STEP 4) + the oracle driver script (to be added in
the run step, producing `eval/results/S_ORACLE_<oracle>.csv`). No run is executed in STEP 3.
