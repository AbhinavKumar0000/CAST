# AgroLLaMA Evaluation — Results Report

**Last updated:** 2026-10-12
**Protocol version:** 1.0.0
**Config SHA-256:** `2fe37c27…` (frozen) / runtime `87dad7a9…`
**Models evaluated:** `nvidia/nemotron-3-ultra-550b-a55b` (primary, n=500), `meta/llama-3.2-11b-vision-instruct` (small, n=150), `z-ai/glm-5.3` (secondary, partial n=32 — see limitations)

---

## 1. Executive summary

- **Deterministic pipeline (C3) is the accuracy backbone** and remains the reference: 21 distinct crops across 10,000 scenarios (51 districts, 3 seasons), 74.8% overall season validity (99.0% Kharif, 98.7% Rabi, 26.4% Zaid — Zaid is the hard stratum).
- **Evidential stuffing (C1) is the single biggest lever for LLM agreement with the deterministic pipeline.** Across all models, Jaccard agreement vs C3 rises sharply from C0 → C1 (nemotron +0.47, glm +0.41, llama +0.34). Accuracy@5 vs C3 reaches 96–99% under C1.
- **MCP tool calling (C2) is a weaker tool than stuffing** (nemotron +0.15, glm +0.12, llama +0.26 vs C0 in Jaccard), and it is fragile: the live weather API rate-limits concurrent calls, and the small Llama model sometimes never emits a final answer after tool calls (18/150 C2 failures).
- **Reliability is high but not perfect** for valid-JSON output: nemotron 95.6–98.6%, llama 84.7–100%, glm (partial) 84.4–93.8% across conditions. Crop out-of-registry (hallucination) rate is **0.0% for all three models** — no crop outside the 21-crop registry was recommended.
- **Cost/reliability:** nemotron is the best primary trade-off (26–37 s/call, ~1000–1400 tokens). llama is fast/cheap (~5 s, ~80 tokens) but weak without evidence. glm matches nemotron accuracy (+lates) but is 6–15× slower (200–420 s/call) and threw intermittent 504s.
- GLM data collection was **paused at 32/50 scenarios** (endpoint degraded to 900–2200 s/call with 504 responses). See §6 limitations.

---

## 2. Design & protocol

Five conditions on identical scenario prompts:

| Cond | Label | Setup |
|---|---|---|
| C0 | LLM-only | Raw scenario prompt |
| C0b | LLM-only strong | Scenario + strengthened elicitation |
| C1 | LLM + stuffing | Scenario + evidence stuffing (deterministic tool outputs) |
| C2 | LLM + MCP | Scenario + live tool-calling over 6 MCP tools (weather, climate, season, soil, risk, crop_score) |
| C3 | No-LLM | Deterministic crop-score pipeline (reference) |

Details:
- Scenario space: 10,000 scenarios, 51 districts of Madhya Pradesh, 3 seasons (as-of dates 2015–2025).
- Deterministic pipeline: weather/climate/season/soil/risk → crop_score (weights from repo config). Canonical evidence bundles for all 10,000 scenarios: `eval/runs/archive_v2/evidence/` (frozen v2, `as_of_date`+`week`). The `eval/runs/adhoc/evidence/` bundles are v1 provenance only.
- LLM subsets: nemotron on the full 500-scenario LLM subset; llama on the first 150 (2,000 and 600 calls). glm on the first 50 (200-call target; 128 captured).
- Provider: NVIDIA NIM (OpenAI-compatible), 4 rotating free keys, `temperature=0.2`, `max_output_tokens=4096`. Retries/exponential backoff per provider config.
- Ground truth surrogate for recommendations = deterministic C3 top-5 per scenario.
- **Clustered design.** Scenarios are clustered within district (51 districts, ~9.8 scenarios each), and the B1/B2 batches are near district-disjoint. **All inference uses district-clustered resampling** (resample districts with replacement; cluster-bootstrap p-values; Holm over the pre-registered family), not scenario-level resampling. Point estimates of the paired contrasts are unchanged; clustered 95% CIs are used throughout. See `eval/scripts/n500_clustered_inference.py` and PROTOCOL 8.29b.

---

## 3. Deterministic pipeline (C3) — reference behavior

| Metric | Value |
|---|---|
| Scenarios | 10,000 (stress 4,212 / normal 5,788) |
| Districts | 51 |
| Distinct crops | 21 |
| Shannon entropy (top-5 crop dist.) | 4.03 |
| Per-district differentiation (Jaccard distance) | 0.181 |
| Season validity overall | 74.8% (stress 54.8%, normal 89.4%) |
| Season validity — Kharif / Rabi / Zaid | 99.0% / 98.7% / **26.4%** |

Figures E01–E06 (deterministic phase): `eval/figures/Fig_E01..E06`.

