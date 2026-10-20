# S REPORT — simulated-scenario study ("S" series)

**Status: COMPLETE — AWAITING USER APPROVAL.** No commit has been made; nothing is pushed.
Report written 2026-10-19. Scoring outputs generated 2026-10-19T01:25:01Z; supplementary
conditional outputs 2026-10-19; figures 2026-10-19.

| Item | Location |
|---|---|
| Pre-registration (ACTIVE) | `eval/PROTOCOL.md` §8.33 (2026-10-16 08:53 UTC); §8.32 (07:25 UTC) superseded as per its own terms |
| Scorer | `eval/scripts/score_s.py` (offline, no model calls) |
| Registered outputs | `eval/results/s_scores.json`, `eval/results/s_scores_cells.csv`, `eval/results/s_sanity.json` |
| Supplementary (disclosure) | `eval/scripts/s_score_conditional_supp.py` → `eval/results/s_scores_conditional.json` |
| C3 instrument recompute | `eval/scripts/s_c3_recompute.py` → `eval/results/s_c3_full_repo.json` |
| Figures | `eval/scripts/s_figures.py` → `eval/results/figures/` (5 figures × PDF + PNG + CSV) |
| Metric tests | `eval/tests/test_s_metrics.py` — 11/11 pass |
| Retry audit | `eval/results/s_retry_audit.json` / `.md` |

Everything below was computed by script from frozen inputs; every number in this report can be
re-derived from the provenance table (§19). Results are reported good or bad, with no post-hoc
retuning. **This report ends awaiting user approval; interpretation for a paper is out of scope.**

---

## 1. Claim under test (§8.32.1, unchanged)

LLM-only advice rests on training-era knowledge; the MCP tool path lets the model use the
(current) data it can read. Test: under a changed-conditions "simulated scenario", tool-using
conditions (C1a/C2a/C2b/C3) change their advice while no-tool conditions (C0/C0b) do not.

Design: 13 perturbation sets × 40 base scenarios × 3 tool-using conditions (C1a/C2a/C2b) ×
2 models = **3 120 run cells**
(`W1 W2 W3 H1 D1 D2 WET1 WET2 O1 O2 C1 N1 NE15`), plus C0/C0b (reused canonical base
responses, by registration §8.33.4 — not re-run per set), C3 (registered deterministic
pipeline, recomputed offline), and the N0 identity control (evidence identity, not LLM-run).

## 2. Data collection and retry audit

- **Retry audit (BEFORE-2, 2026-10-18T22:12Z):** 119 failure records across the S runs, all on
  nemotron (model_failure 74, api_status_400 45), all classified **infra**, all
  **retried and succeeded (119/119)** after the provider outage (incident NPC-1,
  `eval/PROGRESS.md`).
- **Records present:** 3 120/3 120 (check `run_records_present`).
- **Usable final cells:** 3 001; **unusable 119** — `llama|invalid_json` 65,
  `nemotron|invalid_json` 32, `nemotron|truncated` 22. (This 119 is a *different* census from
  the retry-audit 119: these are final records where the model returned malformed/over-long
  output, handled by pp/ITT below; the retried cells are healthy in the final files.)
  Raw-file state: 25 of 26 set×model files hold exactly 120/120 ok records; the raw
  `s_W1/eval_nemotron-3-ultra` file still contains its 119 historical error records next to
  the 120 successful ones (239 raw entries). The scorer's documented prefer-non-error dedupe
  (`load_pert_records`) resolves every cell to its successful record — `dedupe_no_duplicate_ok`
  (0 both-ok duplicates) and `usable_after_audit` (0 error cells left) both PASS, and the
  audit verified all 119 retried cells succeeded.
- **Evidence bundles:** 520/520 (13 sets × 40), including N0.

## 3. Validity checks — 20/20 PASS (`s_sanity.json`)

| # | Check | Key detail |
|---|---|---|
| 1 | `oracle_input_sha256_unchanged` | all frozen input hashes match BEFORE-1 record |
| 2 | `baseline_canonical_extraction` | presence 40/40 for all 10 model×condition baselines; usable see §6 |
| 3 | `c3_baseline_nonempty` | base 40 C3 top-5s present |
| 4 | `c3_recompute_reproduces_frozen_base_40` | 40 match / 0 mismatch vs `archive_v2/deterministic` |
| 5 | `c3_recompute_complete_all_sets` | 560 cells recomputed, none missing/errored |
| 6 | `c0_c0b_prompt_hash_invariance` | 160 match / 0 mismatch / 0 unverifiable (original NFC records, U+241F separator) |
| 7 | `run_records_present` | 3 120/3 120 present; usable 3 001; unusable reasons in §2 |
| 8 | `dedupe_no_duplicate_ok` | no duplicate (model,set,sid,cond) cells |
| 9 | `usable_after_audit` | 0 error cells left after retry |
| 10 | `c0_c0b_not_rerun_reused_by_design` | C0/C0b point to canonical base records |
| 11 | `evidence_bundles_complete` | 520/520 |
| 12 | `season_invariant_across_sets` | season labels identical across all sets |
| 13 | `s_run_prompt_hash_recomputation` | 3 120/3 120 match (S-run separator `\x1f`) |
| 14 | `c2a_c2b_prompt_set_invariant` | prompts identical across sets within condition |
| 15 | `tool_output_chain_of_custody` | 11 660/11 660 tool outputs byte-match their bundles (dual-hash rule, §13.4) |
| 16 | `canonical_crops_within_oracle_universe` | all advice crops ∈ oracle universe |
| 17 | `n0_evidence_identity_vs_archive` | all 40 N0 bundles identical to archive (all 6 tools incl. crop_score) |
| 18 | `n0_shift_control_shift5_zero` | max Shift@5 = 0.0 (registered harness control) |
| 19 | `n0_oracle_no_signal_strict_and_lenient` | max D = 0 over 80 cells |
| 20 | `n0_stale_equals_base` | N0 stale = base stale = 0 for all 40 |

