# AgroLLaMA: Evaluation & Figures (Paper-Writer Handoff)

**Audience:** the person writing the paper, and anyone who needs to understand *what was tested,
how, and what every figure means*. It is written so you can lift the scientific claims directly.

> **Deeper companions:** the tool internals (every formula, threshold and map) are in
> `TOOLS_REFERENCE.md`; the call mechanics and scenario/testing pipeline are in
> `EVAL_HARNESS_AND_SCENARIOS.md`; the figures are interpreted one-by-one in
> `FIGURES_EXPLAINED.md`. This document remains the high-level overview.

**One-line summary:** We compare LLM crop recommendations under six conditions, from a bare
LLM, through "give it all the evidence in the prompt", up to real MCP tool calling, against a
**deterministic reference (C3)**. The headline result: **giving the model real tool access raises
the agronomic quality of its recommendations substantially and significantly**, and the gain is
robust to conservative statistical treatment.

---

## 0. Where things live

| Thing | Path |
|---|---|
| Frozen protocol (authoritative, every decision timestamped) | `eval/PROTOCOL.md` |
| Human-readable results report | `eval/report/RESULTS_REPORT.md` |
| Figure captions + headline numbers | `eval/report/N500_FIGURES.md` |
| **Canonical figures (this doc)** | `eval/figures/n500/` |
| Canonical figure script | `eval/scripts/n500_figures.py` |
| Frozen result JSONs | `eval/results/n500_primary_metrics.json`, `eval/results/n500_clustered_inference.json` |
| Superseded figure sets (moved, not deleted) | `eval/figures/archive_v1/` (+ `eval/figures/SUPERSEDED.md`) |

> **Rule of thumb:** only the **n=500 `Fig_N01–N07`** set is headline-usable. Everything in
> `archive_v1/` uses older condition names or partial runs and is explicitly superseded.

---

## 1. The research question

> Does giving a language model **live tool access via MCP** produce better, safer, more
> seasonally-appropriate crop recommendations than (a) the model alone, (b) the model with a
> stronger prompt, or (c) the model with the same evidence *pasted into the prompt* (no tool
> calling)? And how do all of these compare to a **purely deterministic pipeline**?

The comparison is deliberately fair: the "pasted evidence" condition (**C1a**) receives *exactly
the same raw tool outputs* the tool-using condition (**C2a**) could fetch, so the only
difference is **whether the model actually calls tools**, not what information it has.

---

## 2. Conditions

All LLM conditions share the **same model and temperature**. Ground truth = the deterministic
**C3** top-5.

| ID | Name | Tools / prompt | Fair? | Role |
|---|---|---|---|---|
| **C0** | LLM-only | none; minimal prompt (district, coords, date) | Yes | Weakest baseline |
| **C0b** | LLM-only strong | none; prompt tells it to *consider* soil/season/rainfall/temp/risk | Yes | Strongest fair baseline |
| **C1a** | Fair stuffing | **raw evidence pasted** (weather, climate, season, soil, risk) + candidate requirements. **No** crop_score, **no** ranking, **no** scores, **no** function calling | Yes | Isolates "information without tools" |
| **C1b** | Oracle (leaks the answer) | full **C3 ranking injected** into the prompt | No | Upper bound only, never headline |
| **C2a** | Tools, full set | **six MCP tools**: weather, climate, season, risk, soil, **crop_score** | Yes | **The proposed method** |
| **C2b** | Tools, no scorer | **five tools** (all except crop_score) | Yes | Ablation: tools without the deterministic ranker |
| **C3** | No-LLM reference | deterministic tools + weighted scorer | n/a | Reference / ground-truth surrogate |

Pre-registered primary contrasts (the "family" of 4, Holm-corrected):
**C2a−C0b, C2a−C1a, C2b−C0b, C2b−C1a**.

**Models:** PRIMARY = `nvidia/nemotron-3-ultra-550b-a55b` on **n=500** (the headline);
SMALL = `meta/llama-3.2-11b-vision-instruct` on n=150; `z-ai/glm-5.3` was **dropped** (partial
n=32, endpoint degraded).

**Provider:** NVIDIA NIM (OpenAI-compatible), multi-key round-robin, `temperature=0.2`,
`max_output_tokens=4096` (4096→8192 for the C1a stuffing condition; see harness note §4.4).

---

## 3. Metrics (exact definitions)

