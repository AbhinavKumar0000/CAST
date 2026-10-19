# AgroLLaMA: Figures Explained (Every Plot, Statistic and Number)

**Audience:** anyone reading, presenting or refereeing the AgroLLaMA evaluation. This is a
**plots-only** reference: what each figure is, which statistic it encodes, where the numbers
come from, how to read it, and how to interpret it.

**Canonical set:** `Fig_N01`–`Fig_N07`, in `eval/figures/n500/`. These are the **only
headline-usable** figures. Everything else (M-series, Fig01–14, E-series) is **superseded**
and lives under `eval/figures/archive_v1/`, covered in §11 for provenance.

**How the canonical figures are made:** `eval/scripts/n500_figures.py`. It reads **only**
two frozen artifacts, 
`eval/results/n500_primary_metrics.json` and `eval/results/n500_clustered_inference.json`
(plus the `.txt` for the C2a-vs-C3 match/beat/lose counts), so the figures are fully
reproducible offline with `python -u eval/scripts/n500_figures.py`. Each figure is saved as
**PDF + PNG (300 dpi)** in `eval/figures/n500/`, and its exact underlying numbers as
`eval/figures/n500/data/<figure>.csv`.

**Global conventions.**
- Condition colour = **Okabe–Ito** palette; **C3 = black** (the deterministic reference):
  `C0 #0072B2`, `C0b #56B4E9`, `C1a #009E73`, `C2a #D55E00`, `C2b #E69F00`, `C3 #000000`.
- Condition short tags: `C0 LLM`, `C0b LLM v2`, `C1a pasted`, `C2a MCP+crop`, `C2b MCP`,
  `C3 det`.
- The headline numbers use the **strict, per-protocol** cell (`strict_pp_*`) on the
  **`cells_WITH pilot_dev`** basis (all n=500). Pre-registered pairs are
  `C2a−C0b, C2a−C1a, C2b−C0b, C2b−C1a`.

---

## 1. Which figure answers which question

| Figure | Question |
|---|---|
| **N01** | How good is each condition on its own? |
| **N02** | Are the four pre-registered improvements real, and do they survive clustering? |
| **N03** | How much does district clustering inflate uncertainty? |
| **N04** | Is the tool benefit uniform across districts or concentrated? |
| **N05** | Does the benefit hold in each cropping season? |
| **N06** | Does the main contrast hold on both flip-halves? |
| **N07** | Head-to-head, how often does the tool-using LLM match/beat/lose to deterministic C3? |

---

## 2. Fig_N01: Condition quality

**File:** `Fig_N01_condition_quality.{pdf,png}` · **CSV:** `Fig_N01_condition_quality.csv`

* **What it plots:** two panels, side by side.
  * **(a) Season validity (`sv`)**, one bar per condition
    `C0, C0b, C1a, C2a, C2b, C3`, height = the condition's mean `sv`, with a **95%
    bootstrap CI** (black whiskers) and the mean printed above each bar. Higher = better.
  * **(b) Hard-constraint violation (`hv`)**, same layout; **lower = better**.
* **Statistic / data source:** the `strict_pp_<cond>` cells in
  `n500_primary_metrics.json → cells_WITH pilot_dev`; each cell stores
  `[mean, ci_lower, ci_upper, n]` for `sv` and `hv`, computed by a 10,000-resample
  percentile bootstrap. The CSV stores `metric, condition, mean, lo, hi, n`.
* **How to read it:** non-overlapping CIs are a *rough* signal of a real difference; the
  formal paired tests are in N02, so do not over-claim from N01 alone. Bar colours identify
  conditions; C3 (black) is the deterministic reference (no LLM).
* **What it shows (strict, PP, n=500):**

  | Condition | Season validity | Hard-violation |
  |---|---|---|
  | C0 (LLM only) | 0.551 | 0.382 |
  | C0b (LLM strong) | 0.646 | 0.292 |
  | C1a (pasted evidence) | 0.665 | 0.292 |
  | **C2a (tools + scorer)** | **0.803** | **0.161** |
  | C2b (tools, no scorer) | 0.772 | 0.151 |
  | C3 (deterministic) | 0.863 | 0.104 |