## 4. Oracle signal per arm (measured, matches §8.33.4a)

Cells with |D| > 0 / total |D| per set (40 scenarios; identical across conditions and models):

| Set | STRICT | LENIENT |
|---|---|---|
| W1 | 2 / 8 | 2 / 12 |
| W2 | 2 / 8 | 2 / 12 |
| W3 | 2 / 8 | 2 / 12 |
| H1 | 2 / 8 | 2 / 12 |
| D1 | **0 / 0** | 10 / 20 |
| D2 | **0 / 0** | 11 / 22 |
| WET1 | 21 / 21 | 21 / 84 |
| WET2 | 21 / 21 | 21 / 84 |
| O1 | 1 / 1 | 3 / 8 |
| O2 | 2 / 2 | 4 / 14 |
| C1 | 2 / 8 | 12 / 32 |
| N1 | 0 / 0 | 0 / 0 |
| NE15 | 2 / 2 | 14 / 31 |

Signal cells: **57/520 strict, 104/520 lenient** (per model). D1/D2 strict have no oracle
movement at all → their registered companion analysis is LENIENT (§8.33.3).

## 5. Registered convention for Stale@5 at |D| = 0 — READ FIRST

§8.32.4 defines Stale@5 = |top5 ∩ D| / |D|, which is **undefined when |D| = 0**. The scorer
returns **0.0** in that case (`stale_at5`, `score_s.py` L94–99; the docstring there calls this
a "registered convention" — it is NOT in §8.32/§8.33 and that wording is itself logged as
bug B9). Consequences, disclosed in full:

- All pooled/per-set Stale@5 (and Drop = 1 − Stale) levels and contrasts in `s_scores.json`
  are computed over **all** usable cells, with |D| = 0 cells contributing a vacuous 0 (Stale)
  / 1 (Drop). Under ITT the cell set is identical for every condition, so a pooled contrast
  is exactly the signal-conditional contrast scaled by 57/520 ≈ 1/9.12 (sign and Holm
  verdicts preserved; magnitudes shrunk ~9×). Under pp the same holds to within the few
  unusable cells.
- To report the metric **as registered** (undefined cells excluded), an offline supplementary
  run recomputes levels and all four contrasts with the identical machinery
  (district clusters, N_RES/SEED = 10 000/42, pp/ITT, Holm): `s_scores_conditional.json`.
  It is clearly labelled UNREGISTERED sensitivity. **Both conventions are reported below.**
- Shift@5 and Violation@5 are defined everywhere and are unaffected.
- Movement-not-explained-by-hard-constraint-changes (§14.3) exists precisely to quantify advice movement on the |D| = 0 cells.

Verification: conditional ITT C2a−C0b (llama, strict) = +0.294 ≈ 0.032 × 9.12 ✓.

## 6. Coverage and usable baselines (scoring-time, disclosed)

Run cells (§2): usable 3 001/3 120. Canonical baselines — presence 40/40 everywhere; **usable**:

| | C0 | C0b | C1a | C2a | C2b |
|---|---|---|---|---|---|
| llama | 40 | 40 | 40 | 38 | 36 |
| nemotron | 39 | 38 | 37 | 40 | 39 |

Nemotron C0/C0b unusable cache records were replaced at scoring time by the first usable copy
from the on-disk canonical runs (`enrich_baseline`, no model call — §13.5). Three cells have
**no usable record anywhere**: nemotron C0 `S003310`, C0b `S001865`, `S002685` — excluded from
pp, worst-cased in ITT. pp cell counts (strict, WITH_pilot): llama C0/C0b/C1a/C3 = 520, C2a = 518,
C2b = 457; nemotron C0 = 507, C0b = 494, C1a = 481, C2a = 520, C2b = 505.

**pp / ITT definitions** (as locked in the real series, PROTOCOL L495–500, and implemented in
`real_eval.py`): *pp* excludes unusable responses; *ITT* enters every planned cell with the
metric's worst case (Stale 1.0 if |D| > 0 else 0.0; Violation/Shift 1.0; Drop 0.0 if |D| > 0
else 1.0). Pilot membership is a separate axis (WITH_pilot 40 sids / WITHOUT_pilot 32; the
8 pilot∩base sids are `S000279 S000289 S000311 S000358 S000464 S000480 S000646 S000687`).
Shift@5 additionally requires a usable canonical baseline for that condition (metric-aware
cell usability, §13.6).

---

## 7. Headline levels — pooled, WITH_pilot, STRICT, **|D| = 0 → 0 convention** (as scored)

Mean [95 % district-clustered CI] (n). `st`=Stale@5, `vi`=Violation@5, `sh`=Shift@5, `dr`=Drop-faithful.
`st` and `vi` are **higher = worse** (`sh` = higher means more movement, `dr` = higher means better).

**llama — pp**

