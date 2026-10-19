# Figure Guide — LLM vs deterministic crop recommendation (MP, India)

All figures are generated from a single derived table, `eval/results/master_long.csv` (one row per
scenario × model × condition × repeat, plus C3 rows), which is itself computed **only** from existing
run outputs. No new model/API calls were made. Style: Okabe-Ito palette, **colour = condition**,
facet = model, C3 = black dashed reference, bootstrap 95% CIs, Wilson CIs for proportions, Holm-corrected
paired tests. PDF (vector) + PNG (300 dpi); every plotted number is exported to `eval/figures/paper/data/FigXX.csv`.

Metric definitions (honest names):
- **Season validity** = mean over top-5 crops of the fraction valid for the scenario's true season, using the
  independent table in `eval/metrics.py`. C3 = 0.73, not 1.0 (Zaid-dominated).
- **Overlap with C3 (Jaccard)** = set overlap of the model top-5 with the deterministic C3 top-5. This is **not**
  accuracy against human/agronomic ground truth (none exists); it measures agreement with the rule-based baseline.
- **Agreement failure** = fraction of scenarios sharing **no** crop with C3.
- **C1 caveat:** the C1 prompt contains the full deterministic C3 ranking (`CROP_SCORE`), so C1-vs-C3 is partly circular.
- **C2 caveat:** the MCP tools executed live (`season_tool`/`weather_tool` use `datetime.now`), so C2 received the
  **current** date/season, not the scenario's historical date. C2 season results are affected by this harness bug.

---

## What the data says right now (one page)

1. **Showing the model the deterministic evidence (C1) is the single biggest lever.** Jaccard overlap with C3 rises
   from 0.25→0.82 (nemotron), 0.08→0.45 (llama), 0.18→0.69 (glm); all paired differences Holm-significant
   (p<1e-4). **But C1 is partly circular** because the prompt includes the C3 ranking.
2. **Giving the model tools (C2) also helps over a bare prompt (C0)** — Jaccard +0.20/+0.27/+0.23 — **but C2 is
   clearly worse than C1** (C1−C2 = +0.38 nemotron, +0.10 llama, +0.29 glm; significant for nemotron and llama,
   marginal for glm). Tools, as run, are **not** better than simply showing the evidence.
3. **Tools do not improve season validity over a bare prompt.** C2−C0 season validity is not significant for any
   model (nemotron +0.06 Holm p=0.16; llama +0.01; glm +0.07). C2 even *lowers* Rabi accuracy because the live
   season tool reports the current season (Kharif) for historical Rabi scenarios.
4. **No crop hallucinations anywhere.** All 1,611 raw out-of-registry names were the two parenthesised canonical
   crops (`Sesame (Til)`, `Arhar (Tur)`) mis-handled by a normaliser bug, now fixed. Genuine hallucination = 0.0%.
5. **Outputs are reliable, C2 is not always compliant.** Invalid-JSON ≤4.4% everywhere; the only failures are C2
   tool-loop errors (llama 18/150 = 12%). In ~12–14% of C2 responses models made **zero** tool calls.
6. **Coverage is uneven.** nemotron n=500, llama n=150, glm n=32 (preliminary, n<100). Cross-model claims use only
   the nested paired subsets (150 or 32 scenarios).

**Biggest caveats to any paper claim:** (i) no independent ground truth — all quality numbers are agreement with a
rule-based baseline; (ii) C1 leakage; (iii) C2 live-tool date mismatch; (iv) glm is under-powered.

---

## Figures

### Fig01 — Study design schematic
![Study design](../figures/paper/Fig01_study_design.png)
**Shows:** the experimental flow — scenarios → conditions C0/C0b/C1/C2 → three LLMs → metric families, with C3
(deterministic, no LLM) as reference. **How to read:** left-to-right pipeline; C3 feeds the C1 prompt and the
reference ranking. **Key numbers:** 500 MP district-dates (150 stress), 3 LLMs, 5 conditions. **Does not show:**
model internals or tool implementations. **So what:** the design isolates prompt-only vs tools vs deterministic.

### Fig02 — Headline results
![Headline](../figures/paper/Fig02_headline.png)
**Shows:** (a) season validity, (b) Jaccard overlap with C3, (c) agreement-failure rate, by condition × model, with
C3 reference. **How to read:** higher is better in (a),(b); lower in (c); error bars = 95% bootstrap CI; black
dashed = C3. **Key numbers:** overlap C3 = 0.73 season-valid; Jaccard C1 = 0.82/0.45/0.69, C2 = 0.45/0.35/0.40,
C0 = 0.25/0.08/0.18 (nemotron/llama/glm). **Does not show:** per-scenario spread (Fig04) or significance (Fig03).
**So what:** C1 ≈ C3 on agreement; C2 sits between C1 and C0.

