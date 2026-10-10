# Quota Probe Results (2026-10-10)

**Base URL**: https://integrate.api.nvidia.com/v1  
**Test**: 3 requests per model, simple JSON prompt, temperature 0.2, max_tokens 100  
**Note**: These are preliminary measurements; full 3-min probe recommended before full runs.

## Latency Summary

| Model | Short Name | Requests | Median Latency (s) | Notes |
|-------|------------|----------|-------------------|-------|
| nvidia/nemotron-3-ultra-550b-a55b | nemotron-3-ultra | 3 | 4.6 | Fast, variable |
| z-ai/glm-5.3 | glm-5.3 | 3 | 2.8 | Fastest, consistent |
| meta/llama-3.2-11b-vision-instruct | llama-3.2-11b | 3 | 4.1 | Consistent |

**All three models accessible, no 429/403 errors in 9 requests.**

## Estimated Sustainable Rate (Conservative)

Based on median latency + overhead:
- nemotron-3-ultra: ~10 req/min (6s avg)
- glm-5.3: ~15 req/min (4s avg) 
- llama-3.2-11b: ~12 req/min (5s avg)

**Account-wide limit ~40 req/min** → run sequentially, concurrency 2-3.

## Full Run Time Estimate

| Model | Scenarios | Conditions | Est. API Calls | Est. Hours |
|-------|-----------|------------|----------------|------------|
| nemotron-3-ultra (PRIMARY) | 500 | 4 | 2000 × 4 = 8000 | ~13 hrs |
| glm-5.3 (SECOND_FAMILY) | 150 | 4 | 600 × 4 = 2400 | ~4 hrs |
| llama-3.2-11b (SMALL) | 150 | 4 | 600 × 4 = 2400 | ~4 hrs |
| **Total (sequential)** | | | | **~21 hrs** |

*Note: Each scenario-condition pair may need 2-6 tool-calling rounds; using 4 as average.*

## Runner Configuration

- **Concurrency**: 2 for all models (conservative)
- **Rate limit**: 10 req/min (well below measured)
- **Backoff**: 2s base, 60s max, with jitter
- **Daily budget**: 4000 req (reset daily)
- **Auto-pause on 429**, resume after backoff

## Next Steps

1. Run 3-min sustained probe per model (optional, confirms no 429 pattern)
2. Run 30-scenario pilot (4 conditions × 3 models = 360 requests)
3. Review pilot results → approve full runs
4. Execute full runs sequentially (nemotron → glm → llama)