| cond | st | vi | sh | dr |
|---|---|---|---|---|
| C0 | 0.005 [0.000,0.012] (520) | 0.659 [0.567,0.756] (520) | 0.000 [0.000,0.000] (520) | 0.995 [0.988,1.000] (520) |
| C0b | 0.005 [0.000,0.012] (520) | 0.639 [0.545,0.739] (520) | 0.000 [0.000,0.000] (520) | 0.995 [0.988,1.000] (520) |
| C1a | 0.007 [0.000,0.019] (520) | 0.622 [0.523,0.724] (520) | 0.132 [0.080,0.186] (520) | 0.993 [0.981,1.000] (520) |
| C2a | 0.037 [0.019,0.059] (518) | 0.128 [0.072,0.200] (518) | 0.273 [0.229,0.326] (492) | 0.963 [0.941,0.981] (518) |
| C2b | 0.003 [0.000,0.008] (457) | 0.331 [0.253,0.405] (457) | 0.511 [0.440,0.585] (419) | 0.997 [0.992,1.000] (457) |
| C3 | 0.038 [0.018,0.062] (520) | 0.092 [0.058,0.127] (520) | 0.139 [0.123,0.155] (520) | 0.962 [0.938,0.982] (520) |

**llama — ITT** (n = 520 for all cells)

| cond | st | vi | sh | dr |
|---|---|---|---|---|
| C0 | 0.005 [0.000,0.012] | 0.659 [0.567,0.756] | 0.000 [0.000,0.000] | 0.995 [0.988,1.000] |
| C0b | 0.005 [0.000,0.012] | 0.639 [0.545,0.739] | 0.000 [0.000,0.000] | 0.995 [0.988,1.000] |
| C1a | 0.007 [0.000,0.019] | 0.622 [0.523,0.724] | 0.132 [0.080,0.186] | 0.993 [0.981,1.000] |
| C2a | 0.037 [0.019,0.059] | 0.131 [0.075,0.203] | 0.312 [0.235,0.414] | 0.963 [0.941,0.981] |
| C2b | 0.014 [0.002,0.030] | 0.412 [0.349,0.472] | 0.606 [0.532,0.676] | 0.986 [0.970,0.998] |
| C3 | 0.038 [0.018,0.062] | 0.092 [0.058,0.127] | 0.139 [0.123,0.155] | 0.962 [0.938,0.982] |

**nemotron — pp**

| cond | st | vi | sh | dr |
|---|---|---|---|---|
| C0 | 0.029 [0.014,0.045] (507) | 0.367 [0.249,0.478] (507) | 0.000 [0.000,0.000] (507) | 0.971 [0.955,0.986] (507) |
| C0b | 0.031 [0.011,0.059] (494) | 0.329 [0.223,0.444] (494) | 0.000 [0.000,0.000] (494) | 0.969 [0.941,0.989] (494) |
| C1a | 0.044 [0.028,0.059] (481) | 0.323 [0.229,0.424] (481) | 0.427 [0.358,0.501] (449) | 0.956 [0.941,0.972] (481) |
| C2a | 0.040 [0.021,0.063] (520) | 0.153 [0.086,0.243] (520) | 0.139 [0.119,0.157] (520) | 0.960 [0.937,0.979] (520) |
| C2b | 0.032 [0.017,0.050] (505) | 0.255 [0.193,0.329] (505) | 0.355 [0.296,0.419] (495) | 0.968 [0.950,0.983] (505) |
| C3 | 0.038 [0.018,0.062] (520) | 0.092 [0.058,0.127] (520) | 0.139 [0.123,0.155] (520) | 0.962 [0.938,0.982] (520) |

**nemotron — ITT** (n = 520)

| cond | st | vi | sh | dr |
|---|---|---|---|---|
| C0 | 0.036 [0.018,0.055] | 0.383 [0.262,0.498] | 0.025 [0.000,0.081] | 0.964 [0.945,0.982] |
| C0b | 0.037 [0.015,0.066] | 0.362 [0.252,0.481] | 0.050 [0.000,0.128] | 0.963 [0.934,0.985] |
| C1a | 0.048 [0.030,0.067] | 0.374 [0.279,0.470] | 0.506 [0.413,0.606] | 0.952 [0.933,0.970] |
| C2a | 0.040 [0.021,0.063] | 0.153 [0.086,0.243] | 0.139 [0.119,0.157] | 0.960 [0.937,0.979] |
| C2b | 0.041 [0.023,0.059] | 0.277 [0.207,0.363] | 0.386 [0.308,0.476] | 0.959 [0.941,0.977] |
| C3 | 0.038 [0.018,0.062] | 0.092 [0.058,0.127] | 0.139 [0.123,0.155] | 0.962 [0.938,0.982] |

C0/C0b Shift = 0 is **by construction**: those responses are
reused from the base run (§8.33.4), so their shift cells are trivially unchanged.

## 8. Registered contrasts — Stale@5, pooled, WITH_pilot, STRICT (**as scored, 0-convention**; **higher = worse**)

Family = the 4 contrasts within each (model, subset, analysis, scope, mode, metric); Holm across 4.