### Fig03 — Paired forest plot (the impact figure)
![Forest](../figures/paper/Fig03_forest_paired_diffs.png)
**Shows:** within-scenario paired differences for three contrasts (C0−C1, C0−C2, C1−C2) on two metrics, per model;
95% bootstrap CI; Holm-adjusted significance; Cliff's δ. **How to read:** point = mean difference (A−B); CI crossing
0 = not significant; labels are "A−B". **Key numbers:** Jaccard C0−C1 = −0.56/−0.38/−0.54 (all p<1e-4);
C0−C2 = −0.20/−0.27/−0.23; C1−C2 = +0.38 (p≈2e-40), +0.10 (Holm p=0.025), +0.29 (Holm p=0.056). Season validity
C2−C0 all non-significant. **Does not show:** absolute levels. **So what:** C1 dominates; C2 beats C0 but loses to C1;
C2 does not help season validity.

### Fig04 — Per-scenario overlap distribution
![Violin](../figures/paper/Fig04_per_scenario_overlap.png)
**Shows:** full distribution (violin + box + points) of Jaccard overlap with C3 per condition, faceted by model;
C3 line dashed. **How to read:** wider violin = more spread; box = IQR/median. **Key numbers:** means as Fig02;
C1 distributions are tight and high, C2 bimodal in llama/glm. **Does not show:** time or per-season structure.
**So what:** the C1 advantage is consistent, not driven by outliers.

### Fig05 — Season validity by season
![Season](../figures/paper/Fig05_season_validity_by_season.png)
**Shows:** season validity split by Kharif/Rabi/Zaid, per model, with C3 dashed per season. **How to read:**
compare colours within a season; C3 dash = deterministic per-season level. **Key numbers:** Zaid collapses for all
(≈0.12–0.24); nemotron C1 Kharif 0.90 / Rabi 0.88 / Zaid 0.24; **C2 Rabi (0.25) is far below C0 Rabi (0.68)** for
nemotron; llama C2 Rabi 0.17 vs C1 0.76. **Does not show:** why (see diagnostics: live season tool).
**So what:** the Zaid collapse is a metric/registry artifact; the C2 Rabi drop is the live-tool bug.

### Fig06 — C2 outcome breakdown
![C2 outcomes](../figures/paper/Fig06_C2_outcome_breakdown.png)
**Shows:** stacked composition of all C2 scenarios: valid+season-correct, valid+wrong-season, invalid JSON, tool
error, other error. **How to read:** proportions sum to 1 per model; counts annotated. **Key numbers:** nemotron
116 correct / 362 wrong-season / 22 invalid JSON (0 errors); llama 25/102/5 + 18 tool errors; glm 10/20 + 2 errors.
**Does not show:** C0/C1/C3 (see Fig07). **So what:** C2 rarely produces a wrong-season crop, but also rarely a
season-correct one — tools mostly return Kharif-type crops.

### Fig07 — Reliability
![Reliability](../figures/paper/Fig07_reliability.png)
**Shows:** (a) invalid-JSON failure rate, (b) API/tool failure rate, by condition × model, Wilson 95% CIs.
**How to read:** failure rates (0 best); C2 llama is the only structurally high bar. **Key numbers:** invalid JSON
≤0.044 (nemotron C2 0.044, llama C2 0.033); API failure llama C2 0.12 (18/150), glm 0.06–0.16; all C0/C0b/C1 ≈0.
**Does not show:** error causes (see diagnostics: max tool rounds, 504s). **So what:** JSON reliability is high; the
C2 tool loop is the fragile component.

### Fig08 — Efficiency
![Efficiency](../figures/paper/Fig08_efficiency.png)
**Shows:** (a) per-scenario latency (log scale, non-error), (b) output tokens, (c) tool calls, by condition × model.
**How to read:** log axis in (a); bars with 95% bootstrap CI. **Key numbers:** median latency C1: nemotron 33 s,
llama 4 s, glm 217 s; C2: 34/26/408 s. Tokens out: nemotron ~0.9–1.3k, llama 73–467, glm 594–803. Tool calls C2
≈5.2–5.6 (but ~12% zero). **Does not show:** retry/backoff breakdown. **So what:** glm is ~40× slower; C2 adds
latency and tool calls for little quality gain over C1.

### Fig09 — Cost vs quality
![Cost quality](../figures/paper/Fig09_cost_quality.png)
**Shows:** median latency (log x) vs mean Jaccard overlap (y); marker = model, colour = condition; dotted Pareto
frontier (up-left is better). **How to read:** points higher-left dominate. **Key numbers:** nemotron C1 (32 s,
0.82) and llama C1 (4 s, 0.45) are on the frontier; glm is off to the right (≥186 s). **Does not show:** CIs on the
frontier. **So what:** llama C1 gives the best quality-per-second; glm is dominated.

### Fig10 — Tool use (C2)
![Tool use](../figures/paper/Fig10_tool_use.png)
**Shows:** (a) distribution of the number of tool calls per C2 response; (b) mean overlap with C3 as a function of
tool-call count. **How to read:** (a) fractions; (b) dot + 95% CI. **Key numbers:** 0-call fraction — nemotron 14%,
llama 12%, glm 6%; for nemotron, 0-call responses overlap C3 **more** (0.68) than 6-call responses (0.42).
**Does not show:** *which* tools were called (names not recorded). **So what:** calling tools can *hurt* agreement —
consistent with the live-tool date bug.

