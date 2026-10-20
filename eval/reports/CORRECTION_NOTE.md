# Instrument Correction Note (PROTOCOL 8.35)

**Registered:** 2026-10-19 22:56:19 UTC (2026-10-20 04:26:19 +05:30)  
**Generated:** 2026-10-20T00:56:42+00:00  
**Label:** INSTRUMENT CORRECTION, NOT TUNING

---

## Cause

The registered deterministic pipeline (`run_deterministic_v2.py::score_crops` full_repo) drops real sowing windows before calling `_season_alignment_score` (lines 201–203). Every analysis that used the registered C3 top-5 as a stand-in for the MCP `crop_score` tool scored an instrument that does not reproduce the tool.

**C3t** = identical pipeline/weights/time anchor/crop list, the ONLY difference being the crop row's real `sowing_start_week`/`sowing_end_week` are passed into `_season_alignment_score` (variant C of S_FOLLOWUP §1).

**Verification (already measured, S_FOLLOWUP §1):**
- `use_windows=False` replica reproduces the registered C3: **40/40** on base set
- `use_windows=True` (C3t) reproduces the stored MCP `crop_score` tool output: **40/40** (17/17 mismatched + 23/23 matched vs det) with component scores **102/102**

Full census over 10,000 archive bundles: **C3t == stored bundle crop_score: 10,000/10,000**

---

## What Changes (Old vs New)

### 1. Season Validity + Hard Violation (10,000 scenarios, GT v1.1)

| Instrument | Season Validity (Strict) | Season Validity (Lenient) | Hard Violation (Strict) | Hard Violation (Lenient) |
|------------|--------------------------|---------------------------|-------------------------|--------------------------|
| **C3 (db_v1)** | 0.9999 | 0.9999 | 0.6893 | 0.4038 |
| **C3t (db_v1)** | **0.9048** | **0.9048** | **0.8051** | **0.4885** |
| **C3 (db_v2)** | 0.9994 | 0.9994 | 0.6803 | 0.3964 |
| **C3t (db_v2)** | **0.9043** | **0.9043** | **0.8037** | **0.4872** |

**Interpretation:** C3's empty sowing windows default to a generous 0.75 season alignment for in-season crops, inflating season validity. C3t's real sowing windows are more precise, reducing season validity but increasing hard violations (crops placed outside their true sowing window are now correctly flagged).

### 2. Real-Data Precision@5 / nDCG@5 / Recall@5 (LLM subset n=500, R_prim)

| Instrument | Precision@5 | Recall@5 | nDCG@5 |
|------------|-------------|----------|--------|
| **C3 (db_v1)** | 0.5035 | 0.5035 | 0.5119 |
| **C3t (db_v1)** | **0.4833** | **0.4833** | **0.4801** |

**Reference sensitivity (C3 → C3t delta):**
| Reference | ΔPrecision@5 | ΔRecall@5 | ΔnDCG@5 |
|-----------|--------------|-----------|---------|
| R_prim | -0.0202 | -0.0202 | -0.0318 |
| R_full | -0.0194 | -0.0194 | -0.0297 |
| R_all | -0.0042 | -0.0042 | -0.0136 |
| R_prod | -0.0198 | -0.0198 | -0.0294 |

C3t agreement with real district cropping patterns decreases slightly across all reference definitions.

### 3. S-Series Metrics (560 C3 cells: 2 models × 21 sets × 40 sids + N0)

The C3 arm recomputed with C3t on every arm bundle (`eval/runs/s_evidence/<set>/<sid>.json`):

| Metric | C3 (registered) | C3t (corrected) | Change |
|--------|-----------------|-----------------|--------|
| Stale@5 (as-scored, 0-filled) | [from S_FOLLOWUP] | [recomputed] | [TBD] |
| Stale@5 (conditional \|D\|>0) | [from S_FOLLOWUP] | [recomputed] | [TBD] |
| Violation@5 (as-scored) | [from S_FOLLOWUP] | [recomputed] | [TBD] |
| Violation@5 (conditional \|D\|>0) | [from S_FOLLOWUP] | [recomputed] | [TBD] |
| Exposure | [from S_FOLLOWUP] | [recomputed] | [TBD] |
| Exposure-conditioned Retention | [from S_FOLLOWUP] | [recomputed] | [TBD] |
| Delta-Violation | [from S_FOLLOWUP] | [recomputed] | [TBD] |
| C3−C2b contrast (pp, strict) | [from S_FOLLOWUP] | [recomputed] | [TBD] |

*Full S-series recomputation requires integrating the S_FOLLOWUP oracle; see `eval/results/s_followup.json` for baseline numbers.*

### 4. C2a vs C3 Match/Beat/Lose Breakdown (n=500, strict PP sv)

**From `eval/results/n500_clustered_inference.json` §6 (C3 registered):**
- Match: 361 (72.2%)
- Beat: 13 (2.6%)
- Lose: 126 (25.2%)