**Takeaway:** validity is high except in Zaid (summer/pre-rain window), where the pipeline itself pushes crops outside their ideal season. LLM comparison is therefore most meaningful on Kharif/Rabi strata.

---

## 4. LLM cross-model results

### 4.1 Per model × condition (all collected scenarios)

`valid` = share responding with a valid JSON object; `err` = hard errors; `lat_m` = median latency (s); `tok` = mean output tokens; `tools` = mean tool calls (C2); `acc5/jac` = Accuracy@5 / Jaccard vs deterministic C3 top-5; `hallu` = out-of-registry crop rate; `season` = season-validity rate.

| Model | Cond | n | ok | valid | err | lat_m | tok | tools | acc5 | jac | hallu | season |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| nemotron | C0 | 500 | 493 | 98.6% | 0 | 26s | 1006 | 0.0 | 73.6% | 23.6% | 0.0% | 52.5% |
| nemotron | C0b | 500 | 484 | 96.8% | 0 | 37s | 1420 | 0.0 | 77.7% | 23.3% | 0.0% | 59.2% |
| nemotron | C1 | 500 | 490 | 98.0% | 0 | 33s | 1302 | 0.0 | 98.2% | 70.9% | 0.0% | 73.2% |
| nemotron | C2 | 500 | 478 | 95.6% | 0 | 34s | 865 | 5.2 | 90.8% | 38.1% | 0.0% | 49.2% |
| llama | C0 | 150 | 150 | 100.0% | 0 | 5s | 83 | 0.0 | 56.7% | 7.6% | 0.0% | 33.7% |
| llama | C0b | 150 | 150 | 100.0% | 0 | 5s | 89 | 0.0 | 63.3% | 9.3% | 0.0% | 35.2% |
| llama | C1 | 150 | 150 | 100.0% | 0 | 4s | 73 | 0.0 | 99.3% | 41.4% | 0.0% | 58.5% |
| llama | C2 | 150 | 127 | 84.7% | 18 | 26s | 439 | 5.6 | 85.7% | 33.3% | 0.0% | 46.1% |
| glm | C0 | 32 | 27 | 84.4% | 5 | 199s | 599 | 0.0 | 81.5% | 18.0% | 0.0% | 50.4% |
| glm | C0b | 32 | 27 | 84.4% | 5 | 200s | 540 | 0.0 | 85.2% | 15.8% | 0.0% | 57.2% |
| glm | C1 | 32 | 29 | 90.6% | 3 | 220s | 728 | 0.0 | 96.6% | 58.9% | 0.0% | 62.1% |
| glm | C2 | 32 | 30 | 93.8% | 2 | 422s | 558 | 5.6 | 73.3% | 30.3% | 0.0% | 45.3% |

### 4.2 Value of each condition (Jaccard vs C0)

| Model | C0b (strong prompt) | C1 (stuffing) | C2 (MCP tools) |
|---|---|---|---|
| nemotron | −0.003 | **+0.473** | +0.145 |
| llama | +0.017 | **+0.338** | +0.257 |
| glm | −0.022 | **+0.409** | +0.123 |

**Interpretation:** prompt-strength alone (C0b) does nothing. Giving the model the deterministic evidence (C1) is the dominant intervention; live MCP tool calling (C2) helps but substantially less than stuffing and costs 6–12× latency.

### 4.3 Headline significance (paired, where n ≥ 20)

