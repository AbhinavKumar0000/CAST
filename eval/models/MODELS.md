# NVIDIA NIM Models Registry

Generated: 2026-10-10T03:45:00Z
Base URL: https://integrate.api.nvidia.com/v1
API Key: from NVIDIA_API_KEY env var (never logged)

## All Tested Candidates (from /v1/models + smoke tests)

| Model ID | Family | Plain Access | Tool Calls | Tool Success | Valid JSON | Median Latency (s) | Status | Rejection Reason |
|---|---|---|---|---|---|---|---|---|
| nvidia/nemotron-3-ultra-550b-a55b | NVIDIA Nemotron | ✓ | 1 (weather only) | ✓ | ✓ | 15.6 / 4.8 | **SELECTED - PRIMARY** | — |
| nvidia/nemotron-3-super-120b-a12b | NVIDIA Nemotron | ✓ | 1 (weather only) | ✓ | ✓ | 6.1 / 1.9 | **SELECTED - SAME FAMILY** | Not from different family |
| nvidia/nemotron-3-nano-omni-30b-a3b-reasoning | NVIDIA Nemotron | Not tested | — | — | — | — | Rejected | Reasoning model, not instruct |
| nvidia/llama-3.1-nemotron-70b-instruct | NVIDIA Nemotron | ✗ (403) | — | — | — | — | Rejected | Not accessible (partner-only) |
| nvidia/llama-3.1-nemotron-ultra-253b-v1 | NVIDIA Nemotron | ✗ (403) | — | — | — | — | Rejected | Not accessible (partner-only) |
| z-ai/glm-5.3 | Z.ai GLM | ✓ | 6 (all tools) | ✓ | ✓ | 57.2 / 21.1 | **SELECTED - SECOND FAMILY** | — |
| meta/llama-3.2-11b-vision-instruct | Meta Llama | ✓ | 6 (all tools) | ✓ | ✓ | 11.2 / 15.8 | **SELECTED - SMALL/THIRD FAMILY** | — |
| meta/llama-3.2-90b-vision-instruct | Meta Llama | ✗ (timeout) | — | — | — | — | Rejected | Timeout |
| moonshotai/kimi-k2.6 | Moonshot Kimi | ✗ (403) | — | — | — | — | Rejected | Not accessible |
| moonshotai/kimi-k3 | Moonshot Kimi | ✗ (timeout) | — | — | — | — | Rejected | Timeout |
| deepseek-ai/deepseek-v4.1-flash | DeepSeek | ✗ (timeout) | — | — | — | — | Rejected | Timeout |
| mistralai/mistral-large-2-instruct | Mistral | ✗ (403) | — | — | — | — | Rejected | Not accessible |
| meta/llama-guard-4-12b | Meta Llama | ✗ (timeout) | — | — | — | — | Rejected | Timeout |

## Selected Models for Benchmark

### 1. PRIMARY: nvidia/nemotron-3-ultra-550b-a55b
- **Family**: NVIDIA Nemotron 3 Ultra
- **Parameters**: 550B total, 55B active (per metadata)
- **Context**: 128K (typical for Nemotron 3 Ultra)
- **Max Output**: 4096 (default, capped to 512 in config)
- **Reasoning**: No (instruct mode)
- **Tool Calling**: ✓ (single parallel call observed)
- **Access**: Free NVIDIA NIM endpoint
- **Measured Latency**: ~15s plain, ~5s tool
- **Selection Reason**: Largest accessible model, passes reliability thresholds

### 2. SECOND_FAMILY: z-ai/glm-5.3
- **Family**: Z.ai GLM
- **Parameters**: Unknown (not in metadata)
- **Context**: 128K (typical for GLM)
- **Max Output**: 8192 (default, capped to 512)
- **Reasoning**: No (instruct mode)
- **Tool Calling**: ✓ (6 sequential calls - all tools)
- **Access**: Free NVIDIA NIM endpoint
- **Measured Latency**: ~57s plain, ~21s tool
- **Selection Reason**: Different family, calls all 6 tools correctly

### 3. SMALL/THIRD_FAMILY: meta/llama-3.2-11b-vision-instruct
- **Family**: Meta Llama 3.2
- **Parameters**: 11B (vision instruct)
- **Context**: 128K (typical for Llama 3.2)
- **Max Output**: 4096 (default, capped to 512)
- **Reasoning**: No (instruct mode)
- **Tool Calling**: ✓ (6 sequential calls - all tools)
- **Access**: Free NVIDIA NIM endpoint
- **Measured Latency**: ~11s plain, ~16s tool
- **Selection Reason**: Different family, fastest passing model, calls all tools

## Common Configuration (ALL SELECTED MODELS)
- **Provider**: nvidia (NVIDIA NIM)
- **Base URL**: https://integrate.api.nvidia.com/v1
- **Temperature**: 0.2
- **Top-p**: 1.0
- **Max Output Tokens**: 512
- **Thinking/Reasoning**: Disabled (instruct modes used)
- **Concurrency**: 2
- **Rate Limit**: 12 req/min (70% of measured ~17 req/min)
- **Retry**: Exponential backoff 2-60s with jitter

## Rejected Models Summary

| Model | Reason |
|---|---|
| nvidia/llama-3.1-nemotron-70b-instruct | 403 Forbidden (partner-only) |
| nvidia/llama-3.1-nemotron-ultra-253b-v1 | 403 Forbidden (partner-only) |
| nvidia/nemotron-3-nano-omni-30b-a3b-reasoning | Reasoning model, not suitable for structured output |
| moonshotai/kimi-k2.6 | 403 Forbidden (partner-only) |
| moonshotai/kimi-k3 | Timeout (>60s) |
| deepseek-ai/deepseek-v4.1-flash | Timeout (>60s) |
| mistralai/mistral-large-2-instruct | 403 Forbidden (partner-only) |
| meta/llama-3.2-90b-vision-instruct | Timeout (>60s) |
| meta/llama-guard-4-12b | Timeout (>60s) |

## Caveats
- All models are free-tier NVIDIA NIM endpoints, may change or disappear without notice
- Models are non-version-locked; behavior may drift over time
- Do not send private/sensitive data to these endpoints
- Rate limits are account-wide (~40 req/min); models run sequentially
- Tool calling behavior varies: Nemotron models make fewer parallel calls, GLM/Llama make sequential calls
- This evaluation uses hindcast weather (Open-Meteo archive reanalysis)
- Ground truth is partially circular (crop_log.csv registry)