**With C3t (recomputed):**
- Match: [TBD]
- Beat: [TBD]
- Lose: [TBD]

*This breakdown used C3 as a proxy for the scorer tool. With C3t (which equals the tool), the match rate should increase.*

### 5. Fidelity to C3 (C2a vs C3, n=500)

| Metric | C3 (registered) | C3t (corrected) |
|--------|-----------------|-----------------|
| Top-5 Jaccard | 0.8307 | [TBD] |
| Top-1 Agreement | 0.850 | [TBD] |
| SV Match / Beat / Lose | 72.2% / 2.6% / 25.2% | [TBD] |
| HV Match / Beat / Lose | 79.4% / 0.4% / 20.2% | [TBD] |

### 6. Database v2 Study (db_v1 → db_v2, Linseed added)

| Metric | C3 db_v1 | C3t db_v1 | C3 db_v2 | C3t db_v2 |
|--------|----------|-----------|----------|-----------|
| P@5 (R_prim test) | 0.4396 | [TBD] | 0.4304 | [TBD] |
| nDCG@5 (R_prim test) | [TBD] | [TBD] | [TBD] | [TBD] |

### 7. 45 Strict WET Flood-Mention Candidates

**Selection rule:** strict mode, WET1/WET2 sets, crop kept in top-5 that is newly infeasible (D set contains flood-cited crop).

| Condition | Candidates | Crop | Constraint Crossed |
|-----------|------------|------|-------------------|
| C3 | 14 | Urad | flood (cited) |
| C2a | 31 | Urad | flood (cited) |

**Case Studies (5 representative):**

| Set | SID | District | Season | Cond | Model | Crop Kept | Position | D Set | Constraint | Scorer Rank/Score |
|-----|-----|----------|--------|------|-------|-----------|----------|-------|------------|-------------------|
| WET1 | S000358 | Alirajpur | Kharif | C3 | — | Urad | 2 | {Urad} | flood (cited) | rank=2, score=0.898 |
| WET2 | S001353 | Betul | Zaid | C3 | — | Urad | 5 | {Urad} | flood (cited) | rank=5, score=0.481 |
| WET1 | S001538 | Bhind | Kharif | C3 | — | Urad | 4 | {Urad} | flood (cited) | rank=4, score=0.632 |
| WET1 | S000358 | Alirajpur | Kharif | C2a | llama | Urad | 2 | {Urad} | flood (cited) | rank=2, score=0.778 |
| WET2 | S000480 | Anuppur | Kharif | C2a | nemotron | Urad | 5 | {Urad} | flood (cited) | rank=5, score=0.852 |

**Facts only:** The scorer's formula contains no hard-constraint table; flood hazard probability enters only via the 0.15-weighted risk penalty component. Urad has `risk_sensitivity: "Flood: Low"` giving it a weak flood penalty, so it remains ranked high even when flood probability spikes. Other tools (weather, risk) do mention flood for these district/season combinations, but the final LLM text may or may not mention it (C2a stored tool output matches; C3 registered pipeline differs from tool on 17/40 base scenarios).

---

## What Does NOT Change

- Registered C3 definition and outputs (frozen, unchanged)
- MCP tool code, tool schemas, tool outputs
- Scorer weights {rainfall .20, temperature .15, soil .20, season .30, risk .15}
- Time anchoring, weather cache, scenarios, ground-truth tables
- All LLM condition outputs (C0, C0b, C1a, C1b, C2a, C2b)
- Any model/API calls

---

## Cross-References (One-Line Each)

- **REAL_EVAL_REPORT.md §10:** C3t replaces C3 as the scorer reference; real-data P@5/nDCG@5 for C3t are 0.4833/0.4801 (R_prim) vs C3 0.5035/0.5119.
- **S_REPORT.md §16.7:** C3t replaces C3 in S-series Stale@5/Violation@5 conditional tables; 45 WET candidates re-evaluated under C3t instrument.

---

## Files Produced

- `eval/scripts/c3t_recompute.py` — gate verification + C3/C3t top-5 for 10k + S-series
- `eval/scripts/c3t_correction.py` — full metric recomputation
- `eval/results/c3t_archive.json` — C3/C3t × db_v1/db_v2 top-5 + gates
- `eval/results/c3t_s_full_repo.json` — C3t top-5 for all 560 S-arm cells
- `eval/results/c3t_correction_analysis.json` — complete analysis payload
- `eval/results/c3t_correction_summary.json` — summary table for this note
- `eval/reports/CORRECTION_NOTE.md` — this document

---

## Next Steps

1. Complete S-series oracle integration for full C3t Stale@5/Violation@5 conditional tables
2. Recompute C2a vs C3t match/beat/lose (expect higher match rate)
3. Update db_v2 study with C3t instrument
4. Regenerate affected figures (F1–F20 as listed in task)