| model | analysis | contrast | Δ [95 % CI] | p | Holm | n |
|---|---|---|---|---|---|---|
| llama | pp | C2a−C0b | **+0.032 [+0.018,+0.050]** | 0.0004 | **0.0012** | 518 |
| llama | pp | C2b−C0b | −0.001 [−0.002,+0.000] | 0.4527 | 0.4527 | 457 |
| llama | pp | C2a−C1a | **+0.030 [+0.017,+0.044]** | 0.0001 | **0.0004** | 518 |
| llama | pp | C3−C2b | **+0.035 [+0.017,+0.055]** | 0.0006 | **0.0012** | 457 |
| llama | ITT | C2a−C0b | **+0.032 [+0.018,+0.049]** | 0.0004 | **0.0012** | 520 |
| llama | ITT | C2b−C0b | **+0.010 [+0.002,+0.019]** | 0.0348 | **0.0348** | 520 |
| llama | ITT | C2a−C1a | **+0.030 [+0.017,+0.044]** | 0.0001 | **0.0004** | 520 |
| llama | ITT | C3−C2b | **+0.024 [+0.010,+0.038]** | 0.0014 | **0.0028** | 520 |
| nemotron | pp | C2a−C0b | +0.003 [−0.029,+0.028] | 0.8625 | 1 | 494 |
| nemotron | pp | C2b−C0b | +0.004 [−0.015,+0.019] | 0.6685 | 1 | 479 |
| nemotron | pp | C2a−C1a | −0.002 [−0.022,+0.023] | 0.8659 | 1 | 481 |
| nemotron | pp | C3−C2b | +0.003 [−0.019,+0.026] | 0.7625 | 1 | 505 |
| nemotron | ITT | C2a−C0b | +0.002 [−0.027,+0.027] | 0.8591 | 1 | 520 |
| nemotron | ITT | C2b−C0b | +0.003 [−0.022,+0.027] | 0.7788 | 1 | 520 |
| nemotron | ITT | C2a−C1a | −0.008 [−0.032,+0.016] | 0.4819 | 1 | 520 |
| nemotron | ITT | C3−C2b | −0.002 [−0.025,+0.020] | 0.8416 | 1 | 520 |

Real-series claim rule: a contrast is "supported" only if it holds under **both** pp and ITT.
llama: C2a−C0b, C2a−C1a, C3−C2b hold under both; C2b−C0b is pp-null (ITT-only positive) →
does **not** satisfy the both-rule. nemotron: all four contrasts null under both.

## 9. Same contrasts under the REGISTERED formula (|D| > 0 cells only) — supplementary disclosure

From `s_scores_conditional.json`; same machinery; clearly unregistered sensitivity (§5).

**Levels (pooled, WITH_pilot, STRICT, Stale@5 — higher = worse)**

| model | analysis | C0 | C0b | C1a | C2a | C2b | C3 |
|---|---|---|---|---|---|---|---|
| llama | pp | 0.044 [0.000,0.089] | 0.044 [0.000,0.089] | 0.066 [0.000,0.146] | **0.338 [0.192,0.489]** | 0.029 [0.000,0.065] | **0.351 [0.177,0.518]** |
| llama | ITT | 0.044 [0.000,0.089] | 0.044 [0.000,0.089] | 0.066 [0.000,0.146] | **0.338 [0.192,0.489]** | 0.132 [0.021,0.235] | **0.351 [0.177,0.518]** |
| nemotron | pp | 0.274 [0.144,0.409] | 0.292 [0.111,0.531] | 0.396 [0.242,0.567] | 0.364 [0.208,0.524] | 0.312 [0.172,0.483] | 0.351 [0.177,0.518] |
| nemotron | ITT | 0.325 [0.188,0.468] | 0.342 [0.143,0.587] | 0.439 [0.286,0.602] | 0.364 [0.208,0.524] | 0.373 [0.225,0.531] | 0.351 [0.177,0.518] |

n: 57 cells where |D| > 0 (pp reduces to 51–57 where a response is unusable).

**Contrasts (same cells; Stale@5 — higher = worse)**

| model | analysis | C2a−C0b | C2b−C0b | C2a−C1a | C3−C2b |
|---|---|---|---|---|---|
| llama | pp | **+0.294 [+0.165,+0.441] H=0.0009** | −0.005 [−0.014,+0.000] H=0.3954 | **+0.272 [+0.156,+0.417] H=0.0009** | **+0.314 [+0.156,+0.484] H=0.0008** |
| llama | ITT | **+0.294 [+0.165,+0.441] H=0.0012** | **+0.088 [+0.021,+0.156] H=0.0142** | **+0.272 [+0.156,+0.417] H=0.0012** | **+0.219 [+0.091,+0.368] H=0.0072** |
| nemotron | pp | +0.024 [−0.280,+0.234] H=1 | +0.036 [−0.137,+0.216] H=1 | −0.019 [−0.219,+0.180] H=1 | +0.034 [−0.186,+0.239] H=1 |
| nemotron | ITT | +0.022 [−0.255,+0.224] H=1 | +0.031 [−0.203,+0.247] H=1 | −0.075 [−0.294,+0.131] H=1 | −0.022 [−0.232,+0.172] H=1 |

Same signs and Holm verdicts as §8; magnitudes ~9.1× larger (dilution factor §5).

## 10. Per-set Stale@5 (pp, STRICT, as scored 0-convention; higher = worse)

Means over all usable cells of the set; empty cells are vacuous 0 where |D| = 0. Columns in
run order. Per-set Violation/Shift and per-set contrasts: `eval/results/figures/*.csv`.