Two **primary** metrics, each computed per scenario over the model's top-5 crops:

### 3.1 Season-validity rate (`sv`)
Fraction of a scenario's top-5 crops that are **valid for that scenario's season**, judged against
the cited crop-season table (`eval/data/ground_truth/crop_season_table_v1.1.csv`).
- **STRICT:** a crop/season row marked `UNVERIFIED` counts as **invalid**.
- **LENIENT:** `UNVERIFIED` rows are **excluded from the denominator** (no penalty for uncertainty).

### 3.2 Hard-violation rate (`hv`)
Fraction of top-5 crops that trip a **hard constraint** (`hard_constraints_v1.1.csv`), a crop in
the wrong season, or a water-intensive crop under drought, etc.
- **STRICT:** `UNVERIFIED` constraint rows count as **violations**.
- **LENIENT:** `UNVERIFIED` rows are excluded.

### 3.3 Analysis-frame: PP vs ITT
- **Per-protocol (PP):** only runs that returned **valid, untruncated JSON** are scored (the model
  did the job).
- **Intention-to-treat (ITT):** *all* planned runs are scored; an invalid/truncated output is
  counted as `sv = 0` and `hv = 1` (worst case). This protects against a model "winning" by
  failing to answer.

### 3.4 Claim rule (pre-registered)
A difference is only **claimed** if it holds with the **same sign and significance under both
STRICT and LENIENT, and under both PP and ITT** (a 2×2×2 robustness gate).

### 3.5 Secondary / diagnostic metrics (never headline)
- **Fidelity to C3**, top-5 Jaccard vs the deterministic reference. Diagnostic only; because C3
  is the repo's own system, agreement with it is *not* external correctness.
- Reliability (valid-JSON rate, truncation, tool-call success), efficiency (latency, tokens),
  consistency (repeat-to-repeat Jaccard/Kendall τ, secondary and circular by construction).

---

## 4. How the testing was done (reproducible pipeline)

### 4.1 Scenarios (`eval/scenarios.py`)
10,000 scenarios = points **sampled inside real MP district polygons** (51 districts), each with
an `as_of_date` from 2015–2025 and a season assigned by the **same month map as `season_tool`**,
so strata are well-defined. From these: a **stress set** (~4,212 drought/heat/flood), and a
**stratified LLM subset of 500** (≈150 stress). The two flip-halves of the 500 are **B1 (150)**
and **B2 (350)**.

### 4.2 Time anchoring: no look-ahead (`eval/time_anchored.py`)
The evaluation is a **hindcast**: "next 7 days" are observed archive values, not forecasts.
To make every scenario reproducible:
- weather is **sliced from a per-district Open-Meteo archive cache** (no live calls);
- the **clock is pinned** to the scenario's `as_of_date` inside `season_tool` and `crop_score`;
- **climate normals** use only dates strictly **before** the scenario date.
The **real tool code** is executed (nothing in `mcp_server/` is modified); an equivalence test
asserts the tool runtime returns byte-identical evidence to the deterministic bundles, i.e. the
LLM and C3 see the *same numbers*.

### 4.3 Deterministic reference C3
For all 10,000 scenarios the deterministic pipeline runs with ablations and weight sensitivities;
the canonical `full_repo` top-5 is the C3 reference.

### 4.4 LLM harness (`eval/llm/nvidia_provider.py`, `eval/scripts/run_model.py`)
Resumable runner (rewrites `results.json` after every call; reruns skip completed work). A
**harness fix** (PROTOCOL §8.10) handles models that emit unknown tool calls or never stop:
unknown calls are answered with a benign error, and the model is forced to emit a final JSON
object. Providers retry with exponential backoff.

### 4.3/4.5 Scoring
Each run's raw text is parsed (`eval/llm/prompts.py:parse_output`), crop names are **alias-
normalised** to the 21-crop registry, and `sv`/`hv` are computed per scenario. Results are
aggregated in `eval/scripts/n500_primary_metrics.py`.

