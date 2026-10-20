# Glossary

| Term | Definition |
|------|------------|
| **MCP** | Model Context Protocol — a standardized interface for LLMs to call external tools/functions |
| **NVIDIA NIM** | NVIDIA Inference Microservices — free-tier OpenAI-compatible API endpoints for LLM inference |
| **AgroLLaMA** | The agricultural LLM system with 6 MCP tools (weather, climate, season, risk, soil, crop_score) |
| **C0** | LLM-only condition: no tools, plain prompt (district, coords, date) |
| **C0b** | LLM-only strong prompt: explicitly told to reason about soil, season, rainfall, temperature, risks |
| **C1a** | Fair stuffing: raw tool outputs + candidate crop requirements pasted into prompt (no scores/ranking) |
| **C1b** | Oracle (relabelled C1): full CROP_SCORE ranking injected into prompt — upper bound |
| **C2a** | LLM + MCP (proposed): LLM calls all 6 tools via NVIDIA function calling |
| **C2b** | LLM + MCP (no scorer): LLM calls 5 tools (excludes crop_score) |
| **C3** | No-LLM deterministic: weighted scorer only, time-anchored, run on all 10,000 scenarios |
| **C3t** | Instrument-corrected C3: identical pipeline but passes real sowing windows to `_season_alignment_score` |
| **PP (Per-Protocol)** | Analysis excluding responses with invalid/truncated JSON |
| **ITT (Intention-to-Treat)** | All planned scenario-runs enter; invalid/truncated = season_validity=0, hard_violation=1 |
| **STRICT** | UNVERIFIED ground-truth rows counted as invalid |
| **LENIENT** | UNVERIFIED ground-truth rows excluded from denominator |
| **Season Validity** | Fraction of crops in top-5 valid for the scenario's season (per-crop check, mean over scenarios) |
| **Hard Violation** | Per-crop check against season/drought/flood constraints; rate = violations / (5 × n_scenarios) |
| **Precision@5** | \|model top-5 ∩ reference top-5\| / min(5, \|reference top-5\|) |
| **nDCG@5** | DCG@5 / IDCG@5 with binary gain (1 if crop in reference top-5) |
| **Recall@5** | \|model top-5 ∩ reference top-5\| / min(5, \|reference top-5\|) |
| **Stale@5** | \|top5 ∩ D\| / \|D\| where D = newly infeasible crops (F0 \ F1) |
| **Violation@5** | \|top5 ∩ ¬F1\| / min(5, \|top5\|) — crops not feasible under perturbed conditions |
| **Shift@5** | 1 − Jaccard(top5_base, top5_perturbed) |
| **Exposure** | Baseline top-5 intersects D (newly infeasible set) |
| **Retention** | \|base_top5 ∩ D ∩ shifted_top5\| / \|base_top5 ∩ D\| over exposed cells |
| **Delta-Violation** | Violation@5(shift) − Violation@5(baseline) |
| **Bootstrap CI** | 95% confidence interval via 10,000 resamples (district-clustered where specified) |
| **Holm–Bonferroni** | Multiple comparison correction across a family of contrasts |
| **Cliff's δ** | Non-parametric effect size for ordinal/continuous outcomes |
| **R_prim** | Headline real-data reference: 2015-16..2022-23 mean area, registry-restricted top-5 |
| **R_full** | Sensitivity reference: 2015-16..2024-25 mean area, registry-restricted |
| **R_all** | Sensitivity reference: 2015-16..2022-23 mean area, ALL crops (no registry restriction) |
| **R_prod** | Sensitivity reference: 2015-16..2022-23 mean production, registry-restricted |
| **DB_v1** | Original crop_log.csv (21 crops) |
| **DB_v2** | Updated crop_log_v2.csv (22 crops: added Linseed) |
| **Frozen Grid** | `eval/runs/archive_v2/deterministic/*.json` — C3 outputs with time-anchored evidence |
| **Adhoc Bundles** | `eval/runs/adhoc/evidence/` — v1 provenance, superseded by frozen grid |
| **S-Series** | Simulated scenario study: perturbed weather cache + fixed oracle, no model retraining |
| **Perturbation Sets** | W1/W2/W3 (warming), D1/D2 (dry spells), WET1/WET2 (heavy rain), O1/O2 (onset), C1 (compound), N0/N1 (controls), NE15 (2015 replay) |
| **Oracle** | Offline feasible set from hard_constraints + crop_season_table (STRICT primary) |
| **|D|>0 (Conditional)** | Analysis restricted to cells where oracle feasible set changed |
| **|D|=0 (As-Scored)** | Analysis with |D|=0 cells scored as 0 (registered convention) |

---

## Acronyms

| Acronym | Expansion |
|---------|-----------|
| LLM | Large Language Model |
| MCP | Model Context Protocol |
| NIM | NVIDIA Inference Microservices |
| DES | Directorate of Economics & Statistics |
| MoA&FW | Ministry of Agriculture & Farmers' Welfare |
| UPAG | Unified Portal for Agricultural Statistics |
| ICAR-CRIDA | Indian Council of Agricultural Research - Central Research Institute for Dryland Agriculture |
| SLBC-MP | State Level Bankers' Committee - Madhya Pradesh |
| GADM | Global Administrative Areas Database |
| ERA5-Land | ECMWF Reanalysis v5 - Land component |
| SPI | Standardized Precipitation Index |
| OOV | Out-Of-Vocabulary |
| PP | Per-Protocol |
| ITT | Intention-to-Treat |
| CI | Confidence Interval |
| ICC | Intraclass Correlation Coefficient |
| DEFF | Design Effect |
| ESS | Effective Sample Size |
| MDD | Minimum Detectable Difference |