### Fig11 — Crop frequency
![Crops](../figures/paper/Fig11_crop_frequency.png)
**Shows:** share of top-5 slots for the 15 most-used crops, per model, plus C3; Shannon entropy (H) per model.
**How to read:** cell = % of slots; rows ordered by overall frequency. **Key numbers:** C3 H≈4.03; models vary —
llama over-uses Soybean (16%)/Cotton (13%)/Wheat (14%); nemotron is flatter. **Does not show:** correctness.
**So what:** models differ in crop prior; over-concentration (low H) coincides with lower agreement (llama).

### Fig12 — Stress vs normal
![Stress](../figures/paper/Fig12_stress_vs_normal.png)
**Shows:** Jaccard overlap and season validity for stress vs normal scenarios, per condition (bars averaged over
models). **How to read:** dark = stress, light = normal, within each condition. **Key numbers:** normal Jaccard
beats stress in C1 (e.g. nemotron 0.83 vs 0.79); differences are small. Season validity drops under stress for C0b
and C2. **Does not show:** per-model CIs in-figure (exported in CSV). **So what:** stress scenarios are modestly
harder; the C2 advantage shrinks under stress.

### Fig13 — Cross-model agreement
![Cross model](../figures/paper/Fig13_cross_model_jaccard.png)
**Shows:** pairwise mean Jaccard between the top-5 of different models, per condition (nested pairs, n annotated).
**How to read:** darker = more agreement; diagonal = 1. **Key numbers:** C2 gives the most agreement (nemotron–glm
0.82, llama–glm 0.75, nemotron–llama 0.63); C0 the least (0.25–0.51). **Does not show:** agreement with C3.
**So what:** tools homogenise model outputs even when they do not improve correctness.

### Fig14 — Deterministic C3 summary (10k scenarios)
![Deterministic](../figures/paper/Fig14_deterministic_summary.png)
**Shows:** C3 behaviour over all 10,000 scenarios: (a) season validity stress vs normal, (b) by season,
(c) specificity (distinct crops, Shannon entropy, district differentiation). **How to read:** bars annotated with
n. **Key numbers:** overall 0.748; normal 0.894 vs stress 0.548; Kharif 0.990, Rabi 0.987, **Zaid 0.264**;
21 distinct crops, H=4.03, differentiation 0.181. **Does not show:** LLMs. **So what:** C3 itself is weak on Zaid
and under stress — the "reference" is not ground truth.

---

## Tables

- **T1_metrics.{csv,md,tex}** — per model × condition: n, Jaccard overlap with C3 [95% bootstrap CI], season
  validity [95% CI], any-overlap rate [Wilson CI], valid-JSON [Wilson CI]. glm rows flagged `preliminary`.
- **T2_coverage.{csv,md}** — n scenarios, valid, errors, tool-round errors, preliminary flag per model × condition.

---

## Archived v1 figures — what was wrong or misleading

Moved to `eval/figures/archive_v1/` (not deleted). Reasons:

- **Fig_M01 valid_json_rate** — computed on post-normalisation top5, so it hid the normaliser bug; and it mixed
  API errors with JSON errors. Superseded by **Fig07** (separated, Wilson CIs).
- **Fig_M02 latency** — included error/retry-inflated records in the same summary and used a linear axis, hiding
  glm's 400 s+ tail. Superseded by **Fig08(a)** (log scale, non-error only).
- **Fig_M03 tokens_out** — single bars, no CI, no input/reasoning split framing. Superseded by **Fig08(b)**.
- **Fig_M04 tool_calls** — presented the mean tool-call count without flagging that ~12–14% of C2 responses made
  **zero** calls, overstating compliance. Superseded by **Fig10(a)** (full distribution).
- **Fig_M05 agreement_c3** — used the buggy normaliser (dropped `Sesame (Til)`/`Arhar (Tur)`), deflating all
  conditions; no CIs. Superseded by **Fig02(b)** / **Fig03** (fixed metrics, CIs, paired tests).
- **Fig_M06 hallucination** — showed "0%", which was an artifact of the normaliser dropping OOV names; the true
  pre-fix rate was 6–14% but entirely the two mis-matched canonical crops. Superseded by the corrected framing in
  this guide (§What the data says, point 4).
- **Fig_M07 season_validity** — plotted a single overall mean, hiding that Zaid collapses (≈0.2) and that C2 Rabi
  collapses due to the live-tool bug. Superseded by **Fig05** (by season) and **Fig06**.
- **Fig_M08 condition_gains** — implied a monotone "more context is better" gain and did not separate the C1
  leakage from genuine gains. Superseded by **Fig03** (honest paired contrasts).
- **Fig_M09 cost_reliability** — x/y definitions unclear and mixed conditions without the C3 reference. Superseded
  by **Fig09** (explicit Pareto frontier).
- **Fig_M10 sample_size** — a bar chart of n only. Superseded by **T2** and the per-panel n labels used throughout.

Cross-cutting v1 problems: (i) no C3 reference line; (ii) lines connecting unordered categories; (iii) no CIs;
(iv) titles inside the plotting area; (v) in-figure gridlines/legends overlapping data; (vi) all metrics computed
with the buggy normaliser.
