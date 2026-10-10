# AgroLLaMA — MCP Server + Publication-Grade Evaluation Framework

**A standards-compliant Model Context Protocol server for location-aware agricultural intelligence in Madhya Pradesh, with a complete evaluation suite for the paper "Domain-Adaptive LLM with Model Context Protocol (MCP) for Intelligent Decision Support in Precision Agriculture".**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-1.13%2B_streamable--http-6366f1?logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48Y2lyY2xlIGN4PSI4IiBjeT0iOCIgcj0iOCIgZmlsbD0iIzYzNjZmMSIvPjwvc3ZnPg==)](https://modelcontextprotocol.io)
[![FastMCP](https://img.shields.io/badge/FastMCP-server-8b5cf6)](https://github.com/jlowin/fastmcp)
[![FastAPI](https://img.shields.io/badge/FastAPI-2.0-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![NVIDIA NIM](https://img.shields.io/badge/NVIDIA_NIM-free-76B900?logo=nvidia&logoColor=white)](https://www.nvidia.com/en-us/nim/)
[![GeoPandas](https://img.shields.io/badge/GeoPandas-1.0%2B-2E7D32)](https://geopandas.org)
[![SciPy](https://img.shields.io/badge/SciPy-SPI--1_Drought-8CAE4D)](https://scipy.org)
[![Region](https://img.shields.io/badge/Region-Madhya_Pradesh,_India-FF6F00)](https://en.wikipedia.org/wiki/Madhya_Pradesh)
[![Status](https://img.shields.io/badge/Status-Research_Prototype-orange)](https://github.com)
[![License](https://img.shields.io/badge/License-MIT-blue)](LICENSE)

---

> **AgroLLaMA** is an MCP server that exposes six deterministic agricultural intelligence tools over the Model Context Protocol. Any MCP-compatible client -- Claude Desktop, Cursor, a custom NVIDIA NIM orchestrator, or a raw Python script -- can connect and receive real weather, climate, soil, seasonal, risk, and crop-scoring data for any field coordinate in Madhya Pradesh. On top of the tool server, a FastAPI application drives an LLM reasoning loop that collects the full evidence bundle and synthesises a location-aware crop recommendation for the farmer.
>
> **NEW**: This repo now includes `eval/` — a complete, publication-grade evaluation framework comparing LLM-only vs LLM+MCP tool use across 10,000 scenarios, with deterministic ablations, bootstrap statistics, and 17+ figures.

```
                         MCP streamable-http :8001/mcp
                        /
Claude Desktop --------+
Cursor         --------+----> FastMCP Server ----> weather_tool
Custom client  --------+      (port 8001)      --> climate_tool
                        |                       --> season_tool
Browser / curl --> FastAPI (port 8000)         --> risk_tool  [SPI-1]
                     |                          --> soil_tool  [R-tree]
                     v                          --> crop_score [weighted fusion]
                  NVIDIA NIM LLM
                  (MCP client + planner)
```

---

## What's in this Repository

| Component | Path | Description |
|-----------|------|-------------|
| **MCP Tool Server** | `mcp_server/` | 6 tools: weather, climate, season, risk, soil, crop_score |
| **FastAPI Orchestrator** | `app/` | HTTP API, web UI, LLM client |
| **Evaluation Framework** | `eval/` | **Complete evaluation suite (NEW)** |
| **Data** | `data/` | District boundaries, soil table, crop registry |

### Evaluation Framework (`eval/`) — NEW

```
eval/
├── PROTOCOL.md           # Frozen experimental protocol (v1.0.0)
├── PROGRESS.md           # Task checklist with timestamps
├── REPO_AUDIT.md         # 15 discrepancies: paper claims vs repo reality
├── config.yaml           # Frozen config (SHA256: 87dad7a9)
├── scenarios.py          # 10,000 stratified scenarios generator
├── weather_cache.py      # Bulk Open-Meteo archive (1 request/district)
├── evidence.py           # Hindcast evidence pipeline (reproducible)
├── metrics.py            # Unit-tested metric functions
├── statistics.py         # Bootstrap CIs, Wilcoxon, McNemar, Cliff's δ
├── status.py             # `make status` / `make watch` progress tracking
├── llm/
│   ├── nvidia_provider.py  # NVIDIA NIM OpenAI-compatible client
│   └── prompts.py          # C0, C0b, C1, C2 prompt builders
├── scripts/
│   ├── fetch_nvidia_models.py   # Model discovery from /v1/models
│   ├── smoke_test_models.py     # 14 candidates tested
│   ├── analyze_deterministic_full.py  # C3 + ablations on 10k
│   └── generate_figures.py      # Figures E01-E06
├── models/
│   ├── models.yaml      # Machine-readable model registry
│   └── MODELS.md        # Human-readable model documentation
├── data/
│   ├── scenarios.jsonl  # 10,000 scenarios
│   ├── stress.jsonl     # 4,212 stress scenarios
│   └── llm_subset.jsonl # 500 LLM scenarios (150 stress)
├── runs/adhoc/
│   ├── evidence/        # 10,000 evidence bundles
│   └── deterministic/   # 10,000 C3 + ablation results
├── results/             # JSON/CSV aggregates
└── figures/             # Fig_E01-E06 (PNG@300dpi + PDF)
```

### Evaluation Status (as of 2026-10-10)

| Phase | Status | Details |
|-------|--------|---------|
| **Audit & Protocol** | ✅ Done | 15 discrepancies documented; protocol frozen |
| **Scenarios & Weather** | ✅ Done | 10k scenarios, 51 districts cached, 10k evidence bundles |
| **Stress Set** | ✅ Done | 4,212 scenarios (drought/heat/flood thresholds) |
| **LLM Subset** | ✅ Done | 500 scenarios (stratified, 150 stress) |
| **Deterministic C3** | ✅ Done | 10,000 scenarios × 7 ablations + 10 weight sensitivities |
| **Figures E01-E06** | ✅ Done | Ablation, sensitivity, season validity, crop freq, diversity |
| **Model Discovery** | ✅ Done | 80 NVIDIA NIM models fetched, 14 smoke-tested |
| **Selected Models** | ✅ Done | 3 models from 3 families (Nemotron, GLM, Llama) |
| **Quota Probe** | 🔄 In Progress | ~3 min/model, concurrency 2-3 |
| **Pilot Run** | ⏳ Pending | 30 scenarios × 4 conditions × 3 models |
| **Full LLM Runs** | ⏳ Pending | Primary 500×4, others 150×4 (sequential) |
| **Cross-Model Figs** | ⏳ Pending | Fig_M01-M10 |
| **Final Report** | ⏳ Pending | RESULTS_REPORT.md + .docx |

---

## Quick Start

### Prerequisites
- Python 3.10+
- NVIDIA API key (for LLM evaluation): `$env:NVIDIA_API_KEY="nvapi-..."`
- GeoPandas (conda recommended on Windows): `conda install -c conda-forge geopandas`

### Installation
```bash
git clone https://github.com/AbhinavKumar0000/CAST.git
cd CAST
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Run the MCP Server + FastAPI
```bash
# Terminal 1: MCP server
python -m mcp_server.server

# Terminal 2: FastAPI (with auto-start MCP)
uvicorn app.main:app
# Web UI: http://127.0.0.1:8000/ui
# API:    http://127.0.0.1:8000/analyze
```

### Evaluation Commands
```bash
# Check status
make status
make watch          # Live progress (refreshes every 5s)

# Generate scenarios (already done)
make scenarios

# Fetch weather archive (already done for 51 districts)
make weather

# Run deterministic C3 + ablations (already done)
make deterministic

# Generate figures (already done)
make figures

# Run quota probe (in progress)
python eval/scripts/simple_quota.py

# After pilot approval: full LLM runs
make pilot          # 30 scenarios × 4 conditions × 3 models
make llm-run        # Full runs (resumable, checkpointed)

# Full analysis & report
make analyze
make figures
make report
```

---

## System Architecture (AgroLLaMA MCP Server)

### Two-Process Design

```
Process 1 -- FastAPI (port 8000)
+------------------------------------------+
|  app/main.py         HTTP + lifespan      |
|  app/orchestrator.py LLM loop bridge      |
|  app/llm/            MCP client + NVIDIA  |
|  app/schemas/        Pydantic contracts   |
|  app/static/         Browser UI           |
+------------------+-----------------------+
                   | MCP streamable-http
                   | POST http://127.0.0.1:8001/mcp
                   v
Process 2 -- FastMCP server (port 8001)
+------------------------------------------+
|  mcp_server/server.py   6 @mcp.tool()    |
|  mcp_server/weather_tool.py              |
|  mcp_server/climate_tool.py              |
|  mcp_server/season_tool.py               |
|  mcp_server/risk_tool.py                 |
|  mcp_server/soil_tool.py                 |
|  mcp_server/crop_score_tool.py           |
|  mcp_server/open_meteo_client.py         |
+------------------------------------------+
          |               |            |
    Open-Meteo API    mp_districts   soil_fixed.json
    (forecast +       .geojson      crop_log.csv
     archive)
```

### The Six MCP Tools

| Tool | Source | Purpose |
|------|--------|---------|
| `weather_tool` | Open-Meteo forecast (7d past + 7d forecast) | Short-horizon weather summary |
| `climate_tool` | Open-Meteo archive (2014-2023) | 10-year climate normals |
| `season_tool` | IST calendar | Kharif/Rabi/Zaid season |
| `risk_tool` | Open-Meteo (30d past + archive 2019-2023) | SPI-1 drought, heatwave, flood |
| `get_soil_by_coordinates` | GADM boundaries + CGWB soil data | District soil intelligence |
| `crop_score` | All above + crop_log.csv | Deterministic weighted crop ranking |

---

## Evaluation Protocol Summary

The evaluation compares **5 conditions** across **3 LLM models**:

| Condition | Tools | Prompt | Purpose |
|-----------|-------|--------|---------|
| **C0** | None | Minimal | LLM-only baseline |
| **C0b** | None | Strong | Best fair LLM-only baseline |
| **C1** | Context stuffing | Standard | LLM + evidence (no function calling) |
| **C2** | MCP function calling | Standard | **Proposed: LLM + tools** |
| **C3** | Deterministic only | — | No-LLM reference |

**Key metrics**: Accuracy@5, Precision@5, Recall@5, nDCG@5, MRR (vs external GT); season validity rate; hard-violation rate; hallucination rate; crop diversity (entropy, per-district differentiation); consistency (Jaccard, Kendall τ); latency/tokens/cost.

**Statistics**: Bootstrap 95% CIs (10k resamples), paired Wilcoxon/McNemar with Holm-Bonferroni, Cliff's δ & Cohen's d effect sizes.

**Models selected**:
1. **PRIMARY**: `nvidia/nemotron-3-ultra-550b-a55b` (Nemotron 3 Ultra, 550B)
2. **SECOND_FAMILY**: `z-ai/glm-5.3` (GLM 5.3, different family)
3. **SMALL**: `meta/llama-3.2-11b-vision-instruct` (Llama 3.2 11B, fastest)

All run via NVIDIA NIM free endpoints (`https://integrate.api.nvidia.com/v1`), temperature 0.2, max_tokens 512.

---

## Known Limitations (from REPO_AUDIT.md)

1. **51 districts** in boundary/soil data (GADM v4.1), not 55 — MP has 55 official districts; newer ones missing
2. **No external ground truth** yet — crop_log.csv is the only registry (circular if used as GT)
3. **Hindcast evaluation** — "next 7 days" are observed archive values, not true forecasts
4. **Free-tier NVIDIA NIM** — non-version-locked, may change/disappear; rate limits ~40 req/min account-wide
5. **Soil types** — only `dominant_soil` populated; `soil_types` arrays are empty
6. **Single LLM family** — only NVIDIA NIM models tested (no GPT/Claude/Gemini comparison)

---

## License

MIT — see [LICENSE](LICENSE).