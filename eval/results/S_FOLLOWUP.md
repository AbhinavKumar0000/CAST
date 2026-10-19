# S_FOLLOWUP — EXPLORATORY follow-up analyses on the S-series (PROTOCOL §8.34)

**Status: EXPLORATORY, offline, awaiting user approval. No commit made.**
Registered before computation: `eval/PROTOCOL.md` §8.34 (2026-10-19 02:44:25 UTC /
08:14:25 +05:30), which pins all eight analyses below. Trigger: user task
"Follow-up analyses on S-series" (2026-10-19).

Ground rules honored:

- **NO model calls.** Everything here is recomputed from frozen on-disk artifacts.
- **Frozen inputs unchanged:** tool schemas, prompts, algorithm, weights, oracle,
  scenarios, perturbations, `crop_log.csv`, `s_scores.json`, `s_scores_cells.csv`
  (registered outputs), and every number in `S_REPORT.md` are untouched.
- New files only for computation; the only edits to existing files are
  **display labels** (item 7 and item 4 qualifiers — §7 below) plus one
  disclosure bullet (S_REPORT §16.11, §4.5 cross-reference).
- **Registered reconstruction gate:** all 12 480 rows of `s_scores_cells.csv`
  re-reconstructed from `s_scores.json` inputs → **PASS, 0 mismatches**
  (float tolerance 1e-6; CSV stores 6 decimals — see bug F1, §11).
- Every result below is reported good or bad (§9 inventory).

Outputs: `s_followup_b6.json`, `s_followup_real_impact.json`,
`s_followup.json`, `s_followup_cases.json`; scripts `s_followup_b6.py`,
`s_followup_real_impact.py`, `s_followup.py`, `s_followup_cases.py`;
figures re-rendered for title/label text only (data unchanged).

Throughout: **pp** = usable responses excluded otherwise; **ITT** = worst case;
primary configuration is WITH_pilot (40 sids) unless stated; metric tables for
Stale@5 and Violation@5 carry **higher = worse**.

---

## 1. Item 1 — B6 root cause, and its impact on the real series

### 1.1 Root cause (single cause, 17/17 verified)

Instruments, per §8.34.1: **A** = stored bundle `crop_score` (frozen MCP tool
output captured at run build), **B** = registered C3 pipeline
(`run_deterministic_v2.py::score_crops`, full_repo), **C** = B but passing the
real sowing windows into `_season_alignment_score`.

| Measurement | Result |
|---|---|
| Instrument gate: B recomputed == frozen archive det output | **40 / 40** |
| A ≠ B mismatches (the 17/40 of bug B6) | 17 / 40 |
| Cause: **season handling** (sowing windows dropped) | **17 / 17** |
| Cause: data version / tie-breaking / rounding / state / other | **0** (each) |
| Variant C == A among the 17 mismatched | **17 / 17** |
| Variant C == B among the 23 matched | **23 / 23** |
| Crop-level score equality C vs A (top-6 pairs of the 17) | **102 / 102** |

Cause of the mismatch, exactly: `run_deterministic_v2.py:201-203` passes
**empty** `sowing_start_week` / `sowing_end_week` into
`_season_alignment_score`, which collapses the season component to
{Annual 0.6 / supports-season 0.75 / not-supported 0.0}, while the MCP tool
uses the real week window {0.85 / 0.25 / 0.6; 1.0 / 0.65 / 0.35}.
Everything else is line-equivalent: weights identical (0.20 rainfall / 0.15
temperature / 0.20 soil / 0.30 season / 0.15 risk), sowing weeks and seasons
identical (bundle is time-anchored to `as_of_date`), `crop_log.csv` unchanged
since the initial commit (verified via `git log`), all other scoring functions
line-equivalent.

Worked example (from `s_followup_b6.json`): S000480, as_of 2024-07-08, week 28,
Kharif — tool top-5 `Sunflower, Arhar (Tur), Sesame (Til), Moong, Urad`;
registered pipeline top-5 `Moong, Sunflower, Soybean, Arhar (Tur), Sesame (Til)`.
Tool scores Sunflower 0.960 with season_alignment 1.0; variant with windows
returns 0.960 (== tool). With empty windows the pipeline's season term for the
same crop differs, reordering the list. This resolves the root-cause half of
bug B6 (S_REPORT §17, §16.7): the registered C3 instrument fix stands (scoring
used the registered pipeline), and the bundle disagreement now has a single,
fully-accounted cause.

Side-by-side top-5s, scores and inputs for all 40 scenarios (17 mismatched
flagged with cause) are in `s_followup_b6.json`.

### 1.2 Impact on the real series (item 1, second half)

`real_eval_scorer_vs_final.py` used the det pipeline (C3) as a **proxy** for the
scorer tool when comparing "what the scorer would rank" against final answers.
Replication gate first (proxy run reproduces the published numbers exactly):

| Published (det proxy) | Replicated | Actual tool ranking |
|---|---|---|
| P@5 all 0.5035 | 0.5035 ✓ | **0.4833** (−0.020) |
| C2a ordered-identical 0.5163 | 0.5163 ✓ | **0.9980** |
| C2a set-identical 0.5813 | 0.5813 ✓ | **0.9980** |
| C2a Jaccard 0.8305 | 0.8305 ✓ | **0.9993** |
| C2a positions-identical 3.3354 | 3.3354 ✓ | **4.9980** |
| C2a P@5 (scorer) 0.5029 | 0.5029 ✓ | **0.4820** |
| C2b ordered / set 0.0000 | 0.0000 ✓ | 0.0000 / 0.0000 |
| C2b Jaccard 0.2718 | 0.2718 ✓ | 0.2582 |
| C2b positions 0.5445 | 0.5445 ✓ | 0.5263 |
| C2b P@5 (scorer) 0.5028 | 0.5028 ✓ | 0.4841 |
| final-answer P@5 (C2a/C2b) 0.4824 / 0.6223 | ✓ | **unchanged** 0.4824 / 0.6223 |

