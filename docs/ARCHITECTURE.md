# System Architecture

## Overview

This document describes the architecture of the AgroLLaMA MCP Evaluation Framework — a system for evaluating whether giving a general-purpose LLM access to agricultural tools via the Model Context Protocol (MCP) improves crop recommendations for farmers in Madhya Pradesh, India.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EVALUATION ORCHESTRATOR                             │
│  (eval/scripts/run_model.py, run_s_series.py, run_deterministic_v2.py)     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────┐           ┌───────────────┐           ┌───────────────┐
│  LLM PROVIDER │           │  TOOL RUNTIME │           │ DETERMINISTIC │
│  (NVIDIA NIM) │           │  (TimeAnchored)│          │    SCORER     │
└───────────────┘           └───────────────┘           └───────────────┘
        │                           │                           │
        │                    ┌──────┴──────┐                   │
        │                    ▼             ▼                   │
        │            ┌─────────────┐  ┌─────────────┐         │
        │            │  WEATHER    │  │  CLIMATE    │         │
        │            │  (Open-Meteo│  │  (Normals)  │         │
        │            │   Archive)  │  │             │         │
        │            └─────────────┘  └─────────────┘         │
        │                    │             │                   │
        │            ┌─────────────┐  ┌─────────────┐         │
        │            │   SEASON    │  │    RISK     │         │
        │            │   (IST)     │  │ (Drought/   │         │
        │            │             │  │  Flood/Heat)│         │
        │            └─────────────┘  └─────────────┘         │
        │                    │             │                   │
        │            ┌─────────────┐  ┌─────────────┐         │
        │            │    SOIL     │  │  CROP_SCORE │         │
        │            │  (District) │  │  (Scorer)   │         │
        │            └─────────────┘  └─────────────┘         │
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    ▼
                    ┌───────────────────────────┐
                    │      RESULTS STORE        │
                    │  (eval/runs/...,          │
                    │   eval/results/...)       │
                    └───────────────────────────┘
```

---

## Core Components

### 1. Evaluation Orchestrator (`eval/scripts/`)

| Script | Purpose |
|--------|---------|
| `run_model.py` | Main LLM evaluation runner: resumable, chunked, multi-worker, cached |
| `run_s_series.py` | S-series runner: perturbed evidence, isolated namespaces |
| `run_deterministic_v2.py` | C3 + ablations on 10k scenarios, time-anchored |
| `score_s.py` | S-series scoring: Stale@5, Violation@5, Shift@5 |
| `c3t_recompute.py` | C3t instrument correction (PROTOCOL 8.35) |
| `analyze_*.py` | Metric computation, contrasts, figures |

**Key properties:**
- **Resumable**: Atomic writes, cache keyed by `hash(model, condition, prompt, sid, repeat)`
- **Budget-aware**: UTC-day HTTP budget enforced per API key account
- **Cached**: SQLite + file cache; successful calls never repeated
- **Deterministic**: Fixed seeds, frozen protocol, registered outputs

### 2. LLM Provider (`eval/llm/nvidia_provider.py`)

- **Endpoint**: `https://integrate.api.nvidia.com/v1` (OpenAI-compatible)
- **Auth**: Multiple API keys via `NVIDIA_API_KEY_1..4` or `NVIDIA_API_KEYS` (round-robin)
- **Model**: `nvidia/nemotron-3-ultra-550b-a55b` (PRIMARY), `meta/llama-3.2-11b-vision-instruct` (SMALL)
- **Params**: temp=0.2, top_p=1.0, max_tokens=4096 (8192 for tool conditions)
- **Tool calling**: Parallel function calling via OpenAI `tools` schema
- **Harness fix** (PROTOCOL 8.10): Unknown tool errors, stall fallback (round 12), `FINAL_JSON_ONLY`

### 3. Tool Runtime (`eval/time_anchored.py`, `eval/mcp_runtime.py`)

| Runtime | Description |
|---------|-------------|
| `ToolRuntime` (in-process) | Direct function calls, time-anchored clock, cached weather |
| `McpToolRuntime` (MCP transport) | Real MCP client → `eval/mcp_eval/server.py` (streamable-HTTP) |

**Time Anchoring (PROTOCOL 8.2):**
- Clock frozen to scenario `as_of_date` 12:00 IST
- Weather/climate/risk sliced from per-district Open-Meteo archive cache
- No live API calls, no `datetime.now()`, no look-ahead

**Equivalence (PROTOCOL 8.21):** MCP transport produces byte-identical model-visible payloads (300/300 calls).

### 4. Deterministic Scorer (`eval/scripts/run_deterministic_v2.py`)

**Pipeline:**
```
Evidence (weather, climate, season, soil, risk)
        │
        ▼
Crop Registry (crop_log.csv / crop_log_v2.csv)
        │
        ▼
Component Scores:
  • Rainfall Match (0.20)     — seasonal rainfall vs crop requirement
  • Temperature Match (0.15)  — current temp vs crop requirement  
  • Soil Match (0.20)         — dominant soil vs crop soil type
  • Season Alignment (0.30)   — sowing window vs current week
  • Risk Penalty (0.15)       — drought/flood/heat probability × sensitivity
        │
        ▼
Weighted Sum → Rank → Top-5
```

**C3 vs C3t:**
- **C3** (registered): Empty sowing windows → season alignment defaults to 0.75 (in-season)
- **C3t** (corrected): Real `sowing_start_week`/`sowing_end_week` passed to `_season_alignment_score`

### 5. Evidence Pipeline (`eval/time_anchored.py`)