* **Interpretation:** a monotone-ish quality ladder. The bare LLM is worst; a stronger
  prompt (C0b) and pasting the evidence (C1a) help a little; **real tool calling (C2a/C2b)
  is a large jump**; the deterministic C3 is best. Hard-violation is the mirror image.
* **Takeaway sentence:** *"Tool access roughly halves the hard-violation rate relative to
  the bare LLM (0.38 → 0.16) while raising season validity from 0.55 to 0.80."*

---

## 3. Fig_N02: Pre-registered contrasts, clustered vs naive

**File:** `Fig_N02_preregistered_forest.{pdf,png}` · **CSV:**
`Fig_N02_preregistered_forest.csv`

* **What it plots:** a **forest plot** with two panels, **(a) `sv`**, **(b) `hv`**, one
  row per pre-registered pair (`C2a−C0b`, `C2a−C1a`, `C2b−C0b`, `C2b−C1a`).
  * **Coloured, bold marker** = the **district-clustered** point estimate ± CI.
  * **Grey thin whisker** (offset just above) = the **scenario-level naive** CI.
  * A dashed vertical line at **0** is the null.
* **Statistic / data source:** `n500_clustered_inference.json → clustered[strict_pp_<metric>_<pair>]`,
  which stores both a `naive` and a `cluster` block, each `{diff, lo, hi, holm, n}`. The CSV
  records `metric, pair, naive_diff/lo/hi, clustered_diff/lo/hi, holm_naive, holm_clustered, n`.
* **How to read it:** a marker whose **entire interval lies on the favourable side of 0**
  (right of 0 for `sv`, left of 0 for `hv`, per the axis label "paired difference") is a
  significant improvement. The footnote `* Holm < 0.001 for all four pairs` applies to both
  the clustered and naive results.
* **What it shows (strict, PP, `sv`):**

  | Pair | Difference | District-clustered 95% CI | Naive Holm |
  |---|---|---|---|
  | C2a − C0b | **+0.161** | [+0.107, +0.214] | 2.7e-13 |
  | C2a − C1a | **+0.135** | [+0.094, +0.176] | 3.9e-15 |
  | C2b − C0b | **+0.128** | [+0.093, +0.160] | 2.8e-12 |
  | C2b − C1a | **+0.105** | [+0.069, +0.140] | 2.5e-11 |

  The same four hold on `hv`: the tool conditions reduce the violation rate by roughly the
  same margins.
* **Interpretation:** all four intervals clear zero; **clustering widens the intervals but
  never crosses zero**. The contrasts are significant and **robust to the clustering
  correction**. The strongest single claim is **C2a − C1a = +0.135 `sv` [+0.094, +0.176]**, 
  *tools beat pasting the same evidence into the prompt.*

---

## 4. Fig_N03: Design effect

**File:** `Fig_N03_design_effect.{pdf,png}` · **CSV:** `Fig_N03_design_effect.csv`

* **What it plots:** two panels.
  * **(a) District ICC**, one point per condition for `sv` (**circles**) and `hv`
    (**squares**), on a 0–0.30 axis. ICC near 0 = no clustering.
  * **(b) Effective sample size (ESS)** vs nominal `n`, one point per condition (same
    shapes), with a dashed `ESS = n` line. Points below the line are clustered.
* **Statistic / data source:** `n500_clustered_inference.json → icc[<metric>_<cond>]`
  (`icc`, `n`, `ess`). The CSV stores both panels with `panel, metric, condition, icc, n, ess`.
* **How to read it:** in (a) only the **tool-using** conditions rise above zero; in (b) the
  vertical drop from the nominal `n≈500` is the loss of effective independent sample.
* **What it shows:** `sv` ICC **0.166 for C2a** (DEFF 2.47, ESS ≈ 203) and **0.084 for C2b**;
  `hv` ICC **0.241 for C2a** (DEFF 3.12, ESS ≈ 160) and **0.070 for C2b**. C0/C0b/C1a are
  ≈ 0. **C3's `sv` ICC is exactly 0** (purely deterministic, so the same district/season
  gives identical evidence); its `hv` ICC is small (0.052). ESS for C2a's `sv` is ≈ 203, not
  500.
* **Interpretation (methods sentence):** scenarios are not independent observations; the
  **district is the effective unit of randomisation**. This is *why* all inference in the
  paper uses the district-clustered bootstrap. The **point estimates** of the paired
  contrasts are unaffected, only their intervals widen.