Pairwise overlap with the actual tool rankings: **242 / 500 ordered top-5s
differ (48.4 %), 209 / 500 sets differ.** Reading (good and bad):

- The proxy **massively understated C2a fidelity to the actual scorer tool**:
  ordered-identical was reported as 0.516 but is in fact 0.998 (C2a advice
  follows the real `crop_score` tool almost perfectly; positions 3.34 → 5.00).
  All C2a fidelity claims in the real series get *stronger*, not weaker.
- P@5 of the scorer's own ranking vs ground truth drops 2.0 pp when using the
  tool instead of the det proxy (0.5035 → 0.4833): the det pipeline was a
  slightly *kinder* ranking than the tool it stood in for.
- C2b (which does not build advice on crop_score top-5s) is unaffected in its
  registered ordered/set identities; small Jaccard/positions/P@5 moves are
  recomputed and disclosed above.
- Final-answer metrics are untouched by construction (final lists are the LLM's).

Full data: `s_followup_real_impact.json` (script `s_followup_real_impact.py`).

---

## 2. Item 2 — Exposure-conditioned retention (EXPLORATORY metric)

Definition per §8.34.2: exposure E = |baseline top-5 ∩ D| > 0; retention =
|base_top5 ∩ D ∩ shifted_top5| / |base_top5 ∩ D|, mean over exposed cells,
district-clustered bootstrap (seed 42, n=10 000), pp and ITT (unusable shifted
response but exposed → worst case 1.0; unusable baseline → excluded, exposure
unknown). C0/C0b are exposure-only (reused by design §8.33.4).

### 2.1 Exposure share of baseline top-5s (context; n = exposed / usable baseline cells)

| model | cond | STRICT exposed | share [95 % CI] | LENIENT exposed | share [95 % CI] |
|---|---|---|---|---|---|
| llama | C0 | 10/520 | 0.019 [0.000,0.047] | 13/520 | 0.025 [0.000,0.056] |
| llama | C0b | 10/520 | 0.019 [0.000,0.047] | 36/520 | 0.069 [0.036,0.112] |
| llama | C1a | 10/520 | 0.019 [0.000,0.047] | 42/520 | 0.081 [0.047,0.121] |
| llama | C2a | 30/494 | 0.061 [0.026,0.105] | 65/494 | 0.132 [0.089,0.177] |
| llama | C2b | 10/468 | 0.021 [0.000,0.053] | 27/468 | 0.058 [0.020,0.104] |
| llama | C3 | 26/520 | 0.050 [0.016,0.093] | 66/520 | 0.127 [0.092,0.165] |
| nemotron | C0 | 17/507 | 0.034 [0.015,0.054] | 37/507 | 0.073 [0.040,0.113] |
| nemotron | C0b | 18/494 | 0.036 [0.012,0.070] | 33/494 | 0.067 [0.030,0.117] |
| nemotron | C1a | 20/481 | 0.042 [0.012,0.077] | 54/481 | 0.112 [0.059,0.174] |
| nemotron | C2a | 30/520 | 0.058 [0.024,0.100] | 69/520 | 0.133 [0.091,0.176] |
| nemotron | C2b | 23/507 | 0.045 [0.021,0.081] | 51/507 | 0.101 [0.060,0.147] |
| nemotron | C3 | 26/520 | 0.050 [0.016,0.093] | 66/520 | 0.127 [0.092,0.165] |

C0/C0b rows are baseline exposure (context only, per §8.34.2). Mean |E| among
exposed cells: **strict 1.0–1.8** crops (llama C3 1.77, C2a 1.33; nemotron C1a
1.50, C2b 1.65); lenient up to 2.35 (C3 both models 2.35, llama C2a 2.17,
nemotron C2a 2.13). Exposure is **small** — strict mode exposes 1.9–6.1 % of cells — so
retention CIs below are wide (few exposed cells, k = 2–14 districts).

### 2.2 Retention among exposed cells — STRICT (primary), mean [95 % CI], n = pp / eligible

| cond | llama pp | llama ITT | nemotron pp | nemotron ITT |
|---|---|---|---|---|
| C1a | 1.000 [1.000,1.000] (10) | 1.000 [1.000,1.000] (10) | 0.392 [0.167,0.800] (17/20) | 0.483 [0.236,0.846] (20) |
| C2a | 0.717 [0.478,0.974] (30) | 0.717 [0.478,0.974] (30) | 0.783 [0.580,1.000] (30) | 0.783 [0.580,1.000] (30) |
| C2b | 0.857 [0.750,1.000] (7/10) | 0.900 [0.800,1.000] (10) | 0.536 [0.324,0.867] (21/23) | 0.576 [0.356,0.889] (23) |
| C3 | 0.795 [0.683,1.000] (26) | 0.795 [0.683,1.000] (26) | 0.795 [0.683,1.000] (26) | 0.795 [0.683,1.000] (26) |

### 2.3 Retention — LENIENT (secondary mode), same definitions

| cond | llama pp | llama ITT | nemotron pp | nemotron ITT |
|---|---|---|---|---|
| C1a | 0.881 [0.700,1.000] (42) | 0.881 [0.700,1.000] (42) | 0.465 [0.297,0.692] (48/54) | 0.525 [0.321,0.750] (54) |
| C2a | 0.810 [0.687,0.920] (65) | 0.810 [0.687,0.920] (65) | 0.855 [0.771,0.935] (69) | 0.855 [0.771,0.935] (69) |
| C2b | 0.646 [0.348,0.926] (24/27) | 0.685 [0.362,0.939] (27) | 0.328 [0.191,0.478] (49/51) | 0.355 [0.218,0.504] (51) |
| C3 | 0.813 [0.717,0.909] (66) | 0.813 [0.717,0.909] (66) | 0.813 [0.717,0.909] (66) | 0.813 [0.717,0.909] (66) |

Facts (reported as found): **nemotron retains markedly less than llama at C1a**
(strict 0.39/0.48 vs 1.00; lenient 0.47/0.53 vs 0.88) **and at C2b**
(lenient 0.33/0.35 vs 0.65/0.69); llama C2a is the lowest llama entry
(0.717); C3 is identical across models (deterministic scorer) at 0.795/0.813;
C2a is similar between models (0.72–0.86). All entries and CIs:
`s_followup.json → retention`.

---

## 3. Item 3 — Delta-violation (Violation@5 shift − Violation@5 condition baseline)

Per §8.34.3: pooled WITH_pilot, pp + ITT, strict + lenient, over (a) signal
cells |D| > 0 and (b) all cells. **Higher = worse** (negative Δ = shifted advice
violates fewer hard constraints than the condition's own baseline advice).
C0/C0b Δ = 0 by construction (reused responses) — noted, not tested.

Cell format: mean [95 % CI]; **†** p < 0.05, **‡** p < 0.10 (exact p listed
under the table); unmarked p ≥ 0.10.

### 3.1 STRICT

| model | cond | scope | pp | ITT |
|---|---|---|---|---|
| llama | C1a | signal | **−0.032 [−0.064,−0.004]†** | **−0.032 [−0.064,−0.004]†** |
| llama | C1a | all | **−0.022 [−0.038,−0.010]†** | **−0.022 [−0.038,−0.010]†** |
| llama | C2a | signal | −0.049 [−0.104,+0.000]‡ | −0.049 [−0.104,+0.000]‡ |
| llama | C2a | all | **−0.028 [−0.057,−0.004]†** | −0.072 [−0.174,−0.004]‡ |
| llama | C2b | signal | +0.097 [−0.100,+0.281] | +0.124 [−0.064,+0.314] |
| llama | C2b | all | +0.053 [−0.072,+0.151] | +0.048 [−0.064,+0.152] |
| llama | C3 | signal | −0.025 [−0.066,+0.022] | −0.025 [−0.066,+0.022] |
| llama | C3 | all | +0.001 [−0.005,+0.005] | +0.001 [−0.005,+0.005] |
| nemotron | C1a | signal | +0.008 [−0.041,+0.053] | +0.039 [−0.019,+0.091] |
| nemotron | C1a | all | +0.028 [−0.018,+0.075] | +0.020 [−0.067,+0.102] |
| nemotron | C2a | signal | −0.032 [−0.073,+0.004] | −0.032 [−0.073,+0.004] |
| nemotron | C2a | all | −0.005 [−0.018,+0.006] | −0.005 [−0.018,+0.006] |
| nemotron | C2b | signal | −0.008 [−0.078,+0.079] | +0.000 [−0.063,+0.086] |
| nemotron | C2b | all | −0.002 [−0.045,+0.049] | +0.003 [−0.039,+0.053] |
| nemotron | C3 | signal | −0.025 [−0.066,+0.022] | −0.025 [−0.066,+0.022] |
| nemotron | C3 | all | +0.001 [−0.005,+0.005] | +0.001 [−0.005,+0.005] |

p values of marked cells: llama C1a signal p=0.0377, all p=0.0048; llama C2a
signal p=0.0622, all pp p=0.0413, all ITT p=0.0876. (n: signal 57 — except
pp ll/nem C2b 50/49, nem C1a 53; all cells: ll C1a/C3 520, ll C2a 492/520,
ll C2b 419/520, nem C1a 449/520, nem C2a 520, nem C2b 495/520, nem C3 520.)

### 3.2 LENIENT

| model | cond | scope | pp | ITT |
|---|---|---|---|---|
| llama | C1a | signal | −0.012 [−0.036,+0.010] | −0.012 [−0.036,+0.010] |
| llama | C1a | all | **−0.016 [−0.031,−0.004]†** | **−0.016 [−0.031,−0.004]†** |
| llama | C2a | signal | −0.034 [−0.080,+0.006] | −0.040 [−0.097,+0.014] |
| llama | C2a | all | **−0.029 [−0.055,−0.007]†** | −0.073 [−0.174,−0.006]‡ |
| llama | C2b | signal | +0.059 [−0.103,+0.214] | +0.080 [−0.071,+0.234] |
| llama | C2b | all | +0.051 [−0.074,+0.149] | +0.045 [−0.068,+0.152] |
| llama | C3 | signal | −0.021 [−0.047,+0.005] | −0.021 [−0.047,+0.005] |
| llama | C3 | all | −0.000 [−0.009,+0.008] | −0.000 [−0.009,+0.008] |
| nemotron | C1a | signal | +0.038 [−0.057,+0.143] | +0.054 [−0.032,+0.127] |
| nemotron | C1a | all | +0.017 [−0.023,+0.062] | +0.011 [−0.062,+0.081] |
| nemotron | C2a | signal | −0.006 [−0.022,+0.013] | −0.006 [−0.022,+0.013] |
| nemotron | C2a | all | −0.002 [−0.012,+0.007] | −0.002 [−0.012,+0.007] |
| nemotron | C2b | signal | **−0.077 [−0.132,−0.021]†** | **−0.071 [−0.119,−0.022]†** |
| nemotron | C2b | all | −0.013 [−0.049,+0.030] | −0.007 [−0.046,+0.036] |
| nemotron | C3 | signal | −0.021 [−0.047,+0.005] | −0.021 [−0.047,+0.005] |
| nemotron | C3 | all | −0.000 [−0.009,+0.008] | −0.000 [−0.009,+0.008] |

p of marked cells: ll C1a all 0.0251; ll C2a all pp 0.0195 / ITT 0.0781;
nem C2b signal pp 0.0067 / ITT 0.0039. Signal n = 104 (pp ll C2a 101, ll C2b
92, nem C1a 89, nem C2b 96); all-cell n as in §3.1.

Reading (honest): **no condition significantly increases Violation@5 under
shift anywhere** (the largest positive, llama C2b signal +0.097/+0.124, is
noise). Several entries *decrease* (llama C1a, llama C2a; nemotron lenient
C2b signal −0.077, significant pp **and** ITT). ITT inflates magnitudes where
unusable cells sit (llama C2a all: −0.028 pp → −0.072 ITT); note the
construction mix — llama C2a all ITT CI excludes 0 while p = 0.0876 (percentile
CI vs bootstrap two-sided p; both reported as computed, no cell removed).
Full grids (all p, k, n): `s_followup.json → delta_violation`.

---

## 4. Item 4 — Headline swap (conditional PRIMARY, 0-filled SENSITIVITY) + "higher = worse"

S_REPORT §7–§8 remain the **registered as-scored (0-filled)** presentation —
untouched. Here the Stale@5 tables are presented with the |D|>0 conditional
version (S_REPORT §5/§9) as **PRIMARY** and the 0-filled version as
**SENSITIVITY**; every Stale@5 and Violation@5 table carries **higher = worse**.
Convention facts: |D| = 0 cells dilute the 0-filled numbers by ×9.12 (strict;
S_REPORT §5); signal cells: 57 strict / 104 lenient.

### 4.1 PRIMARY — Stale@5 conditional (|D| > 0), pooled, WITH_pilot, STRICT (higher = worse)

Levels, mean [95 % CI]:

| model | analysis | C0 | C0b | C1a | C2a | C2b | C3 |
|---|---|---|---|---|---|---|---|
| llama | pp | 0.044 [0.000,0.089] | 0.044 [0.000,0.089] | 0.066 [0.000,0.146] | **0.338 [0.192,0.489]** | 0.029 [0.000,0.065] | **0.351 [0.177,0.518]** |
| llama | ITT | 0.044 [0.000,0.089] | 0.044 [0.000,0.089] | 0.066 [0.000,0.146] | **0.338 [0.192,0.489]** | 0.132 [0.021,0.235] | **0.351 [0.177,0.518]** |
| nemotron | pp | 0.274 [0.144,0.409] | 0.292 [0.111,0.531] | 0.396 [0.242,0.567] | 0.364 [0.208,0.524] | 0.312 [0.172,0.483] | 0.351 [0.177,0.518] |
| nemotron | ITT | 0.325 [0.188,0.468] | 0.342 [0.143,0.587] | 0.439 [0.286,0.602] | 0.364 [0.208,0.524] | 0.373 [0.225,0.531] | 0.351 [0.177,0.518] |

Contrasts, Δ [95 % CI] Holm-p (n = 48–57 usable signal cells):

| model | analysis | C2a−C0b | C2b−C0b | C2a−C1a | C3−C2b |
|---|---|---|---|---|---|
| llama | pp | **+0.294 [+0.165,+0.441] H=0.0009** | −0.005 [−0.014,+0.000] H=0.3954 | **+0.272 [+0.156,+0.417] H=0.0009** | **+0.314 [+0.156,+0.484] H=0.0008** |
| llama | ITT | **+0.294 [+0.165,+0.441] H=0.0012** | **+0.088 [+0.021,+0.156] H=0.0142** | **+0.272 [+0.156,+0.417] H=0.0012** | **+0.219 [+0.091,+0.368] H=0.0072** |
| nemotron | pp | +0.024 [−0.280,+0.234] H=1 | +0.036 [−0.137,+0.216] H=1 | −0.019 [−0.219,+0.180] H=1 | +0.034 [−0.186,+0.239] H=1 |
| nemotron | ITT | +0.022 [−0.255,+0.224] H=1 | +0.031 [−0.203,+0.247] H=1 | −0.075 [−0.294,+0.131] H=1 | −0.022 [−0.232,+0.172] H=1 |

**Verdicts unchanged under the swap:** llama C2a−C0b, C2a−C1a, C3−C2b hold
both pp and ITT; C2b−C0b remains pp-null / ITT-only → fails the both-rule;
nemotron strict all-null. Magnitudes ~9.1× the as-scored values.

### 4.2 SENSITIVITY — Stale@5 as-scored (0-filled), pooled, WITH_pilot, STRICT (higher = worse)

Levels:

| model | analysis | C0 | C0b | C1a | C2a | C2b | C3 |
|---|---|---|---|---|---|---|---|
| llama | pp | 0.005 [0.000,0.012] | 0.005 [0.000,0.012] | 0.007 [0.000,0.019] | 0.037 [0.019,0.059] | 0.003 [0.000,0.008] | 0.038 [0.018,0.062] |
| llama | ITT | 0.005 [0.000,0.012] | 0.005 [0.000,0.012] | 0.007 [0.000,0.019] | 0.037 [0.019,0.059] | 0.014 [0.002,0.030] | 0.038 [0.018,0.062] |
| nemotron | pp | 0.029 [0.014,0.045] | 0.031 [0.011,0.059] | 0.044 [0.028,0.059] | 0.040 [0.021,0.063] | 0.032 [0.017,0.050] | 0.038 [0.018,0.062] |
| nemotron | ITT | 0.036 [0.018,0.055] | 0.037 [0.015,0.066] | 0.048 [0.030,0.067] | 0.040 [0.021,0.063] | 0.041 [0.023,0.059] | 0.038 [0.018,0.062] |

Contrasts:

| model | analysis | C2a−C0b | C2b−C0b | C2a−C1a | C3−C2b |
|---|---|---|---|---|---|
| llama | pp | **+0.032 [+0.018,+0.050] H=0.0012** | −0.001 [−0.002,+0.000] H=0.4527 | **+0.030 [+0.017,+0.044] H=0.0004** | **+0.035 [+0.017,+0.055] H=0.0012** |
| llama | ITT | **+0.032 [+0.018,+0.049] H=0.0012** | **+0.010 [+0.002,+0.019] H=0.0348** | **+0.030 [+0.017,+0.044] H=0.0004** | **+0.024 [+0.010,+0.038] H=0.0028** |
| nemotron | pp | +0.003 [−0.029,+0.028] H=1 | +0.004 [−0.015,+0.019] H=1 | −0.002 [−0.022,+0.023] H=1 | +0.003 [−0.019,+0.026] H=1 |
| nemotron | ITT | +0.002 [−0.027,+0.027] H=1 | +0.003 [−0.022,+0.027] H=1 | −0.008 [−0.032,+0.016] H=1 | −0.002 [−0.025,+0.020] H=1 |

### 4.3 Violation@5 levels (registered, pooled, WITH_pilot, STRICT; higher = worse)

| model | analysis | C0 | C0b | C1a | C2a | C2b | C3 |
|---|---|---|---|---|---|---|---|
| llama | pp | 0.659 [0.567,0.756] | 0.639 [0.545,0.739] | 0.622 [0.523,0.724] | 0.128 [0.072,0.200] | 0.331 [0.253,0.405] | 0.092 [0.058,0.127] |
| llama | ITT | 0.659 [0.567,0.756] | 0.639 [0.545,0.739] | 0.622 [0.523,0.724] | 0.131 [0.075,0.203] | 0.412 [0.349,0.472] | 0.092 [0.058,0.127] |
| nemotron | pp | 0.367 [0.249,0.478] | 0.329 [0.223,0.444] | 0.323 [0.229,0.424] | 0.153 [0.086,0.243] | 0.255 [0.193,0.329] | 0.092 [0.058,0.127] |
| nemotron | ITT | 0.383 [0.262,0.498] | 0.362 [0.252,0.481] | 0.374 [0.279,0.470] | 0.153 [0.086,0.243] | 0.277 [0.207,0.363] | 0.092 [0.058,0.127] |

### 4.4 "higher = worse" qualifier added

Applied to: every Stale@5/Violation@5 table in this report and in S_REPORT
(§7 legend, §8, §9, §10, §11, §12, §13 headers) and to figure titles —
`stale_by_set` / `violation_by_set` suptitles and `contrasts_forest` suptitle
now read "higher = worse" / "positive = first condition staler, higher = worse".
Figures re-rendered: 5 figures, CSV rows unchanged 156/156/156/16/156 (label
edits only; `s_figures.py`). Shift@5 and Drop-faithful are not Stale/Violation
and keep their existing direction wording.

### 4.5 Pooled LENIENT (registered secondary oracle mode, §8.32.3) — previously untabulated

Found during item 4: the registered scorer computed pooled lenient levels and
contrasts, but S_REPORT tabulates pooled STRICT only (lenient appears solely
as the pre-specified D1/D2 companion, §11). **Disclosure gap — closed here**
(cross-reference added as S_REPORT §16.11). Lenient is secondary to STRICT
primary; §8.33.3 pre-specifies it as companion only for D1/D2, so everything
in §4.5 is secondary presentation. All values **higher = worse**.

Stale@5 as-scored levels:

| model | analysis | C0 | C0b | C1a | C2a | C2b | C3 |
|---|---|---|---|---|---|---|---|
| llama | pp | 0.006 [0.000,0.015] | 0.027 [0.013,0.047] | 0.037 [0.022,0.057] | 0.065 [0.047,0.086] | 0.021 [0.009,0.035] | 0.065 [0.046,0.087] |
| llama | ITT | 0.006 [0.000,0.015] | 0.027 [0.013,0.047] | 0.037 [0.022,0.057] | 0.067 [0.050,0.088] | 0.035 [0.019,0.056] | 0.065 [0.046,0.087] |
| nemotron | pp | 0.030 [0.015,0.049] | 0.029 [0.012,0.049] | 0.039 [0.027,0.052] | 0.070 [0.051,0.092] | 0.026 [0.014,0.043] | 0.065 [0.046,0.087] |
| nemotron | ITT | 0.042 [0.020,0.073] | 0.042 [0.017,0.076] | 0.057 [0.039,0.081] | 0.070 [0.051,0.092] | 0.035 [0.020,0.053] | 0.065 [0.046,0.087] |

Stale@5 as-scored contrasts:

| model | analysis | C2a−C0b | C2b−C0b | C2a−C1a | C3−C2b |
|---|---|---|---|---|---|
| llama | pp | **+0.039 [+0.011,+0.064] H=0.0168** | −0.008 [−0.034,+0.014] H=0.5123 | **+0.028 [+0.005,+0.048] H=0.0240** | **+0.047 [+0.033,+0.064] H=0.0004** |
| llama | ITT | **+0.040 [+0.014,+0.064] H=0.0087** | +0.008 [−0.019,+0.033] H=0.5188 | **+0.029 [+0.008,+0.048] H=0.0116** | **+0.030 [+0.015,+0.045] H=0.0012** |
| nemotron | pp | **+0.039 [+0.022,+0.057] H=0.0004** | −0.002 [−0.014,+0.011] H=0.7982 | **+0.031 [+0.017,+0.045] H=0.0004** | **+0.036 [+0.021,+0.052] H=0.0004** |
| nemotron | ITT | +0.027 [−0.001,+0.053] H=0.1278 | −0.008 [−0.039,+0.020] H=0.6217 | +0.013 [−0.009,+0.031] H=0.4350 | **+0.030 [+0.015,+0.046] H=0.0012** |

Key honest reading: under the registered **secondary** lenient mode,
**nemotron C3−C2b holds the both-rule** (+0.036 pp H=0.0004; +0.030 ITT
H=0.0012) — the only nemotron contrast anywhere in the registered machinery
that does so; nemotron C2a−C0b / C2a−C1a are pp-only (ITT H=0.128 / 0.435) →
fail the both-rule; llama's three hold (C2b−C0b null). The **primary STRICT
conclusion is unchanged** (nemotron null at strict). Conditional (|D|>0)
lenient mirrors this (nemotron C3−C2b pp H=0.0004 / ITT H=0.0004; llama's
three hold; nemotron C2a−C0b/C2a−C1a pp-only; C2b−C0b null) — full values in
`s_scores.json` / `s_scores_conditional.json` (lenient keys).

---

## 5. Item 5 — Power: minimum detectable difference (MDD) for the Stale contrasts

Method per §8.34.5: SE = (hi − lo) / (2 × 1.96) from the observed conditional
contrast CI; MDD80 = (z₁₋α/₂ + z₀.₈₀) × SE at α = 0.05 and α = 0.0125 (worst
Holm rank of 4). Conditional (|D|>0) contrast, strict mode.

### 5.1 STRICT, pp

| model | contrast | observed Δ | SE | MDD80 (α=.05) | MDD80 (α=.0125) | \|Δ\|/MDD(.05) | Holm |
|---|---|---|---|---|---|---|---|
| llama | C2a−C0b | +0.294 | 0.0704 | 0.197 | 0.235 | **1.49** | 0.0009 |
| llama | C2b−C0b | −0.005 | 0.0036 | 0.010 | 0.012 | 0.48 | 0.3954 |
| llama | C2a−C1a | +0.272 | 0.0664 | 0.186 | 0.222 | **1.46** | 0.0009 |
| llama | C3−C2b | +0.314 | 0.0835 | 0.234 | 0.279 | **1.34** | 0.0008 |
| nemotron | C2a−C0b | +0.024 | 0.1311 | 0.367 | 0.438 | 0.06 | 1 |
| nemotron | C2b−C0b | +0.036 | 0.0901 | 0.252 | 0.301 | 0.14 | 1 |
| nemotron | C2a−C1a | −0.019 | 0.1018 | 0.285 | 0.340 | 0.07 | 1 |
| nemotron | C3−C2b | +0.034 | 0.1084 | 0.304 | 0.362 | 0.11 | 1 |

### 5.2 STRICT, ITT (same method, ITT CIs)

llama: C2a−C0b ratio **1.49** (MDD80 .05 = 0.197, H=0.0012); C2a−C1a **1.46**
(0.186, H=0.0012); C3−C2b Δ=+0.219 ratio **1.11** (MDD 0.198, H=0.0072);
C2b−C0b Δ=+0.088 ratio 0.91 (MDD 0.096, H=0.0142 — the registered ITT-only
result sits just at the detection boundary). nemotron ITT: |Δ| 0.022–0.075,
ratios 0.06–0.25, all H=1.

### 5.3 Reading (good and bad)

- **llama's three both-rule contrasts are "large" relative to the study's
  resolution** (ratios 1.34–1.49 at α=.05; still >1 at worst-Holm α=.0125:
  1.25/1.23/1.13 computed from table) — the strict null for C2b−C0b
  (|Δ| 0.005 vs MDD 0.010) is consistent with a genuinely negligible effect,
  but the study could not have resolved effects below ~1 pp there.
- **nemotron's strict nulls are severely underpowered** (ratios 0.06–0.14;
  MDD80 = 0.25–0.37): strict-mode data cannot distinguish "no effect" from any
  effect up to 25–37 pp. The strict all-null statement about nemotron is a
  *low-information* result, not evidence of equivalence — disclosed as such.
- Lenient mode has more cells (n ≈ 91–104): nemotron lenient pp MDDs drop to
  0.09–0.14 and three conditional contrasts are Holm-significant in pp
  (ratios 1.42–1.60), but ITT fails for C2a−C0b/C2a−C1a (→ not claimable
  under the both-rule); only C3−C2b holds pp+ITT (§4.5).
- All variants (strict/lenient × pp/ITT × both α) and raw SEs:
  `s_followup.json → power` (32 entries).

---

## 6. Item 6 — Case studies: five WET scenarios that kept a newly infeasible crop

Selection rule (stated; deterministic): mode STRICT; sets WET1/WET2;
conditions C3 + C2a; usable advice top-5; crop ∈ top5 ∩ D, |D| > 0; candidates
sorted (C3 first, set, sid, model, crop); pick the first candidate per set
within each condition with **distinct scenario ids** (C2a: llama for WET1,
nemotron for WET2 when available), then fill in sorted order → 3 × C3 +
2 × C2a. Candidates available: 45 (C3 14, C2a 31). Full rule stored in
`s_followup_cases.json` (see §11 F2: the first pass produced five near-identical
cases; the rule was diversified **before** the final output).

| # | set/sid | condition | season/district | kept (advice pos) | constraint crossed | scorer rank / score | season / risk components |
|---|---|---|---|---|---|---|---|
| 1 | WET1 / S000358 | C3 (model-independent) | Kharif / Alirajpur | Urad (2) | flood: false→true, table=cited, strict | 2 / 0.898 | 0.75 / 0.83 |
| 2 | WET2 / S001353 | C3 | Zaid / Betul | Urad (5) | flood: false→true, table=cited, strict | 5 / 0.481 | 0.00 / 0.875 |
| 3 | WET1 / S001538 | C3 | Kharif / Bhind | Urad (4) | flood: false→true, table=cited, strict | 4 / 0.632 | 0.75 / 0.828 |
| 4 | WET1 / S000358 | C2a (llama) | Kharif / Alirajpur | Urad (2) | flood: false→true, table=cited, strict | 2 / 0.778 | 0.35 / 0.83 |
| 5 | WET2 / S000480 | C2a (nemotron) | Kharif / Anuppur | Urad (5) | flood: false→true, table=cited, strict | 5 / 0.852 | 1.00 / 0.901 |

Facts only (per §8.34.6):

- **All 45 strict candidates are Urad under flood (cited).** Under the strict
  oracle the WET arms expose exactly one crop (Urad); the five cases therefore
  differ by set/sid/condition/model, not by crop or hazard. This is a property
  of the oracle signal, not of the selection rule.
- **The scorer formula contains no hard-constraint table.** In every case the
  newly-active flood constraint enters the score only through the 0.15-weighted
  `risk_penalty` component (e.g. case 4: risk 0.83 contributes 0.1245 of the
  total; rainfall 0.2 + soil 0.2 + temperature 0.1485 + season 0.105 carry the
  rest). Nothing in `crop_score`/`score_crops` blocks a flood-cited crop; only
  the oracle's D set marks it infeasible — which is exactly the gap Stale@5
  measures.
- Case 2 (Zaid): season_alignment = 0.00 (Urad not Zaid-supported) and
  rainfall = 0.00, yet soil 0.20 + temperature 0.15 + risk 0.131 still rank it
  5th — a low-ranked retention, not a near-top recommendation.
- Case 1 vs case 4 (same scenario): registered pipeline scores Urad 0.898
  (season 0.75 via empty-window default) while the stored MCP tool scores it
  0.778 (season 0.35 via real windows, week 31) — the B6 season-handling
  difference (§1) visible inside a live case.
- Chain-of-custody for the C2a cases: re-computed tool top-6 == stored bundle
  `crop_score` top-6 (`stored_tool_top6_matches_recompute: true`), and stored
  `current_week` == `as_of` week (31 and 28).

---

## 7. Item 7 — Terminology rename: display text only, machine keys frozen

"false-change" → "movement not explained by hard-constraint changes", with the
one-line note **soft-score movement is expected** (the scorer's components are
continuous, so advice can move even when no hard constraint changes).

| Location | Before | After |
|---|---|---|
| S_REPORT §14.3 heading | False-change (advice moved while the oracle did not…) | Movement not explained by hard-constraint changes (advice moved while the oracle did not…) |
| S_REPORT §5, §15.5, §16.x, §18, §19, §20 | 6 × "false-change" prose/label spots | renamed in place |
| `s_figures.py` figure suptitle | "S-series false-change control: advice moved although the oracle did not" | "S-series: advice movement not explained by hard-constraint changes — soft-score movement is expected" |
| `s_figures.py` panel title | "<model> — false-change rate" | "<model> — movement not explained by hard-constraint changes" |
| `s_figures.py` docstring | false_change : P(Shift@5>0 \| \|D\|=0) | same definition + display-rename note |
| `PROGRESS.md` S-STEP 11a | "…contrasts forest, false-change" | "…contrasts forest, movement-not-explained (§14.3 display rename…)" |

**Not renamed (provenance):** JSON key `s_scores.json → false_change`, its
`false_change.*` figure filenames and CSV `figure`/`metric` values
(`shift_gt0_given_no_signal`), the function/section keys `false_change`,
`false_change_fig`, and the `score_s.py` docstring (frozen scorer; B9 note
unchanged). Figures re-rendered with identical data (5 PDF+PNG+CSV; CSV rows
156/156/156/16/156). S_REPORT keeps the S_REPORT §19 provenance row pointing
at `false_change` keys.

---

## 8. Item 8 — Methods disclosures (paper-ready paragraph)

> **S-series scoring: two data-handling choices.** (i) *Nemotron baseline
> enrichment.* Some cached canonical C0/C0b responses recorded for nemotron in
> the canonical runs were unusable (malformed/truncated output). Before scoring
> these baseline cells were deterministically replaced by the first usable copy
> of the same cell found in the on-disk canonical runs (`enrich_baseline` in
> `score_s.py`; offline, no model call, no response content generated or
> altered — an availability repair only, documented in the function docstring).
> Three cells have no usable record anywhere and are excluded per-protocol (pp)
> / worst-cased (ITT). This affects only nemotron baseline usability, never a
> perturbed response. (ii) *Stale@5 at |D| = 0 (registered vs as-scored).* The
> registered definition (PROTOCOL §8.32.4), Stale@5 = |top5 ∩ D| / |D|, is
> undefined when the oracle did not move (D = ∅); the scorer as-run returns 0
> on those cells, and its docstring — which overclaimed this as the registered
> convention (bug B9) — was left as-run for provenance. Both conventions are
> therefore reported: the as-scored 0-filled version (S_REPORT §7–§8) and the
> |D| > 0 conditional version (S_REPORT §9; primary in S_FOLLOWUP §4). All
> verdicts are invariant to the convention (dilution factor ×9.12; verification
> 0.294 ≈ 0.032 × 9.12, S_REPORT §5).

(Supporting disclosures already in S_REPORT §16 — pp/ITT operationalization,
C3 instrument §16.7/B6, coverage framing, N0/N1 — and the pooled-lenient
gap §16.11 → §4.5 here — complete the methods story.)

---

## 9. Honest-result inventory (every result, good and bad)

1. **B6 has one root cause** (season handling, 17/17; nothing else) — closed.
2. **Real-series impact of the B6 proxy:** C2a fidelity to the real tool was
   *understated* (0.516 → 0.998 ordered-identical; 242/500 lists differ
   proxy-vs-tool); scorer P@5 vs ground truth is 2.0 pp lower with the actual
   tool (0.5035 → 0.4833); final-answer P@5 unchanged.
3. **Retention gaps:** nemotron C1a 0.39 pp / 0.48 ITT (strict) vs llama 1.00;
   nemotron C2b lenient 0.33/0.35; llama C2a 0.717; C3 0.795 both models.
4. **Exposure is thin** (strict 1.9–6.1 % of cells; 10–30 exposed), so all
   retention estimates are imprecise (k = 2–15 districts).
5. **Delta-violation:** no significant increase anywhere; several decreases
   (llama C1a/C2a strict; nemotron C2b lenient signal, both analyses);
   llama C2b positive-but-noise; C0/C0b untested by construction.
6. **Power:** llama's three claimable contrasts are detectable (ratio 1.34–1.49);
   llama C2b−C0b sits at the resolution floor; **nemotron strict nulls are
   underpowered (MDD 25–37 pp) and must not be read as equivalence**;
   nemotron lenient pp is powered and significant for three contrasts but ITT
   fails them (both-rule) — only nemotron C3−C2b (lenient) holds pp+ITT.
7. **Disclosure gap found and closed:** pooled registered-lenient results were
   never tabulated in S_REPORT (now in §4.5 + S_REPORT §16.11). Strict primary
   conclusions unchanged.
8. **Case studies:** all strict WET exposure is a single crop (Urad/flood-cited);
   the scorer has no hard-constraint gate — flood enters only via the risk
   penalty (weight 0.15).
9. **Labels changed, numbers did not** (items 4/7); figure PNGs other than
   `contrasts_forest.png` were not pixel-inspected (carried from S_REPORT §18).
10. **No frozen file, no registered number changed; no model calls; no commit.**

---

## 10. Provenance — every number → script → output

| Section | Script | Output |
|---|---|---|
| §1.1 B6 root cause | `eval/scripts/s_followup_b6.py` | `s_followup_b6.json` |
| §1.2 real-series impact | `eval/scripts/s_followup_real_impact.py` | `s_followup_real_impact.json` |
| §2 exposure/retention, §3 delta-violation, §5 power | `eval/scripts/s_followup.py` (gate: reconstructs `s_scores_cells.csv`, PASS 12 480 / 0 mismatch @1e-6) | `s_followup.json` |
| §4.1–§4.3, §4.5 tables | presentation-only reads of `s_scores_conditional.json` + `s_scores.json` (no new computation) | (none — registered JSONs) |
| §4.4, §7 figure labels | `eval/scripts/s_figures.py` re-render (data unchanged) | `eval/results/figures/*` |
| §6 cases | `eval/scripts/s_followup_cases.py` | `s_followup_cases.json` |
| §8 methods paragraph | sources: `score_s.py` (`enrich_baseline`, `stale_at5`), S_REPORT §5/§16.5 | (text) |

---

## 11. Follow-up-phase bug / iteration log (date found → date fixed)

| # | Found | Fixed | Issue | Impact |
|---|---|---|---|---|
| F1 | 2026-10-19 | 2026-10-19 | `s_followup.py` reconstruction gate compared floats at 1e-9 against `s_scores_cells.csv`, which stores 6 decimals → false mismatches | none on results; tolerance set to 1e-6, gate PASS 12 480 / 0 |
| F2 | 2026-10-19 | 2026-10-19 | First case-study pass (§6) selected 5 near-identical cases (all Urad, WET1, C3-heavy) because strict WET exposure is a single crop and the initial rule lacked set/model diversity | selection rule diversified (distinct sids, one per set, model alternation) **before** the final `s_followup_cases.json`; rule stored in the JSON |
| F3 | 2026-10-19 | 2026-10-19 (disclosed) | Pooled registered-lenient levels/contrasts computed by the scorer but never tabulated in S_REPORT (§4.5) | registered numbers untouched; disclosed here + S_REPORT §16.11 cross-reference |

(B6, the original instrument bug, remains logged as B6 in S_REPORT §17; §1.1
above supplies its root cause.)

---

**STOP — AWAITING USER APPROVAL.** No commit made. Registered S-series outputs
(`s_scores.json`, `s_scores_cells.csv`, S_REPORT numbers) unchanged.