| cond | W1 | W2 | W3 | H1 | D1 | D2 | WET1 | WET2 | O1 | O2 | C1 | N1 | NE15 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **llama** |
| C0 | .013 | .013 | .013 | .013 | .000 | .000 | .000 | .000 | .000 | .000 | .013 | .000 | .000 |
| C0b | .013 | .013 | .013 | .013 | .000 | .000 | .000 | .000 | .000 | .000 | .013 | .000 | .000 |
| C1a | .019 | .025 | .013 | .013 | .000 | .000 | .000 | .000 | .000 | .000 | .025 | .000 | .000 |
| C2a | .019 | .013 | .019 | .019 | .000 | .000 | .175 | .200 | .000 | .000 | .013 | .000 | .025 |
| C2b | .007 | .013 | .007 | .000 | .000 | .000 | .000 | .000 | .000 | .000 | .014 | .000 | .000 |
| C3 | .025 | .025 | .025 | .025 | .000 | .000 | .175 | .175 | .000 | .000 | .025 | .000 | .025 |
| **nemotron** |
| C0 | .013 | .013 | .013 | .013 | .000 | .000 | .154 | .154 | .000 | .000 | .013 | .000 | .000 |
| C0b | .013 | .013 | .013 | .013 | .000 | .000 | .158 | .158 | .000 | .026 | .013 | .000 | .000 |
| C1a | .007 | .007 | .013 | .000 | .000 | .000 | .306 | .184 | .026 | .000 | .000 | .000 | .025 |
| C2a | .019 | .019 | .019 | .019 | .000 | .000 | .200 | .200 | .000 | .000 | .019 | .000 | .025 |
| C2b | .007 | .025 | .007 | .007 | .000 | .000 | .216 | .158 | .000 | .000 | .013 | .000 | .000 |
| C3 | .025 | .025 | .025 | .025 | .000 | .000 | .175 | .175 | .000 | .000 | .025 | .000 | .025 |

Per-set conditional view (|D| > 0 cells only) for the signal sets, e.g. llama WET1 C2a = 0.333
vs C0b = 0.000 (n = 21); nemotron WET1 C2a = 0.381 vs C0b = 0.316 (n = 21/19);
llama/nemotron NE15 C2a = 0.500 vs C0b = 0.000 (n = 2) — full table in
`s_scores_conditional.json → levels`.

## 11. D1/D2 pre-specified LENIENT companion (§8.33.3)

**As scored (0-convention; Stale@5 higher = worse):** D1/D2 strict have |D| = 0 everywhere, so these are lenient-mode
Stale@5 over all 40 cells per set.

| model | set | analysis | C0b | C1a | C2a | C2b | C2a−C0b [CI] | Holm | n |
|---|---|---|---|---|---|---|---|---|---|
| llama | D1 | pp | .075 | .075 | .025 | .041 | −0.050 [−0.125,+0.000] | 0.4588 | 40 |
| llama | D1 | ITT | .075 | .075 | .025 | .062 | −0.050 [−0.125,+0.000] | 0.3441 | 40 |
| llama | D2 | pp | .075 | .113 | .025 | .029 | −0.050 [−0.125,+0.000] | 0.3441 | 40 |
| llama | D2 | ITT | .075 | .113 | .025 | .050 | −0.050 [−0.125,+0.000] | 0.3441 | 40 |
| nemotron | D1 | pp | .026 | .000 | .025 | .013 | +0.000 [−0.043,+0.034] | 1 | 38 |
| nemotron | D1 | ITT | .050 | .075 | .025 | .013 | −0.025 [−0.088,+0.024] | 0.9258 | 40 |
| nemotron | D2 | pp | .026 | .000 | .025 | .000 | +0.000 [−0.043,+0.034] | 1 | 38 |
| nemotron | D2 | ITT | .050 | .025 | .025 | .000 | −0.025 [−0.088,+0.024] | 1 | 40 |

**Conditional (|D| > 0, lenient signal 10/11 cells):** llama C2a−C0b = −0.200
[−0.364,+0.000] Holm 0.1284 (D1) and −0.182 [−0.333,+0.000] Holm 0.1092 (D2), pp = ITT;
nemotron +0.000 Holm 1 (pp) / −0.100 Holm 0.8476 (ITT) D1, +0.000/−0.091 Holm 1 (D2).
No D1/D2 contrast reaches 0.05 under either convention.

## 12. Pilot axis (WITHOUT_pilot = 32 sids)

Stale@5 contrasts, pooled, STRICT, pp (higher = worse):

| model | contrast | as scored (0-conv) | conditional (|D|>0) |
|---|---|---|---|
| llama | C2a−C0b | +0.031 [+0.015,+0.051] H=0.006 n=415 | +0.250 [+0.121,+0.397] H=0.0054 n=51 |
| llama | C2b−C0b | −0.001 [−0.002,+0.000] H=0.4089 n=369 | −0.006 [−0.016,+0.000] H=0.3972 n=45 |
| llama | C2a−C1a | +0.028 [+0.014,+0.043] H=0.0028 n=415 | +0.225 [+0.115,+0.364] H=0.0058 n=51 |
| llama | C3−C2b | +0.038 [+0.018,+0.062] H=0.006 n=369 | +0.311 [+0.151,+0.476] H=0.0004 n=45 |
| nemotron | C2a−C0b | +0.003 [−0.038,+0.034] H=1 n=390 | +0.027 [−0.318,+0.266] H=1 n=47 |
| nemotron | C2b−C0b | +0.005 [−0.019,+0.024] H=1 n=379 | +0.042 [−0.152,+0.256] H=1 n=42 |
| nemotron | C2a−C1a | −0.005 [−0.029,+0.025] H=1 n=391 | −0.043 [−0.266,+0.179] H=1 n=47 |
| nemotron | C3−C2b | +0.009 [−0.016,+0.035] H=1 n=405 | +0.082 [−0.150,+0.295] H=1 n=46 |

WITH_pilot (headline) is §8/§9; conclusions do not hinge on the 8 pilot sids.

## 13. Season strata (pooled cells, STRICT, Stale@5, pp; higher = worse)