---

## 5. Fig_N04: District variation in the tool effect

**File:** `Fig_N04_district_variation.{pdf,png}` · **CSV:** `Fig_N04_district_variation.csv`

* **What it plots:** a horizontal bar per **district**, one row each, sorted by effect size.
  Bar length = the district's mean **C2b − C0b season validity**. Colour = split half
  (**B1** blue, **B2** orange). Title prints the overall mean and the between-district SD.
* **Statistic / data source:** `n500_clustered_inference.json → district_effect`
  (`mean`, `sd_between`, and a sorted list of `{district, mean, n, half}`). CSV:
  `district, mean, n, half`.
* **How to read it:** bars to the right = the district benefits from tools; the spread
  quantifies heterogeneity.
* **What it shows:** effect **mean +0.123**, between-district **SD 0.134**, range from
  **−0.171 (Burhanpur)** to **+0.400 (Barwani)**.
* **Important caveat:** the raw B1-vs-B2 gap (+0.094, ≈ 0.70 SD) is **district-level
  composition**, not a clean "batch effect", B1 happens to draw lower-effect districts
  (Burhanpur, Dhar, …) and B2 the higher-effect remainder. The **merged** n=500 contrast is
  what is claimed. (This is the visual explanation of the N06 split-half result.)

---

## 6. Fig_N05: Per-season contrasts

**File:** `Fig_N05_season_contrasts.{pdf,png}` · **CSV:** `Fig_N05_season_contrasts.csv`

* **What it plots:** three panels (Kharif, Rabi, Zaid); in each, one row per pre-registered
  pair; a marker = clustered point estimate ± CI. **Filled** marker = `p < 0.05`;
  **hollow** = not significant. A dashed 0 line is the null.
* **Statistic / data source:** `n500_clustered_inference.json → per_season[<season>_strict_pp_sv_<pair>]`
  (`diff`, `lo`, `hi`, `p`, `k`, `n`). CSV:
  `season, pair, diff, lo, hi, p, significant, k, n`.
* **How to read it:** same as a forest plot, but sliced by season; the filled/hollow
  distinction is the within-season significance at α = 0.05.
* **What it shows (strict, PP, `sv`):**
  * **Kharif:** strong everywhere, **+0.275 / +0.250 / +0.168 / +0.142**.
  * **Rabi:** mixed, **+0.119 / −0.012 / +0.061 / −0.067**. The two negative values
    (`C2a−C1a`, `C2b−C1a`) reflect the **Rabi rainfall-channel limitation** (below).
  * **Zaid:** largest for the C1a-relative pairs, **+0.053 / +0.167 / +0.163 / +0.276**.
* **Interpretation:** the benefit is **not confined to one season**; where it weakens
  (Rabi) there is an identified mechanistic cause.

> **Rabi limitation (PROTOCOL §8.14).** Rabi-month rainfall normals are far below every
> crop's rainfall band, so the rainfall channel of `crop_score` cannot discriminate in Rabi,
> so it collapses onto temperature/soil/season/risk. This is a **scorer** limitation,
> not an LLM result; **no weights were changed.** (See `TOOLS_REFERENCE.md` §7.4.)

---

## 6b. Where the gain comes from (source of growth)

The figures imply three distinct sources of improvement, which the paper should state
explicitly:

1. **Prompt content (C0 → C0b → C1a).** Telling the model *what to consider* (C0b) and,
   more strongly, *pasting the raw evidence* (C1a) raises `sv` from 0.551 to 0.646 to 0.665
   and drops `hv` from 0.382 to 0.292. This is "more/better information in the prompt".
2. **Real tool access (C1a → C2a/C2b).** Holding the *information* roughly fixed, letting
   the model **actually call** the tools yields the largest single jump (to 0.803/0.772
   `sv`). The C2a−C1a contrast (+0.135) isolates this effect *from* information content.
3. **The deterministic scorer (C2b → C2a and C2a → C3).** Adding `crop_score` (C2b→C2a)
   and the deterministic pipeline itself (C3) squeeze out the remaining gains
   (0.772 → 0.803 → 0.863). C3 is the ceiling; C2a is close.