```
Scenario (district, point, as_of_date)
        │
        ▼
TimeAnchoredBuilder
        │
        ├─► Weather: Open-Meteo archive [as_of-7d .. as_of+6d] (hindcast)
        ├─► Climate: Normals [2014-01-01 .. as_of-1d] (no look-ahead)
        ├─► Season: IST clock at as_of_date → Kharif/Rabi/Zaid
        ├─► Soil: GADM polygon → district → soil metadata
        └─► Risk: SPI-1 (30d), flood_probability, heatwave_probability
        │
        ▼
Evidence Bundle (JSON, cached per scenario)
```

---

## Data Flow

### LLM Evaluation Flow (C0/C0b/C1a/C1b/C2a/C2b)

```
1. Scenario Selection
   └─► llm_subset.jsonl (500) or stress subset (4,212)
   
2. Evidence Building (C1a/C1b/C2a/C2b)
   └─► TimeAnchoredBuilder.build(scenario) → evidence bundle
   
3. Prompt Construction
   └─► prompt_c0/c0b/c1a/c1b/c2(scenario, evidence, tools)
   
4. LLM Call (NvidiaProvider.run)
   ├─► Build tool schemas (C2a: 6 tools, C2b: 5 tools)
   ├─► Round-robin API key selection
   ├─► POST /chat/completions with retries/backoff
   ├─► Tool calling loop (max 15 rounds)
   │   ├─► Execute tool via ToolRuntime (time-anchored)
   │   ├─► Handle unknown tools → error + FINAL_JSON_ONLY
   │   └─► Stall fallback at round 12 → forced final
   └─► Parse JSON output → {"top5": [...], "explanation": "..."}
   
5. Caching & Storage
   ├─► Cache key = SHA256(model|cond|prompt|sid|repeat)
   ├─► Atomic write to eval/cache/llm/<model>/
   └─► Append to eval/runs/eval_<model>/results.json
```

### Deterministic Flow (C3)

```
1. All 10,000 scenarios
2. TimeAnchoredBuilder.build(scenario) → evidence bundle
3. score_crops(evidence, weights, week) for each ablation
4. Store in eval/runs/archive_v2/deterministic/<sid>.json
5. Analyze: season validity, hard violation, diversity, ablations
```

### S-Series Flow

```
1. Base 40 scenarios (eval/results/s_base_set.json)
2. For each perturbation set (W1, D1, WET1, ...):
   a. PerturbedTimeAnchoredBuilder(set_name).build(scenario)
   b. Run C1a/C2a/C2b via run_s_series.py
   c. Store in eval/runs/s_<set>/eval_<model>/results.json
3. Score with Oracle (hard_constraints + crop_season_table)
4. Metrics: Stale@5, Violation@5, Shift@5, Exposure, Retention
```

---

## Configuration

**Single source:** `eval/config.yaml` (FROZEN, SHA256 stamped in every result)

Key sections:
- `paths` — all directory roots (relative, no absolute paths)
- `model` — provider, name, temperature, token caps, tool rounds
- `cost_control` — budget, concurrency, retries, cache
- `scenarios` — generation params, stress rules, subset
- `ablations` — tool ablations, weight sensitivity
- `statistics` — bootstrap, CI, tests, effect sizes

---

## Output Structure

```
eval/
├── results/                    # Registered outputs (frozen, never edited)
│   ├── n500_primary_metrics.json
│   ├── n500_clustered_inference.json
│   ├── real_eval.json
│   ├── s_scores.json
│   ├── c3t_archive.json
│   └── ...
├── runs/                       # Raw run logs (gitignored)
│   ├── eval_nemotron-3-ultra/         # C1a/C2a/C2b × 150 (B1)
│   ├── eval_nemotron-3-ultra_b2/      # C1a/C2a/C2b × 350 (B2)
│   ├── eval_llama-3.2-11b/            # All conditions × 150
│   ├── s_W1/eval_nemotron-3-ultra/    # S-series per set
│   └── ...
├── cache/
│   ├── llm/                      # LLM call caches (per model, transport)
│   └── weather/                  # Open-Meteo per-district archives
└── data/
    ├── scenarios.jsonl
    ├── stress.jsonl
    ├── llm_subset.jsonl
    └── ground_truth/
```

---

## Reproducibility Guarantees

1. **Frozen Protocol** — PROTOCOL.md v2.0 registered before any v2 results
2. **Config SHA256** — Stamped in every results file
3. **Git Commit** — Every run records `git_commit` 
4. **Deterministic Evidence** — Time-anchored, cached weather, no live calls
5. **Atomic Caching** — Cache key includes model, condition, prompt, scenario, repeat
6. **Registered Outputs** — `eval/results/*.json` never edited after registration
7. **Figure Scripts** — Read ONLY from `eval/results/`, write to `figures/out/`

---

## Diagram Files (Copied to docs/diagrams/)

The following architecture diagrams from the original repo should be copied unchanged to `docs/diagrams/`:
- `docs/diagrams/architecture.svg` — System overview (this document)
- `docs/diagrams/data_flow.svg` — Evidence → LLM → Results
- `docs/diagrams/tool_runtime.svg` — ToolRuntime vs McpToolRuntime
- `docs/diagrams/time_anchoring.svg` — Clock injection + weather slicing
- `docs/diagrams/deterministic_pipeline.svg` — Scorer component breakdown
- `docs/diagrams/s_series.svg` — Perturbation → Oracle → Metrics

> Note: If the original diagrams don't exist as files, they are described textually above.