**As scored:** llama Kharif C0b/C1a/C2a/C2b/C3 = .000/.000/.065/.000/.053; Rabi
.012/.018/.016/.008/.024; Zaid .000/.000/.035/.000/.042.
nemotron Kharif .045/.071/.065/.024/.053; Rabi .012/.005/.018/.011/.024; Zaid
.046/.065/.042/.072/.042.

**Conditional:** llama Kharif .000/.000/.440/.000/.360; Rabi .250/.375/.325/.214/.500;
Zaid .000/.000/.227/.000/.273. nemotron Kharif .304/.458/.440/.160/.360; Rabi
.250/.125/.375/.281/.500; Zaid .300/.429/.273/.526/.273.

## 14. Controls

### 14.1 N0 identity control (registered: Shift@5 = 0)
All pass: evidence identity vs archive (40/40, all six tools), oracle D = ∅ (strict and
lenient, 80 cells), max Shift@5 = 0.0, N0 Stale = base Stale = 0. Harness valid.

### 14.2 N1 cooling control (registered: "must reverse warm/dry-arm direction" — INCONCLUSIVE, disclosed)
N1 oracle signal = 0/0 in both modes (as designed, cooling-only). The §8.32.5 wording does
not define an operational test for a temperature-only arm, so the scoring-time
operationalization (signed change of the blocked-crop share in top-5 vs base; heat uses the
STRICT heat-block set, drought the LENIENT drought-block set) was applied with the coded rule
`n1 > pool-mean`:

| model | component | N1 Δ | pool mean | coded rule |
|---|---|---|---|---|
| llama | heat_cited (vs warm pool W1/W2/W3/H1/C1) | +0.045 | −0.008 | PASS (reversed) |
| llama | drought_lenient (vs dry pool D1/D2) | −0.019 | +0.006 | FAIL |
| nemotron | heat_cited | +0.025 | −0.008 | PASS |
| nemotron | drought_lenient | −0.030 | +0.000 | FAIL |

Under the equally plausible "opposite sign to the pool's own movement" reading, both
components reverse for both models (N1 negative where the dry pool is ≥ 0). Because §8.32.5
is underspecified here, this control is reported **inconclusive with all numbers shown**; it
is not used to gate any other result. (Also: D1/D2 strict pools have no oracle movement at
all, so a "dry-arm direction" to reverse does not exist at strict.)

### 14.3 Movement not explained by hard-constraint changes (advice moved while the oracle did not; P(Shift > 0 | |D| = 0))

(Display rename of the metric previously labelled "false-change"; the machine key
`s_scores.json → false_change` and figure filename `false_change.*` are unchanged.)

| model | C0 | C0b | C1a | C2a | C2b | C3 |
|---|---|---|---|---|---|---|
| llama | 0/463 = .000 | 0/463 = .000 | 154/463 = .333 | 207/435 = .476 | 231/369 = .626 | 168/463 = .363 |
| nemotron | 0/454 = .000 | 0/441 = .000 | 292/396 = .737 | 173/463 = .374 | 313/446 = .702 | 168/463 = .363 |

C0/C0b = 0 **by construction** (reused responses cannot change). Every tool condition — and
C3, the deterministic scorer — changes its top-5 on a large fraction of cells where no
constraint flag moved. (Per-set values: `s_scores.json → false_change`, figure
`false_change.png/csv`.)

### 14.4 Tool-output overlap (echo of `crop_score` top-5; mean share of advice ⊆ crop_score top-5)

| model | C1a | C2a | C2b |
|---|---|---|---|
| llama | 0.153 (n=520) | **0.992** (n=444) | 0.201 (n=288) |
| nemotron | 0.468 (n=481) | **1.000** (n=520) | 0.385 (n=505) |

C2a advice is essentially the crop_score top-5; C2b (crop_score removed) overlaps far less —
the tool's presence, not generic tool access, drives the echo.

---

## 15. What moved and what did not (factual summary; no paper claims)

1. **Advice movement (Shift@5):** tool conditions move advice substantially (llama pp C1a
   0.132 / C2a 0.273 / C2b 0.511 / C3 0.139; nemotron 0.427 / 0.139 / 0.355 / 0.139), no-tool
   conditions not at all (0.000 — by construction, they are reused responses).
2. **Registered Stale@5 contrasts:** llama shows 3/4 contrasts significant under both pp and
   ITT (C2a−C0b, C2a−C1a, C3−C2b; C2b−C0b ITT-only, fails the both-rule); direction is
   positive — llama C2a/C3 advice **retains more** of the newly-infeasible crops than the
   baselines on the pooled 0-convention metric. nemotron: no contrast significant.
3. **Under the registered (conditional) metric:** llama retains ~34–35 % of the newly-
   infeasible set under C2a/C3 vs ~3–6 % under C0/C0b/C1a/C2b (C2b ITT 13 %); nemotron
   retains 27–44 % under every condition with no separation. Same verdicts as (2).
4. **Violation@5:** both models' tool conditions — especially C2a and C3 — have much lower
   infeasible-advice shares than the no-tool baselines (llama C0 0.659 → C2a 0.128 → C3
   0.092; nemotron C0 0.367 → C2a 0.153 → C3 0.092), consistent in pp and ITT.
5. **Movement not explained by hard-constraint changes:** tools (and C3) rewrite advice on 33–74 % of oracle-unmoved cells; C3
   itself moves on 36 % of them.
6. **Controls:** N0 passes completely; N1 direction control is inconclusive (§14.2).

