# S-series run plan, v2 (amended; supersedes S_PLAN.md)

Pre-registration: PROTOCOL §8.33 (2026-10-16 08:53 UTC). Perturbations: `S_PERTURBATIONS_V2.md`.
Oracle: `S_ORACLE_V2.md`.

## Design
- **Base set B = 40** scenarios (`eval/results/s_base_set.json`), stratified (seed 42) across
  Kharif 13 / Rabi 16 / Zaid 11 from the 150-scenario common support.
- **13 simulated-scenario arms**: W1,W2,W3,H1,D1,D2,WET1,WET2,O1,O2,C1,NE15,N1
  (N0 is harness-only; C0/C0b base columns reused; C3 deterministic, free).
- **Conditions run fresh**: C1a (fair stuffing), C2a (six tools), C2b (five tools).
- **Models**: `nvidia/nemotron-3-ultra-550b-a55b`, `meta/llama-3.2-11b-vision-instruct`.
- C0/C0b reused from canonical runs; C3 from `archive_v2/deterministic`.

## Cost estimate (from observed per-call means; no dollar cost - no citable price)
| model | requests | tokens |
|-------|----------|--------|
| nemotron | ~7,280 | ~42 M |
| llama | ~8,320 | ~114 M |
| **total** | **~15,600** | **~156 M** |

- Completions derived from observed means: nemotron C2a ~7 / C2b ~6 tool rounds; llama C2a ~8 /
  C2b ~7; C1a = 1.
- **Daily budget** (`eval/llm/budget.py`) is 4,000 requests / UTC-day -> **~4 UTC-days minimum**.
- Wall-clock longer (rate limits: nemotron ~10 req/min, llama ~12 req/min, account ~40 req/min).

## Execution
- `py -3 eval/scripts/run_s_series.py --models nemotron llama --sets <arm>` per arm; resumable;
  isolated run/cache namespaces per (model, arm); atomic `results.json`.
- Harness validity first: `--sets N0` must reproduce `archive_v2/evidence` (verified already) and
  S-N0 `Shift@5 = 0`.
- Stop for user approval after each model-call batch.

## Abort rules (inherited §8.30)
Stop and report if any of: provider auth/HTTP error; invalid-JSON < 90%; unknown tool call;
S-N0 mismatch; 429 rate > 10%; nemotron valid-JSON < 90% at the 4096/8192 caps.

## Scoring (after runs)
- `eval/scripts/score_s.py` (to build): per (scenario, arm, condition) top5; Stale@5 (primary),
  Violation@5, Shift@5, Drop-faithful; STRICT primary (LENIENT for D1/D2 per §8.33.3);
  contrasts C2a-C0b, C2b-C0b, C2a-C1a, C3-C2b; cluster bootstrap 10000/42 + Holm.
