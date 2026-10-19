# S-series offline oracle, v2 (amendment to STEP 3)

Supersedes `S_ORACLE.md` (kept as historical record). Adds a **heatwave (temperature)** term so
the warming arm has an oracle, and states which mode is pre-specified per arm. Still reads only
frozen/GT tables + the risk indicators the replayed `mcp_server.risk_tool` produces.

## Inputs
- `eval/data/ground_truth/crop_season_table_v1.2.csv` (unchanged)
- `eval/data/ground_truth/hard_constraints_v1.1.csv` (unchanged)
- **NEW** `eval/data/series/s_heatwave_constraints_v1.0.csv` - heatwave blocks:
  - `heatwave_probability >= 0.35` (the risk tool's "moderate" band: >=3 consecutive days >=35C
    or a >=38C day)
  - `cited`: Wheat (ICAR-IIWBR terminal heat), Barley (IIWBR-EB53-2023), Gram (ICAR-IIPR),
    Mustard (ICAR-DRMR); `unverified`: Pea, Lentil.

## Oracle definition (v2)
```
SeasonValid(c,k)   := (c,k) in season_table and status in ALLOWED
ConstraintOK(c,s)  := not (c in FLOOD_BLOCKED    and flood_prob(s)    >= 0.40)
                    and not (c in DROUGHT_BLOCKED and drought_z(s)      <= -1.5)
                    and not (c in HEATWAVE_BLOCKED and heatwave_prob(s) >= 0.35)
Feasible(c,s)      := SeasonValid(c,k) and ConstraintOK(c,s)
```
`ALLOWED`: STRICT = {cited}; LENIENT = {cited, unverified}; `contradicted` excluded in both.

## Added risk indicators
`flood_probability`, `drought_z_score_30d`, `heatwave_probability` all come from the replayed
`mcp_server.risk_tool` over the perturbed weather copy (not from model output).

## Pre-specified mode per arm
- **Temperature arms (W1/W2/W3/H1) and compound (C1)**: STRICT is primary (heatwave + flood both
  have cited rows; Wheat/Barley/Gram/Mustard are cited).
- **Wet arms (WET1/WET2), onset arms (O1/O2), NE15, controls**: STRICT primary (flood/Urad cited).
- **Dry arms (D1/D2)**: the only relevant constraint (drought) is `unverified`, so STRICT `D = {}`.
  Pre-specified companion analysis for these two arms uses **LENIENT** (Rice, Sugarcane). Stated
  here before any model call.

## Metrics / contrasts
Unchanged from PROTOCOL 8.32.4-8.32.5: Stale@5 (primary) = `|top5 ∩ D|/|D|`, `D = F0 \ F1`;
Violation@5; Shift@5; Drop-faithful; contrasts C2a-C0b, C2b-C0b, C2a-C1a, C3-C2b; district-clustered
bootstrap 10000/42 + Holm.

## Circularity
Unchanged reasoning (`CIRCULARITY.md` F1/F4): constraint/season tables are agronomic documents,
independent of `crop_log.csv` (the scorer's source).