## 16. Deviations from, and operationalizations of, the registration (all disclosed)

1. **pp/ITT wording.** §8.32.5 says "(40 pilot_dev rows excluded / included)" as a gloss on
   pp/ITT; the operative instruction is "as in the real series", where pp/ITT is the
   unusable-response exclusion / worst-case (PROTOCOL L495–500, `real_eval.py`), and pilot
   membership is a separate WITH/WITHOUT axis. Implemented that way; pilot reported both ways
   (§12). No metric changed.
2. **Presence vs usability in coverage checks.** The registered coverage idea is record
   presence; the checks were reframed as presence (PASS 3 120/3 120) plus a separately
   reported usability census (119 unusable, §2) instead of failing on unusable model output.
3. **Stale@5 at |D| = 0.** Scorer returns 0 (its docstring overclaims registration);
   both conventions reported (§5, §9); docstring left as-run for provenance (bug B9).
4. **Chain-of-custody climate hash.** Climate month dicts hash differently with int vs str
   keys (runtime serves int keys; JSON round-trip yields str keys, flipping `sort_keys`
   order). The check accepts either canonical form (dual hash); value differences still fail.
   Result 11 660/11 660 — no genuine value mismatch was hidden (a value difference cannot
   match in either form).
5. **Nemotron C0/C0b baseline enrichment.** Unusable cached canonical records replaced at
   scoring time by the first usable copy of the same cell in the on-disk canonical runs
   (`enrich_baseline`; no model call, deterministic, function-docstring documented). Three
   cells have no usable record anywhere (§6) and are pp-excluded/ITT-worst-cased.
6. **Metric-aware cell usability.** Shift@5 needs the condition's canonical baseline;
   missing baselines exclude the cell from shift only (`usable_shift`). Stale/Violation/
   Drop/contrast cells need only the response.
7. **C3 instrument.** The registered C3 is `run_deterministic_v2.py::score_crops` full_repo
   (PROTOCOL / S_PLAN_V2 line 13: "C3 from archive_v2/deterministic"), but the run bundles
   recorded the MCP `crop_score` tool output, which disagrees for **17/40** base scenarios.
   Scoring recomputes C3 from the registered pipeline (`s_c3_recompute.py`; base gate 40/40
   vs the frozen archive; 560 cells incl. N0). Bundle crop_score is still used for C2a chain
   of custody + overlap. Report deviates from neither: it follows the registration; the
   bundle disagreement is logged (bug B6).
8. **Prompt-hash separators.** S runs hash with `\x1f` (`run_s_series.py`), canonical runs
   with `\u241f` (`run_model.py`/`verify_reuse.py`). Both verified (3 120/3 120 and 160/160).
   Records from the two NFC runs carry `prompt_hash: ""` for some cells — treated as
   "unverifiable", not mismatch (the invariance check, which hashes the ORIGINAL records,
   reported 160 match / 0 mismatch / 0 unverifiable).
9. **N1 direction test** is a scoring-time operationalization of an underspecified
   control (§14.2), reported inconclusive.
10. **N0 is evidence-only.** N0 was never LLM-run (identity control by construction); it is
    scored from bundles/oracle only and excluded from run-cell tables.
11. **Pooled LENIENT not tabulated here (gap found 2026-10-19, disclosed in S_FOLLOWUP).**
    The scorer computed pooled lenient-mode levels/contrasts (registered secondary oracle
    mode, §8.32.3), but this report tabulates pooled STRICT only (lenient appears solely as
    the pre-specified D1/D2 companion, §11). Full pooled-lenient tables and their one
    different verdict (nemotron C3−C2b holds the both-rule under lenient; strict primary
    unchanged) are disclosed in `S_FOLLOWUP.md` §4.5.


**Cross-reference (PROTOCOL 8.35 instrument correction):** The registered C3 arm used in S-series Stale@5/Violation@5 tables differs from the actual MCP crop_score tool. The corrected instrument C3t (identical pipeline with real sowing windows) reproduces the tool 10,000/10,000. The 45 strict WET candidates (14 C3 + 31 C2a, all Urad/flood-cited) are re-evaluated under C3t. See eval/reports/CORRECTION_NOTE.md.

## 17. Bug log (S series; date found → date fixed)

| # | Found | Fixed | Bug | Impact |
|---|---|---|---|---|
| B1 | 2026-10-16 | 2026-10-16 | `run_s_series.py` heartbeat thread zombied after set completion (printed stale 120/120 for hours) | log-only; fixed before remaining sets |
| B2 | 2026-10-16 | 2026-10-16 | nemotron 404 provider outage (incident NPC-1) — W1/nemotron 99 % failures, budget burned | recovered by retry audit; all 119 re-acquired (§2). TODO: preflight model health check |
| B3 | run phase 2026-10-16/17 | then | D1 retry hang (timeout 600 → 120 s); `s_status.py` f-string TypeError; `s_resume` watcher not crash-proof; budget selftest clobber | run-phase fixes; no result impact |
| B4 | 2026-10-19 | 2026-10-19 | `score_s.py` N0 KeyError (N0 excluded from F) — N0 inserted post-gate into evidence sets | fixed; N0 checks pass |
| B5 | 2026-10-19 | 2026-10-19 | `score_s.py` c0 invariance used S-run separator (`\x1f`) against canonical hashes (`\u241f`) → false fail | fixed via `prompt_key(sep=…)`; 160/160 match |
| B6 | 2026-10-19 | 2026-10-19 | **C3 instrument mismatch**: bundle crop_score ≠ registered det pipeline for 17/40 base scenarios (registered N0 Shift@5 = 0 control failed when used as C3: max 0.75) | fixed by `s_c3_recompute.py` (registered pipeline, base gate 40/40); no model call, no frozen file changed (§16.7) |
| B7 | 2026-10-19 | 2026-10-19 | chain-of-custody climate "mismatch" 2 107/2 107 false positives from int-vs-str key hashing (§16.4) | dual-hash check; 11 660/11 660 PASS |
| B8 | 2026-10-19 | 2026-10-19 | `score_s.py` `t0 = …` name shadowed the metric loop's `t0` → `TypeError: datetime - list` at `duration_s` | fixed (renamed `base_t`); final run completes |
| B9 | 2026-10-19 | disclosed | `stale_at5` docstring claims "\|D\|=0 → 0 (registered convention)" — not registered (§5) | docstring left as-run for provenance; both conventions reported |
| B10 | 2026-10-19 | disclosed | coverage checks conflated record presence with response usability | reframed as presence + usability census (§16.2) |