The **C2a − C1a** contrast is the cleanest "source of growth" statement: information held
constant, the *act of tool calling* is worth **+0.135 season validity**.

---

## 7. Fig_N06: Split-half robustness

**File:** `Fig_N06_half_contrasts.{pdf,png}` · **CSV:** `Fig_N06_half_contrasts.csv`

* **What it plots:** two panels (`C2b−C0b`, `C2b−C1a`); three rows each = **B1**, **B2**,
  **merged**. Bold marker = clustered estimate; grey whisker = naive.
* **Statistic / data source:** `n500_clustered_inference.json → per_half[...]` for each
  half, and `clustered[...]` for merged. Each block has `naive` and `cluster`
  `{diff, lo, hi, n}`. CSV mirrors N02 plus a `group` column.
* **How to read it:** an interval entirely right of 0 = the contrast holds in that
  subgroup.
* **What it shows:** the merged and **B2** contrasts are comfortably significant; the **B1**
  cell is the weak one, specifically **B1 `C2b−C1a` does not clear zero** and
  **B1 `C2b−C0b` is marginal**.
* **Interpretation:** the main effect is **not a single-batch artefact**, but heterogeneity
  is real and disclosed. Combined with Fig_N04, the B1 weakness is explained by **district
  composition**, not by a failure of the method.

---

## 8. Fig_N07: Tool LLM vs deterministic (C2a vs C3)

**File:** `Fig_N07_c2a_vs_c3.{pdf,png}` · **CSV:** `Fig_N07_c2a_vs_c3.csv`

* **What it plots:** four **stacked bars**, `sv` strict, `sv` lenient, `hv` strict,
  `hv` lenient, each split into **match** (green) / **beat** (yellow) / **lose** (orange)
  fractions of scenarios. Segments ≥5% are labelled with their percentage.
* **Statistic / data source:** the match/beat/lose counts are parsed from
  `eval/results/n500_clustered_inference.txt` (block "C2a vs C3"), via the regex in
  `n500_figures.py:_c2a_vs_c3`. CSV: `metric, spec, category, count, n, frac`.
  * **match** = `|C2a − C3| < 1e-9`; **beat** = C2a better (`sv` higher / `hv` lower);
    **lose** = C2a worse.
* **How to read it:** each bar is a category distribution over the same scenarios; higher
  green = closer to the deterministic reference.
* **What it shows:** `sv` strict ≈ **72.2% match, 2.6% better, 25.2% worse**;
  `hv` strict ≈ **79.4 / 0.4 / 20.2**; `hv` lenient ≈ **81.2 / 0.2 / 18.6**.
* **Interpretation:** the tool-using LLM **matches the deterministic pipeline on ~72–81% of
  scenarios** and is **rarely better**. Honest framing: *"the LLM adds little beyond the
  deterministic pipeline, but it is close to it and clearly better than any LLM-only
  baseline."* This figure is diagnostic (fidelity to the repo's own reference), **never** a
  claim of external correctness.

---

## 9. Robustness / using the figures together

* **The claimability gate** (STRICT × LENIENT × PP × ITT) is what makes the N02/N05/N06
  contrasts reportable; each pre-registered pair passes it.
* **Clustering** (N03) does not change any point estimate; it only widens intervals (N02).
* **Heterogeneity** is shown twice: across districts (N04) and across halves (N06).
* **Ceiling / fidelity** is N07: the tool-LLM sits just below deterministic C3.

Recommended reading order for a reader: **N01** (overview) → **N02** (is it real?) →
**N05** (in which seasons?) → **N03/N04/N06** (clustering & heterogeneity) → **N07**
(how close to the deterministic ceiling).

---

## 10. Figure → data-file map

| Figure | Primary JSON key(s) | CSV |
|---|---|---|
| N01 | `n500_primary_metrics.json → cells_WITH pilot_dev[strict_pp_*]` | `Fig_N01_condition_quality.csv` |
| N02 | `n500_clustered_inference.json → clustered[strict_pp_*]` | `Fig_N02_preregistered_forest.csv` |
| N03 | `n500_clustered_inference.json → icc[*]` | `Fig_N03_design_effect.csv` |
| N04 | `n500_clustered_inference.json → district_effect` | `Fig_N04_district_variation.csv` |
| N05 | `n500_clustered_inference.json → per_season[...]` | `Fig_N05_season_contrasts.csv` |
| N06 | `n500_clustered_inference.json → per_half[...]`, `clustered[...]` | `Fig_N06_half_contrasts.csv` |
| N07 | `n500_clustered_inference.txt` (match/beat/lose block) | `Fig_N07_c2a_vs_c3.csv` |