| Comparison | Metric | n | Result |
|---|---|---|---|
| glm vs llama, C0 | Jaccard | 27 | med 0.125 vs 0.111, p=0.0010 (adj 0.0039), Cliff's δ −0.49 |
| glm vs llama, C0b | Jaccard | 27 | med 0.111 vs 0.111, p=0.0019 (adj 0.0077), δ −0.37 |
| glm vs llama, C1 | Jaccard | 29 | med 0.600 vs 0.429, p=0.0119 (adj 0.0474), δ −0.35 |
| nemotron vs glm, C1 | Jaccard | 29 | med 0.667 vs 0.600, p=0.0098 (adj 0.0391), δ +0.22 |
| nemotron vs llama, C2 | Jaccard | 95 | med 0.333 vs 0.286, p=0.0029 (adj 0.0147), δ +0.10 |
| Any latency comparison | — | — | p<0.001 always; GLM 6–15× slower (Cohen's d ≈ −0.7 to −1.2) |

Full table (all metrics × conditions, Holm-adjusted): `eval/results/llm_paired_stats.json`.

---

## 5. Figures

### 5a. n=500 headline + district-clustered (canonical)

`eval/figures/n500/` (PNG + PDF, 300 dpi), produced by `eval/scripts/n500_figures.py` from
`eval/results/n500_primary_metrics.json` and `eval/results/n500_clustered_inference.json`.
Full captions and numbers: `eval/report/N500_FIGURES.md`.

- **N01** strict per-protocol season validity & hard violation by condition (n=500)
- **N02** four pre-registered contrasts, district-clustered vs naive CI
- **N03** district ICC and effective sample size (design effect)
- **N04** district-level C2b−C0b effect (51 districts, B1/B2)
- **N05** per-season pre-registered contrasts
- **N06** B1 vs B2 vs merged contrasts
- **N07** per-scenario C2a-vs-C3 match/beat/lose

### 5b. Cross-model (secondary; superseded as headline)

Moved to `eval/figures/archive_v1/cross_model_M/` (PNG + PDF, 300 dpi) — see
`eval/figures/SUPERSEDED.md`:

- **M01** valid-JSON rate by model × condition
- **M02** median latency by model × condition
- **M03** output-token efficiency
- **M04** tool-call usage in C2
- **M05** Accuracy@5 vs deterministic C3
- **M06** out-of-registry (hallucination) rate
- **M07** season-validity rate
- **M08** per-condition gain vs C0 (Jaccard)
- **M09** cost (latency) vs reliability trade-off
- **M10** available paired sample sizes

Aggregates: `eval/results/llm_aggregates.json`, `eval/results/llm_condition_deltas.json`.

---

## 6. Limitations & known issues

1. **GLM-5.3 is partial (n=32, 128 calls).** Collection was paused because the NVIDIA free endpoint slowed to 900–2200 s/call with intermittent `504 Gateway Timeout` (5 of 32 scenarios have ≥1 condition missing/error). Comparisons involving glm use a 27–32 scenario paired window.
2. **llama C2 failures (18/150).** The small model repeatedly requests tool calls and stops without a final JSON ("Max tool-calling rounds reached"). Runs flagged as errors, not invalid JSON.
3. **Open-Meteo rate limiting.** C2 executes the *live* weather API through the 6 tools; concurrent workers trigger HTTP 429 and DNS failures. C2 was run at 1–2 workers; determinism of tool outputs is therefore unaffected, but wall-time is.
4. **Consistency (repeat) tests are pending** (3 repeats × 100 scenarios planned). No repeat runs are included here.
5. **Reference is the deterministic pipeline, not authoritative agronomy ground truth.** Agreement metrics measure *faithfulness to the repo's own system*, not external correctness (no ICAR-CRIDA data acquired).
6. **Zaid season** dominates season-validity shortfalls for all systems; restrict comparisons to Kharif/Rabi for sensitivity.
7. **Effective unit of replication is the district (51), not the 500 scenarios.** Scenarios are clustered within district (mean 9.8/district) and the two batches are near district-disjoint, so scenario-level CIs are anti-conservative. Season-validity ICC by district is 0.17 (C2a) and hard-violation ICC 0.24 (C2a); the design effect reaches 2.5-3.1 (effective N ~160-203 for C2a), though it is ~1.0 for the paired contrasts (shared district structure cancels). All reported inference uses district-clustered resampling (PROTOCOL 8.29b); conclusions are unchanged and all 16 claimability cells hold. The C2b-C0b "batch" gap is district-level variation (between-district SD of the effect 0.13; B1/B2 gap 0.09 = 0.70 SD), not a clean batch effect.

---

## 7. Reproduction

```powershell
# Full primary run (nemotron, 500 scenarios) — completed
$env:NVIDIA_REQUEST_TIMEOUT="600"
python -u eval/scripts/run_model.py --model nvidia/nemotron-3-ultra-550b-a55b --scenarios 500 --workers 6

# llama (150 scenarios) — completed
python -u eval/scripts/run_model.py --model meta/llama-3.2-11b-vision-instruct --scenarios 150 --workers 6 --conditions C0,C0b,C1
python -u eval/scripts/run_model.py --model meta/llama-3.2-11b-vision-instruct --scenarios 150 --workers 2 --conditions C2 --retry-errors

# glm (50 scenarios, paused) — resume with same command
python -u eval/scripts/run_model.py --model z-ai/glm-5.3 --scenarios 50 --workers 4

# Cleanup + analysis
python -u eval/scripts/finalize_results.py --run eval_llama-3.2-11b
python -u eval/scripts/analyze_cross_model.py
```

Runs are resumable: `results.json` is rewritten after every call; rerunning skips completed work and only executes the remainder.

---

## 8. Status of remaining protocol items

- [x] Deterministic C3 + ablations + sensitivity (figures E01–E06)
- [x] LLM full runs: nemotron (500×4), llama (150×4); glm partial (50×4 target, 32 done)
- [x] Cross-model analysis + figures M01–M10, aggregates JSON
- [ ] Consistency tests (3 repeats) — pending
- [ ] External ground truth (ICAR-CRIDA / data.gov.in) — not acquired
- [ ] Expert rating pass — not performed
- [ ] Paper-ready replacement text — skeleton in §4