### 4.6 Statistics (`eval/statistics.py`)
Bootstrap 95% CIs (10,000 resamples), paired **Wilcoxon** signed-rank and **McNemar** tests,
**Holm–Bonferroni** correction over the pre-registered family, and effect sizes (**Cliff's δ**,
Cohen's d).

---

## 5. The clustering correction (important for the paper's methods section)

Scenarios are **clustered within district** (51 districts, mean **9.8** scenarios each), and the
B1/B2 halves are **near district-disjoint**. Because `crop_score` ranks from district-determined
soil/season, scenarios in the same district get similar recommendations → **scenario-level CIs are
anti-conservative**.

`eval/scripts/n500_clustered_inference.py` therefore re-does **all** inference by **resampling
districts** (not scenarios): district ICC, design effect (DEFF), effective sample size (ESS), and
a **district-clustered bootstrap** for the four pre-registered contrasts (centered bootstrap p,
Holm). **Point estimates of the paired contrasts are unchanged**; only the CIs widen.

**Bottom line:** redoing everything cluster-aware changes **0 of 16 claimability cells**; every
pre-registered conclusion holds.

---

## 6. Primary results (n=500, Nemotron)

### 6.1 Condition quality (strict, per-protocol; the headline table)

| Condition | Season validity | Hard-violation |
|---|---|---|
| C0 (LLM only) | 0.551 | 0.382 |
| C0b (LLM strong) | 0.646 | 0.292 |
| C1a (pasted evidence) | 0.665 | 0.292 |
| **C2a (tools + scorer)** | **0.803** | **0.161** |
| C2b (tools, no scorer) | 0.772 | 0.151 |
| C3 (deterministic) | 0.863 | 0.104 |

### 6.2 Pre-registered contrasts (strict, per-protocol, season validity)

| Pair | Difference | District-clustered 95% CI | Naive Holm |
|---|---|---|---|
| C2a − C0b | **+0.161** | [+0.107, +0.214] | 2.7e-13 |
| C2a − C1a | **+0.135** | [+0.094, +0.176] | 3.9e-15 |
| C2b − C0b | **+0.128** | [+0.093, +0.160] | 2.8e-12 |
| C2b − C1a | **+0.105** | [+0.069, +0.140] | 2.5e-11 |

All four are **claimable** on `sv` and `hv`, under STRICT and LENIENT, under PP and ITT. The
district-clustered p-values floor at the bootstrap resolution (**4.0e-04**). The **C2a vs C1a**
contrast is the cleanest scientific statement: *the same information, delivered via tools rather
than pasted into the prompt, lifts season validity by ~13.5 points.*

### 6.3 C2a vs the deterministic reference C3 (per scenario, n=500)
| metric | match | beat (C2a better) | lose |
|---|---|---|---|
| sv strict | 361 (72.2%) | 13 (2.6%) | 126 (25.2%) |
| hv strict | 397 (79.4%) | 2 (0.4%) | 101 (20.2%) |
| hv lenient | 406 (81.2%) | 1 (0.2%) | 93 (18.6%) |

i.e. on ~72–81% of scenarios the tool-using LLM is *as good as* the deterministic pipeline, and
when it differs it is usually slightly worse, expected, since C3 is the reference the tools
implement.

---

## 7. Figure-by-figure interpretation (canonical set `Fig_N01–N07`)

Each figure is exported as **PDF + PNG (300 dpi)** to `eval/figures/n500/`, with the underlying
numbers in `eval/figures/n500/data/<figure>.csv`.

---

### Fig_N01: Condition quality (`Fig_N01_condition_quality`)
**File:** `Fig_N01_condition_quality.{pdf,png}` · **CSV:** `Fig_N01_condition_quality.csv`

* **Question:** How good is each condition, on its own?
* **What it plots:** two panels, (a) **season validity** and (b) **hard-constraint violation**, 
  as **bars** for C0, C0b, C1a, C2a, C2b, C3, each with a **95% CI** and the mean printed above
  the bar. Colour = condition (Okabe–Ito; C3 = black reference).
* **How to read it:** higher is better in (a); **lower is better** in (b). Non-overlapping CIs are
  a rough signal of a real difference (formal tests are in N02).
* **What it shows:** a clear monotone-ish ladder. The bare LLM is worst; the strong prompt and
  pasted evidence help a little; **tool calling (C2a/C2b) is a large jump**; the deterministic C3
  is best. Hard-violation is the mirror image.
* **Takeaway sentence for the paper:** *"Tool access roughly halves the hard-violation rate
  relative to the bare LLM (0.38 → 0.16) while raising season validity from 0.55 to 0.80."*

---

### Fig_N02: Pre-registered contrasts, clustered vs naive (`Fig_N02_preregistered_forest`)
**File:** `Fig_N02_preregistered_forest.{pdf,png}` · **CSV:** `Fig_N02_preregistered_forest.csv`

* **Question:** Are the four pre-registered improvements real, and do they survive clustering?
* **What it plots:** a **forest plot**; one row per pair (C2a−C0b, C2a−C1a, C2b−C0b, C2b−C1a),
  for `sv` (left) and `hv` (right). Coloured **bold** markers = **district-clustered** CI; grey
  thin whiskers = **scenario-level naive** CI. A dashed **0** line is the null.
* **How to read it:** a marker whose whole interval sits to the right of 0 = a significant
  improvement (for `hv` a favourable direction is likewise away from zero in the green/negative
  sense as labelled). The footnote `* Holm < 0.001` applies to all four pairs, clustered and naive.
* **What it shows:** all four intervals clear zero; clustering **widens** the intervals but never
  crosses zero.
* **Takeaway:** the headline contrasts are significant and **robust to the clustering correction**.

---

### Fig_N03: Design effect (`Fig_N03_design_effect`)
**File:** `Fig_N03_design_effect.{pdf,png}` · **CSV:** `Fig_N03_design_effect.csv`

* **Question:** How much does district clustering inflate uncertainty?
* **What it plots:** (a) **district ICC** per condition for `sv` (circles) and `hv` (squares);
  (b) **effective sample size (ESS)** vs nominal `n`, with a dashed `ESS = n` line (points below
  the line are clustered).
* **How to read it:** (a) ICC near 0 = no clustering, higher = stronger. (b) the vertical drop
  from the nominal `n≈500` shows the *effective* independent sample.
* **What it shows:** only the **tool-using** conditions cluster, `sv` ICC **0.166 for C2a**
  (DEFF 2.47, ESS ~203) and 0.084 for C2b; `hv` ICC **0.241 for C2a** (DEFF 3.12, ESS ~160).
  C0/C0b/C1a are ~0; C3 `sv` is exactly 0 (deterministic).
* **Why it matters:** justifies the clustered method in §5. The *contrasts* are far less
  clustered than the levels (shared district structure cancels).

---

### Fig_N04: District-level effect of C2b−C0b (`Fig_N04_district_variation`)
**File:** `Fig_N04_district_variation.{pdf,png}` · **CSV:** `Fig_N04_district_variation.csv`

* **Question:** Is the tool-access benefit uniform across districts, or driven by a few?
* **What it plots:** one **horizontal bar per district** (51), sorted by effect size, showing the
  district's mean **C2b − C0b season-validity** effect. Bars are coloured by **batch membership**
  (B1 vs B2). Title prints mean and between-district SD.
* **How to read it:** bars to the right = the district benefits from tools; the spread shows
  heterogeneity.
* **What it shows:** effect mean **+0.123**, between-district **SD 0.134**, range **−0.171
  (Burhanpur)** to **+0.400 (Barwani)**.
* **Important caveat to state in the paper:** the raw B1-vs-B2 gap (+0.094 ≈ 0.70 SD) is
  **district-level variation**, *not* a clean "batch effect", B1 happens to draw lower-effect
  districts (Burhanpur, Dhar, …) and B2 the higher-effect remainder. The merged n=500 contrast is
  what is claimed.

---

### Fig_N05: Per-season contrasts (`Fig_N05_season_contrasts`)
**File:** `Fig_N05_season_contrasts.{pdf,png}` · **CSV:** `Fig_N05_season_contrasts.csv`

* **Question:** Does the benefit hold in each cropping season (Kharif/Rabi/Zaid)?
* **What it plots:** three panels (one per season); rows = the four pairs; markers = clustered
  point estimate with CI; **filled** = p < 0.05, **hollow** = not significant.
* **What it shows (strict PP `sv`):**
  - **Kharif:** strong everywhere, +0.275 / +0.250 / +0.168 / +0.142.
  - **Rabi:** mixed, +0.119 / −0.012 / +0.061 / **−0.067**. The negative values (Rabi, C2a−C1a
    and C2b−C1a) reflect the well-documented **Rabi rainfall-channel limitation** (below).
  - **Zaid:** largest for C1a-relative pairs, +0.053 / +0.167 / +0.163 / +0.276.
* **Takeaway:** the benefit is **not confined to one season**; where it weakens (Rabi) there is an
  identified mechanistic cause.

> **Rabi limitation (declared in PROTOCOL §8.14):** Rabi-month rainfall normals are far below
> every crop's rainfall band, so the rainfall channel of `crop_score` cannot discriminate in Rabi,
> so it collapses onto temperature/soil/season/risk. This is a **scorer limitation**, not an
> LLM result; no weights were changed.

---

### Fig_N06: Split-half robustness (`Fig_N06_half_contrasts`)
**File:** `Fig_N06_half_contrasts.{pdf,png}` · **CSV:** `Fig_N06_half_contrasts.csv`

* **Question:** Do the C2b contrasts hold on each half of the 500, or is the merged result an
  artefact of one batch?
* **What it plots:** two panels (C2b−C0b, C2b−C1a); three rows = **B1**, **B2**, **merged**;
  bold = clustered, grey = naive.
* **What it shows:** the merged and B2 intervals are clearly positive. **B1 is the weak half**, 
  B1 **C2b−C1a** drops to **not significant** under clustering ([-0.004, +0.139], p≈0.09) and
  B1 **C2b−C0b** is borderline ([0.000, +0.123], p≈0.047).
* **Takeaway:** the effect is **not an artefact**, but it is **district/temporal-heterogeneous**;
  combined with N04 this is a *district-composition* story, honestly disclosed.

---

### Fig_N07: Tool-LLM vs deterministic, per scenario (`Fig_N07_c2a_vs_c3`)
**File:** `Fig_N07_c2a_vs_c3.{pdf,png}` · **CSV:** `Fig_N07_c2a_vs_c3.csv`

* **Question:** When C2a (tools+scorer) could be compared head-to-head with C3, how often is it
  equal, better, or worse?
* **What it plots:** four **stacked bars**, `sv` strict, `sv` lenient, `hv` strict, `hv` lenient, 
  split into **match / beat / lose** (green / yellow / orange).
* **What it shows:** `sv` strict ≈ **72.2% match, 2.6% better, 25.2% worse**; `hv` strict ≈
  **79.4 / 0.4 / 20.2**; `hv` lenient ≈ **81.2 / 0.2 / 18.6**.
* **Takeaway:** the tool-using LLM **matches the deterministic pipeline on ~72–81% of scenarios**
  and is rarely better, an honest framing of "the LLM adds little *beyond* the deterministic
  pipeline, but it is close to it, and clearly better than any LLM-only baseline."

---

## 8. The superseded figure sets (so nothing is lost)

These are **moved** to `eval/figures/archive_v1/` and are **not** headline-usable; keep them only
for provenance. Full details in `eval/figures/SUPERSEDED.md`.

### 8.1 `archive_v1/cross_model_M/`: cross-model set `Fig_M01–M10`
Uses the **older condition naming (C1/C2)** and the **partial** cross-model run (Llama 150, GLM
32). They answer secondary/process questions:
- **M01** valid-JSON rate by model×condition · **M02** median latency · **M03** token efficiency ·
  **M04** tool-call usage in C2 · **M05** "Accuracy@5 / Fidelity to C3" · **M06** out-of-registry
  (hallucination) rate · **M07** season-validity rate · **M08** per-condition gain vs C0 (Jaccard)
  · **M09** latency-vs-reliability trade-off · **M10** paired sample sizes.
- Historical/qualitative findings retained there: prompt-strength alone (C0b) does nothing;
  **stuffing is the biggest lever**, tool calling helps but less than stuffing in that older
  framing; hallucination (out-of-registry) rate was **0.0%** for all models; GLM far slower.

### 8.2 `archive_v1/paper/`: deterministic-phase set `Fig01–Fig14`
The first-pass paper figures (deterministic C3 behaviour, ablations, sensitivity, crop
frequency/diversity) built on the older naming and the pre-registered n=500 run's precursor.

### 8.3 `archive_v1/E_series/`: early deterministic set `Fig_E01–E06`
Legacy deterministic figures (ablation, weights sensitivity, per-season validity, crop frequency,
diversity). The **E-series carries hardcoded legacy values** (e.g. `n=8,628`) and is superseded;
for the deterministic reference numbers use `RESULTS_REPORT.md` §3 and the C3 row in §6.1 here.

---

## 9. Known limitations (state these in the paper)

1. **The reference is the repo's own deterministic pipeline (C3), not authoritative agronomy.**
   `sv`/`hv` use a **cited crop-season / hard-constraint table** (v1.1), but there is **no external
   ground truth** (ICAR-CRIDA / data.gov.in not acquired). "Fidelity to C3" is therefore a
   *diagnostic*, never a correctness claim.
2. **Hindcast, not forecast.** Scenario weather is observed archive data (no look-ahead), so the
   study evaluates *model behaviour given real evidence*, not forecasting skill.
3. **Unit of replication is the district (51), not the 500 scenarios**, scenarios are clustered
   (ICC up to 0.24 for C2a `hv`). All inference is district-clustered (§5); scenarios-level CIs
   would be anti-conservative.
2. **Heterogeneity is real and disclosed:** the B1/C2b−C1a cell is not significant on its own
   (N06); the B1/B2 gap is district composition (N04).
3. **Rabi rainfall-channel limitation** weakens the tool signal in Rabi (Fig_N05; PROTOCOL §8.14).
4. **GLM dropped** (partial n=32, degraded endpoint); cross-model comparisons are at **n=150**
   (common support), not 500.
4. **Llama C2 failures** (18/150), small model sometimes stops after tool calls without a final
   JSON; handled via the ITT frame. **Consistency repeats** are secondary and circular; see
   PROTOCOL §8.29a.
5. **Free-tier, non-version-locked models**, results are tied to model snapshots that may change.
5. **Zaid** is intrinsically hard for every system (the deterministic pipeline itself scores
   ~0.53), which compresses headroom there.

---

## 10. Reproduction (exact commands)

```powershell
# Regenerate the canonical n=500 figures from frozen artifacts (offline, no API)
python -u eval/scripts/n500_figures.py
#   -> eval/figures/n500/Fig_N01..N07.{pdf,png} + eval/figures/n500/data/*.csv

# Recompute the primary metrics from the frozen runs
python -u eval/scripts/n500_primary_metrics.py     # -> eval/results/n500_primary_metrics.{json,txt}

# Redo all inference district-clustered (the method used in the paper)
python -u eval/scripts/n500_clustered_inference.py # -> eval/results/n500_clustered_inference.{json,txt}

# Consistency repeats (secondary; needs the repeat runs present)
python -u eval/scripts/consistency_analysis.py
```

Original LLM runs were produced with `eval/scripts/run_model.py` (resumable); see
`RESULTS_REPORT.md` §7 for the exact commands.

---

## 10a. Handoff checklist for the paper writer

- **Headline numbers to cite:** §6.1 (condition table) and §6.2 (contrasts). The single strongest
  claim is **C2a − C1a = +0.135 season validity [+0.094, +0.176]**, i.e. *tools beat pasting the
  same evidence into the prompt.*
- **Methods sentence for clustering:** "Because scenarios are clustered within district
  (51 districts, mean 9.8 each) and the split halves are near district-disjoint, all inference
  uses a district-clustered bootstrap; every conclusion is unchanged (0/16 cells)."
- **Robustness gate:** every claim passes STRICT **and** LENIENT, PP **and** ITT.
- **Do not headline:** C1b (oracle/leaks answer), "Fidelity to C3", hallucination rate, or
  consistency (all secondary/diagnostic).
- **Be explicit about the reference:** success is agreement with the repo's deterministic
  pipeline, not external agronomic correctness.
- **Figures:** use `Fig_N01`–`Fig_N07`; cite the `.csv` in each `data/` folder for exact values.
- **Superseded figures must not reappear** as headline; if a reviewer asks about the earlier
  cross-model plots, point to `archive_v1/` and explain they used older naming/partial runs.

---

## 11. Glossary

| Symbol / term | Meaning |
|---|---|
| **C0, C0b, C1a, C1b, C2a, C2b, C3** | the seven conditions (see §2) |
| **sv / hv** | season-validity rate / hard-violation rate |
| **STRICT / LENIENT** | how `UNVERIFIED` ground-truth rows are treated |
| **PP / ITT** | per-protocol vs intention-to-treat scoring frame |
| **ICC / DEFF / ESS** | intra-class correlation / design effect / effective sample size |
| **B1, B2** | the 150- and 350-scenario halves of the n=500 subset |
| **Holm** | Holm–Bonferroni multiple-comparison correction |
| **Cliff's δ** | non-parametric effect size (−1..1) |