> If a number in a formatted figure ever disagrees with the frozen JSON/CSV, the **JSON/CSV
> is authoritative** and the figure should be regenerated with
> `python -u eval/scripts/n500_figures.py`.

---

## 10b. Reproducing the figures

```powershell
python -u eval/scripts/n500_primary_metrics.py     # -> n500_primary_metrics.{json,txt}
python -u eval/scripts/n500_clustered_inference.py # -> n500_clustered_inference.{json,txt}
python -u eval/scripts/n500_figures.py             # -> eval/figures/n500/Fig_N01..N07.{pdf,png} + data/*.csv
```

The figure script is **offline**: it needs the frozen artifacts above and makes **no API
calls**.

---

## 10a. Handoff checklist

- Headline numbers to cite: Fig_N01 (condition table) and Fig_N02 (contrasts). Strongest
  single claim: **C2a − C1a = +0.135 `sv` [+0.094, +0.176]**.
- Methods sentence for clustering: *"Because scenarios are clustered within district (51
  districts, mean 9.8 each) and the split halves are near district-disjoint, all inference
  uses a district-clustered bootstrap; every conclusion is unchanged (0/16 cells)."*
- Robustness gate: every claim passes STRICT **and** LENIENT, PP **and** ITT.
- **Do not headline:** the oracle condition (leaks the answer), "fidelity to C3" (N07 is
  diagnostic), and consistency repeats (secondary and circular).
- Always frame N07 as *"close to the repo's own deterministic pipeline"*, not external
  correctness.

---

## 11. The superseded figure sets (provenance only)

Moved to `eval/figures/archive_v1/` and **not** headline-usable. Details in
`eval/figures/SUPERSEDED.md`.

### 11.1 `archive_v1/cross_model_M/`: `Fig_M01–M10` (older naming C1/C2, partial runs)

Process / secondary questions; based on the partial cross-model run (Llama n=150, GLM
n=32). One-line meaning of each:

| Fig | Meaning |
|---|---|
| **M01** | Valid-JSON rate by model × condition |
| **M02** | Median latency by model × condition |
| **M03** | Token efficiency |
| **M04** | Tool-call usage in the tool condition |
| **M05** | "Accuracy@5 / fidelity to C3" |
| **M06** | Out-of-registry (hallucination) rate, was **0.0%** for all models |
| **M07** | Season-validity rate |
| **M08** | Per-condition gain vs C0 (Jaccard) |
| **M09** | Latency-vs-reliability trade-off |
| **M10** | Paired sample sizes |

Historical/qualitative findings retained there: prompt-strength alone (C0b) does nothing;
in that older framing "stuffing" was the biggest lever and tool calling helped less than
stuffing; hallucination rate was 0.0%; GLM was far slower.

### 11.2 `archive_v1/paper/`: `Fig01–Fig14` (first-pass deterministic figures)

Deterministic C3 behaviour, ablations, weight sensitivity, crop frequency/diversity, built
on older naming and the precursor to the pre-registered n=500 run.

### 11.3 `archive_v1/E_series/`: `Fig_E01–E06` (early deterministic set)

Legacy deterministic figures (ablation, weights sensitivity, per-season validity, crop
frequency, diversity). The E-series carries **hardcoded legacy values** (e.g. `n=8,628`)
and is superseded. For the deterministic reference numbers, use the deterministic tables in
`RESULTS_REPORT.md` §3 and the C3 row of Fig_N01.

> **Rule:** if a figure is not `Fig_N01–N07` from `eval/figures/n500/`, it is not
> headline-usable. Never mix an archive figure into the paper without flagging it.

---

*See also:* `EVAL_HARNESS_AND_SCENARIOS.md` (how the numbers were produced),
`TOOLS_REFERENCE.md` (tool internals), `SYSTEM_GUIDE.md` (runtime product).