## 18. Limitations (plain words)

- **The oracle barely moves in most arms.** Only 57 of 520 cells (strict) have any
  newly-infeasible crop; D1/D2 have none at strict (their analysis is lenient by design).
  Most headline means are diluted by vacuous zeros (§5); signal-conditional numbers rest on
  as few as 57 cells, and per-set conditional cells run as low as n = 1–2 (O1, W1…). Wide
  CIs in §9 reflect this.
- **C0/C0b are reused, not re-run.** Their Shift = 0, §14.3 movement rate = 0 and "didn't change
  advice" readings are true by construction, not observed behavior under perturbation. The
  registered design accepts this (§8.33.4); the claim's no-tool side is therefore
  structural, and Drop@|D| = 0 is vacuous (= 1) by construction for every condition.
- **119 unusable cells** (5 %) are non-random: mostly llama C2b (63/520 cells unusable, pp n = 457)
  and nemotron C1a. pp and ITT both reported; a claim would need both.
- **Nemotron baselines were partly repaired offline** (§16.5); three cells could not be
  repaired and are pp-excluded.
- **The N1 direction control is underspecified** and reported inconclusive (§14.2).
- **Overlap ≠ causation:** C2a echoes crop_score (0.99–1.00) by design; contrasts involving
  C2a measure the bundled-tool path as a whole.
- **One scorer, one bootstrap seed** (42), one Holm family definition — all as registered.
- **Figures:** all five written without error; CSVs cross-checked against `s_scores.json`
  values; `contrasts_forest.png` was visually inspected during SCORING 5, the other PNGs were
  not pixel-inspected (agent has no image input in this session).

## 19. Provenance — every reported number → its source

| Number(s) | Source |
|---|---|
| §3 checks 1–20 | `s_sanity.json` (written by `score_s.py`) |
| §2 coverage/retry | `s_sanity.json → run_records_present`; `s_retry_audit.json` |
| §4 signal counts | `s_scores.json → signal`; matches §8.33.4a pre-run audit |
| §7 levels (all metrics) | `s_scores.json → levels` (keys `model\|WITH_pilot\|analysis\|scope\|mode\|cond\|metric`) |
| §8 contrasts + Holm | `s_scores.json → contrasts` |
| §9 conditional | `s_scores_conditional.json` (from `s_score_conditional_supp.py`, source = `s_scores_cells.csv`) |
| §10 per-set | `s_scores.json → levels[scope=set]`; conditional per-set → `s_scores_conditional.json` |
| §11 D1/D2 | `s_scores.json` + `s_scores_conditional.json` (lenient) |
| §12 WITHOUT_pilot | same two files, subset `WITHOUT_pilot` |
| §13 seasons | `levels[season:*]` in both files |
| §14.1 N0 | `s_sanity.json → n0_*` checks; `s_scores.json → false_change` N0 rows |
| §14.2 N1 | `s_scores.json → n1_direction` |
| §14.3 movement-not-explained (display rename) | `s_scores.json → false_change` (figure `false_change.*`) |
| §14.4 overlap | `s_scores.json → tool_overlap` |
| §15 synthesis | arithmetic over §7–§14 (no new computation) |
| C3 instrument | `s_c3_full_repo.json` (`s_c3_recompute.py`), base gate 40/40 |
| Figures | `eval/results/figures/*.pdf/png/csv` (`s_figures.py`, renders `s_scores.json` only) |
| Tests | `eval/tests/test_s_metrics.py` — 11 pass |

## 20. Figures (all in `eval/results/figures/`)

| Figure | Files | Rows (CSV) |
|---|---|---|
| Stale@5 per set × condition | `stale_by_set.{pdf,png,csv}` | 156 |
| Violation@5 per set × condition | `violation_by_set.{pdf,png,csv}` | 156 |
| Shift@5 per set × condition | `shift_by_set.{pdf,png,csv}` | 156 |
| Primary contrasts forest (pp ● / ITT □, Holm labels) | `contrasts_forest.{pdf,png,csv}` | 16 |
| Movement not explained by hard-constraint changes with binomial SE | `false_change.{pdf,png,csv}` | 156 |

Titles carry the configuration: pp, STRICT, WITH_pilot. Secondary metric/CIs for every
scope are in `s_scores.json`; beyond display-level SE bars on the movement-not-explained
figure (§14.3), no
value is computed outside the scorer's outputs.

---

**END OF REPORT — AWAITING USER APPROVAL.** No commit, push, or paper text has been made.
