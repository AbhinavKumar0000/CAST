
## A. Season validity: C3 vs the LLM conditions

C3 season validity (metric table = eval/metrics.py CROP_SEASON_VALIDITY) on the shared subset (n=500): overall mean = 0.7268
  - C3 Kharif: 0.9505 (n=190)
  - C3 Rabi: 0.8780 (n=177)
  - C3 Zaid: 0.2060 (n=133)
scenario.season_stratum vs evidence-bundle season mismatch: 0/500
  nemotron   C0 season-validity mean=0.5249 (n=493)
  nemotron   C0b season-validity mean=0.5916 (n=484)
  nemotron   C1 season-validity mean=0.7319 (n=490)
  nemotron   C2 season-validity mean=0.4916 (n=466)
  llama      C0 season-validity mean=0.3373 (n=150)
  llama      C0b season-validity mean=0.3520 (n=150)
  llama      C1 season-validity mean=0.5850 (n=150)
  llama      C2 season-validity mean=0.4606 (n=105)
  glm        C0 season-validity mean=0.5037 (n=27)
  glm        C0b season-validity mean=0.5722 (n=27)
  glm        C1 season-validity mean=0.6207 (n=29)
  glm        C2 season-validity mean=0.4528 (n=30)

### C2 failing cases (season validity < 1): scenario date vs live tool vs model top5

Live date today = 2026-10-13 (month 10) -> season_tool would report 'Kharif' for EVERY scenario, regardless of as_of_date (mcp_server/season_tool.run uses datetime.now(IST)).

C2 season-invalid cases: 350
  S000063 as_of=2024-02-07 true_season=Rabi district=Agar Malwa tools=6 top5=['Moong', 'Sunflower', 'Soybean'] invalid=[('Moong', {'Kharif', 'Zaid'}), ('Soybean', {'Kharif'})]
  S000072 as_of=2025-04-23 true_season=Zaid district=Agar Malwa tools=6 top5=['Moong', 'Sunflower', 'Soybean'] invalid=[('Sunflower', {'Kharif', 'Rabi'}), ('Soybean', {'Kharif'})]
  S000170 as_of=2024-03-27 true_season=Rabi district=Agar Malwa tools=6 top5=['Moong', 'Sunflower', 'Soybean'] invalid=[('Moong', {'Kharif', 'Zaid'}), ('Soybean', {'Kharif'})]
  S000190 as_of=2024-05-04 true_season=Zaid district=Agar Malwa tools=6 top5=['Sunflower', 'Moong', 'Soybean'] invalid=[('Sunflower', {'Kharif', 'Rabi'}), ('Soybean', {'Kharif'})]
  S000258 as_of=2024-11-19 true_season=Rabi district=Alirajpur tools=6 top5=['Moong', 'Soybean', 'Urad', 'Groundnut'] invalid=[('Moong', {'Kharif', 'Zaid'}), ('Soybean', {'Kharif'}), ('Urad', {'Kharif'}), ('Groundnut', {'Kharif'})]
  S000279 as_of=2025-12-22 true_season=Rabi district=Alirajpur tools=6 top5=['Moong', 'Urad', 'Groundnut', 'Cotton', 'Maize'] invalid=[('Moong', {'Kharif', 'Zaid'}), ('Urad', {'Kharif'}), ('Groundnut', {'Kharif'}), ('Cotton', {'Kharif'}), ('Maize', {'Kharif'})]
  S000311 as_of=2024-12-18 true_season=Rabi district=Alirajpur tools=6 top5=['Moong', 'Urad', 'Groundnut', 'Cotton', 'Maize'] invalid=[('Moong', {'Kharif', 'Zaid'}), ('Urad', {'Kharif'}), ('Groundnut', {'Kharif'}), ('Cotton', {'Kharif'}), ('Maize', {'Kharif'})]
  S000335 as_of=2025-04-21 true_season=Zaid district=Alirajpur tools=6 top5=['Moong', 'Urad', 'Groundnut', 'Cotton', 'Maize'] invalid=[('Urad', {'Kharif'}), ('Groundnut', {'Kharif'}), ('Cotton', {'Kharif'}), ('Maize', {'Kharif'})]
  S000344 as_of=2024-04-17 true_season=Zaid district=Alirajpur tools=6 top5=['Moong', 'Urad', 'Groundnut', 'Soybean', 'Cotton'] invalid=[('Urad', {'Kharif'}), ('Groundnut', {'Kharif'}), ('Soybean', {'Kharif'}), ('Cotton', {'Kharif'})]
  S000355 as_of=2025-12-10 true_season=Rabi district=Alirajpur tools=6 top5=['Moong', 'Urad', 'Groundnut', 'Cotton'] invalid=[('Moong', {'Kharif', 'Zaid'}), ('Urad', {'Kharif'}), ('Groundnut', {'Kharif'}), ('Cotton', {'Kharif'})]

C2 season-invalid cases: 80
  S000063 as_of=2024-02-07 true_season=Rabi district=Agar Malwa tools=6 top5=['Moong', 'Soybean', 'Sunflower'] invalid=[('Moong', {'Kharif', 'Zaid'}), ('Soybean', {'Kharif'})]
  S000190 as_of=2024-05-04 true_season=Zaid district=Agar Malwa tools=7 top5=['Moong', 'Soybean', 'Sunflower'] invalid=[('Soybean', {'Kharif'}), ('Sunflower', {'Kharif', 'Rabi'})]
  S000258 as_of=2024-11-19 true_season=Rabi district=Alirajpur tools=6 top5=['Moong', 'Urad', 'Soybean', 'Groundnut'] invalid=[('Moong', {'Kharif', 'Zaid'}), ('Urad', {'Kharif'}), ('Soybean', {'Kharif'}), ('Groundnut', {'Kharif'})]
  S000279 as_of=2025-12-22 true_season=Rabi district=Alirajpur tools=6 top5=['Moong', 'Urad', 'Groundnut', 'Cotton'] invalid=[('Moong', {'Kharif', 'Zaid'}), ('Urad', {'Kharif'}), ('Groundnut', {'Kharif'}), ('Cotton', {'Kharif'})]
  S000311 as_of=2024-12-18 true_season=Rabi district=Alirajpur tools=6 top5=['Moong', 'Urad', 'Groundnut', 'Cotton'] invalid=[('Moong', {'Kharif', 'Zaid'}), ('Urad', {'Kharif'}), ('Groundnut', {'Kharif'}), ('Cotton', {'Kharif'})]
  S000335 as_of=2025-04-21 true_season=Zaid district=Alirajpur tools=6 top5=['Moong', 'Urad', 'Groundnut', 'Cotton'] invalid=[('Urad', {'Kharif'}), ('Groundnut', {'Kharif'}), ('Cotton', {'Kharif'})]
  S000344 as_of=2024-04-17 true_season=Zaid district=Alirajpur tools=6 top5=['Moong', 'Urad', 'Groundnut', 'Cotton'] invalid=[('Urad', {'Kharif'}), ('Groundnut', {'Kharif'}), ('Cotton', {'Kharif'})]
  S000355 as_of=2025-12-10 true_season=Rabi district=Alirajpur tools=6 top5=['Cotton', 'Groundnut', 'Moong', 'Urad'] invalid=[('Cotton', {'Kharif'}), ('Groundnut', {'Kharif'}), ('Moong', {'Kharif', 'Zaid'}), ('Urad', {'Kharif'})]
  S000438 as_of=2024-05-19 true_season=Zaid district=Anuppur tools=6 top5=['Moong', 'Soybean', 'Sunflower', 'Sugarcane'] invalid=[('Soybean', {'Kharif'}), ('Sunflower', {'Kharif', 'Rabi'}), ('Sugarcane', {'Annual'})]
  S000464 as_of=2025-04-05 true_season=Zaid district=Anuppur tools=6 top5=['Moong', 'Soybean', 'Sunflower'] invalid=[('Soybean', {'Kharif'}), ('Sunflower', {'Kharif', 'Rabi'})]

C2 season-invalid cases: 20
  S000063 as_of=2024-02-07 true_season=Rabi district=Agar Malwa tools=6 top5=['Moong', 'Soybean', 'Sunflower'] invalid=[('Moong', {'Kharif', 'Zaid'}), ('Soybean', {'Kharif'})]
  S000072 as_of=2025-04-23 true_season=Zaid district=Agar Malwa tools=6 top5=['Moong', 'Soybean', 'Sunflower'] invalid=[('Soybean', {'Kharif'}), ('Sunflower', {'Kharif', 'Rabi'})]
  S000170 as_of=2024-03-27 true_season=Rabi district=Agar Malwa tools=6 top5=['Moong', 'Soybean', 'Sunflower'] invalid=[('Moong', {'Kharif', 'Zaid'}), ('Soybean', {'Kharif'})]
  S000190 as_of=2024-05-04 true_season=Zaid district=Agar Malwa tools=6 top5=['Moong', 'Soybean', 'Sunflower'] invalid=[('Soybean', {'Kharif'}), ('Sunflower', {'Kharif', 'Rabi'})]
  S000258 as_of=2024-11-19 true_season=Rabi district=Alirajpur tools=6 top5=['Moong', 'Soybean', 'Urad', 'Groundnut'] invalid=[('Moong', {'Kharif', 'Zaid'}), ('Soybean', {'Kharif'}), ('Urad', {'Kharif'}), ('Groundnut', {'Kharif'})]
  S000279 as_of=2025-12-22 true_season=Rabi district=Alirajpur tools=6 top5=['Moong', 'Urad', 'Groundnut', 'Cotton'] invalid=[('Moong', {'Kharif', 'Zaid'}), ('Urad', {'Kharif'}), ('Groundnut', {'Kharif'}), ('Cotton', {'Kharif'})]
  S000311 as_of=2024-12-18 true_season=Rabi district=Alirajpur tools=6 top5=['Moong', 'Urad', 'Groundnut', 'Cotton'] invalid=[('Moong', {'Kharif', 'Zaid'}), ('Urad', {'Kharif'}), ('Groundnut', {'Kharif'}), ('Cotton', {'Kharif'})]
  S000335 as_of=2025-04-21 true_season=Zaid district=Alirajpur tools=6 top5=['Moong', 'Urad', 'Groundnut', 'Cotton'] invalid=[('Urad', {'Kharif'}), ('Groundnut', {'Kharif'}), ('Cotton', {'Kharif'})]
  S000344 as_of=2024-04-17 true_season=Zaid district=Alirajpur tools=6 top5=['Moong', 'Urad', 'Groundnut', 'Cotton'] invalid=[('Urad', {'Kharif'}), ('Groundnut', {'Kharif'}), ('Cotton', {'Kharif'})]
  S000355 as_of=2025-12-10 true_season=Rabi district=Alirajpur tools=6 top5=['Moong', 'Urad', 'Groundnut', 'Cotton'] invalid=[('Moong', {'Kharif', 'Zaid'}), ('Urad', {'Kharif'}), ('Groundnut', {'Kharif'}), ('Cotton', {'Kharif'})]

### Season validity metric definition

season_validity_rate(pred, season) = fraction of pred crops where season in CROP_SEASON_VALIDITY[crop] (eval/metrics.py). This table is independent, hard-coded, and DIFFERENT from the repo's crop_log.csv `season_supported` used by crop_score_tool.
Crops with only 'Annual' in the metric table (counted invalid in EVERY season): ['Sugarcane']
Note: scenario 'season_stratum' (scenarios.jsonl generator) vs evidence bundle 'season.current_season' have a mismatch rate of 0/500 on the subset.

## B. Hallucination / out-of-registry: pre- and post-normalisation


### Normalisation pipeline (eval/llm/prompts.py)

parse_output(): raw names (top5_raw) -> normalize_crop(): lower/strip punctuation, then map via ALIASES dict, then exact match against CANONICAL_CROPS; anything unmatched -> out_of_registry and DROPPED from top5. The prompt itself embeds the closed candidate list (CROP_LIST_TEXT).
Total top5 slots analysed: 13005

### Out-of-registry (genuine hallucinations) with the FIXED normalizer

  nemotron: 0 / 9665 = 0.0000
  llama: 0 / 2775 = 0.0000
  glm: 0 / 565 = 0.0000

### GENUINE BUG: parenthesised canonical crops were dropped by the old normalizer

The old normalize_crop() ran re.sub(r'[^a-z0-9 ]',' ') on the input BEFORE lookup, so the canonical names 'Sesame (Til)' and 'Arhar (Tur)' became keys 'sesame til' / 'arhar tur', which exist in neither ALIASES ('sesame (til)' / 'arhar (tur)') nor the canonical map. Both were therefore classified out_of_registry and DROPPED from top5, even though the prompt instructs models to emit those exact names. This deflated agreement metrics and made 'hallucination' measurements meaningless.
Raw names recovered by the fix (old->None but fixed->canonical):
  'Sesame (Til)' x920 -> Sesame (Til)
  'Arhar (Tur)' x691 -> Arhar (Tur)
Effect (before -> after), means over valid-json responses; full table in eval/results/normalization_fix_before_after.json:
  nemotron  C0   n=493  top5_len 4.55->5.00  OOR 8.9%->0.0%  acc@5 0.736->0.807  Jaccard 0.236->0.253  season-valid 0.525->0.512
  nemotron  C0b  n=484  top5_len 4.56->5.00  OOR 8.8%->0.0%  acc@5 0.777->0.841  Jaccard 0.233->0.250  season-valid 0.592->0.578
  nemotron  C1   n=490  top5_len 4.27->5.00  OOR 14.7%->0.0%  acc@5 0.982->0.986  Jaccard 0.709->0.818  season-valid 0.732->0.719
  nemotron  C2   n=466  top5_len 3.77->5.00  OOR 24.5%->0.0%  acc@5 0.908->0.908  Jaccard 0.381->0.461  season-valid 0.492->0.460
  llama     C0   n=150  top5_len 5.00->5.00  OOR 0.0%->0.0%  acc@5 0.567->0.567  Jaccard 0.076->0.076  season-valid 0.337->0.337
  llama     C0b  n=150  top5_len 5.00->5.00  OOR 0.0%->0.0%  acc@5 0.633->0.633  Jaccard 0.093->0.093  season-valid 0.352->0.352
  llama     C1   n=150  top5_len 4.71->5.00  OOR 5.7%->0.0%  acc@5 0.993->1.000  Jaccard 0.414->0.452  season-valid 0.585->0.589
  llama     C2   n=105  top5_len 3.70->5.00  OOR 26.1%->0.0%  acc@5 0.857->0.867  Jaccard 0.333->0.420  season-valid 0.461->0.413
  glm       C0   n=27   top5_len 4.74->5.00  OOR 5.2%->0.0%  acc@5 0.815->0.815  Jaccard 0.180->0.182  season-valid 0.504->0.496
  glm       C0b  n=27   top5_len 4.81->5.00  OOR 3.7%->0.0%  acc@5 0.852->0.889  Jaccard 0.158->0.175  season-valid 0.572->0.570
  glm       C1   n=29   top5_len 4.38->5.00  OOR 12.4%->0.0%  acc@5 0.966->0.966  Jaccard 0.589->0.692  season-valid 0.621->0.607
  glm       C2   n=30   top5_len 3.73->5.00  OOR 25.3%->0.0%  acc@5 0.733->0.733  Jaccard 0.303->0.397  season-valid 0.453->0.413
CONCLUSION: genuine crop-hallucination rate is 0.0% for all models (no name outside the 21-crop registry was ever produced once the two parenthesised names normalise). The old 'pre-normalisation 6-14%' figure was 100% this bug. Fix applied in eval/llm/prompts.py.

## C. Metric definitions and C1 leakage

'Accuracy@5 vs C3' = accuracy_at_k(llm_top5, c3_top5, 5) = 1 iff ANY of the LLM's 5 crops appears in the C3 top-5 (binary hit). NOT accuracy on ranked retrieval.
'Delta Jaccard vs C0' = jaccard_similarity(cond_top5, c3_top5) - jaccard_similarity(c0_top5, c3_top5), where jaccard_similarity uses the SET of names (order ignored).
C1 prompt (eval/llm/prompts.py prompt_c1) embeds CROP_SCORE:
  CROP_SCORE: <full deterministic C3 ranking string injected into the C1 prompt>
=> The deterministic C3 ranking is INSIDE the C1 prompt. C1 agreement with C3 is therefore partly CIRCULAR (answer leakage). C1 numbers are reported separately with this caveat; do not headline C1 as 'LLM agreement'.
prompt_c1 contains 'CROP_SCORE': True (confirmed). 

## D. Latency & tokens


### Latency: does latency_s include retries/backoff?

NvidiaProvider.run() starts the timer (time.perf_counter) BEFORE the retry loop and the tool-calling round loop; every backoff sleep and every model round-trip is inside the timed region. So latency_s = end-to-end scenario wall time (incl. 429/5xx retries up to 5 with exponential backoff <=60s, and C2 tool rounds). Per-request API latency is NOT recorded separately in the results; only the aggregate scenario latency is stored.
  nemotron  C0: median_latency=26s (n=500, no errors)
  nemotron  C0b: median_latency=37s (n=500, no errors)
  nemotron  C1: median_latency=33s (n=500, no errors)
  nemotron  C2: median_latency=34s (n=500, no errors)
  llama     C0: median_latency=5s (n=150, no errors)
  llama     C0b: median_latency=5s (n=150, no errors)
  llama     C1: median_latency=4s (n=150, no errors)
  llama     C2: median_latency (all)=26s ok=26s (n=132) err=35s (n=18)
  glm       C0: median_latency (all)=199s ok=196s (n=27) err=1571s (n=5)
  glm       C0b: median_latency (all)=200s ok=186s (n=27) err=1575s (n=5)
  glm       C1: median_latency (all)=220s ok=217s (n=29) err=1483s (n=3)
  glm       C2: median_latency (all)=422s ok=408s (n=30) err=1647s (n=2)

### Tokens: input / output / reasoning split, and 'thinking' mode

Payload does NOT set a 'thinking' flag; NVIDIA NIM may still emit usage.reasoning_tokens. We store tokens_in, tokens_out, reasoning_tokens separately.
  nemotron : mean in=1786 out=1148 reasoning present in 0/2000 records (mean nan when present)
  llama    : mean in=3953 out=176 reasoning present in 0/582 records (mean nan when present)
  glm      : mean in=1494 out=687 reasoning present in 0/113 records (mean nan when present)

## E. Coverage and overlap


### Completed scenarios per model x condition

  nemotron  scenarios per condition: C0=500, C0b=500, C1=500, C2=500
  llama     scenarios per condition: C0=150, C0b=150, C1=150, C2=150
  glm       scenarios per condition: C0=32, C0b=32, C1=32, C2=32
Scenario overlap:
  nemotron x llama: 150
  nemotron x glm:   32
  llama x glm:      32
  all three:        32
Why GLM has n=32: the z-ai/glm-5.3 endpoint degraded to 900-2200s/call with frequent 504 Gateway Timeouts during collection; the run was paused by decision after 128 records (32 scenarios x 4, some with errors). Resume: eval/scripts/run_model.py --model z-ai/glm-5.3 --scenarios 50 --workers 4.
Incomplete runs and what is needed to finish:
  - glm: 50-scenario target, 32 complete -> rerun run_model (resumable via results.json + cache).
  - Consistency repeats (3x) for nemotron/llama: not started (run_model --repeat 3 --scenarios 100).

## F. Paired complete cases


### Within model: scenario sets identical across conditions?

  nemotron C0: n=500 (union over all conditions=500)
  nemotron C0b: n=500 (union over all conditions=500)
  nemotron C1: n=500 (union over all conditions=500)
  nemotron C2: n=500 (union over all conditions=500)
  llama C0: n=150 (union over all conditions=150)
  llama C0b: n=150 (union over all conditions=150)
  llama C1: n=150 (union over all conditions=150)
  llama C2: n=150 (union over all conditions=150)
  glm C0: n=32 (union over all conditions=32)
  glm C0b: n=32 (union over all conditions=32)
  glm C1: n=32 (union over all conditions=32)
  glm C2: n=32 (union over all conditions=32)

### Paired (complete, non-error, valid-json) cases per model pair x condition

  llama vs nemotron, C0: 148/150 paired complete cases
  llama vs nemotron, C0b: 142/150 paired complete cases
  llama vs nemotron, C1: 144/150 paired complete cases
  llama vs nemotron, C2: 117/150 paired complete cases
  glm vs nemotron, C0: 27/32 paired complete cases
  glm vs nemotron, C0b: 26/32 paired complete cases
  glm vs nemotron, C1: 29/32 paired complete cases
  glm vs nemotron, C2: 30/32 paired complete cases
  glm vs llama, C0: 27/32 paired complete cases
  glm vs llama, C0b: 27/32 paired complete cases
  glm vs llama, C1: 29/32 paired complete cases
  glm vs llama, C2: 28/32 paired complete cases

## G. Conclusions and required corrections

1. **Genuine bug fixed (normalize_crop).** Parenthesised canonical crops ('Sesame (Til)', 'Arhar (Tur)') were unmatchable and dropped. Fix applied in eval/llm/prompts.py. Effect: C2 Jaccard vs C3 +0.07..+0.12, C1 nemotron 0.709->0.818, C2 out-of-registry 24-26%->0%. The 'any-overlap' accuracy@5 also rises. All headline agreement numbers must be recomputed with the fix (raw inputs unchanged).
2. **Hallucination = 0% is correct**, but only after the fix; the old '6-14% pre-normalisation' figure was entirely the bug. Report the corrected 0% (genuine) rate.
3. **C1 leakage.** prompt_c1 embeds the full deterministic CROP_SCORE ranking, i.e. the C3 answer. C1-vs-C3 agreement is partly circular; C1 must be presented as 'LLM with the C3 ranking injected', not as independent agreement. This also means C1 is NOT a fair 'stuffing' comparison for agreement-with-C3 (stuffing includes the answer).
4. **C2 harness bug (not recomputable offline).** NvidiaProvider executes the LIVE tools; season_tool.run/weather_tool/crop_score use datetime.now(IST) and live Open-Meteo, ignoring the scenario as_of_date. For historical scenarios the C2 model is told the wrong season (today: 'Kharif') and current weather. The deterministic evidence replay server (eval/mcp_eval/server.py) exists but is not wired in. This depresses C2 season validity (~0.41-0.46) and inflates C2-vs-C3 disagreement; C2 results cannot be repaired without a re-run (out of scope: no new API calls).
5. **Season validity metric.** Uses eval/metrics.py CROP_SEASON_VALIDITY (independent, hard-coded), where 'Sugarcane'={'Annual'} is invalid in every season, and Zaid caps at ~0.21 for C3 too. C3 on the subset = 0.727 overall (Kharif 0.95, Rabi 0.88, Zaid 0.21); the metric is dominated by Zaid. Report per-season and never present the season metric as 'accuracy'.
6. **Latency** = end-to-end scenario wall time INCLUDING retries/backoff and C2 tool rounds; GLM errored records sit at ~1500s vs ~190s for ok. Use only non-error records for latency figures and state the definition. Per-request latency is not stored.
7. **Tokens**: reasoning_tokens is absent for all models (0 records); tokens_in/out are the only reliable efficiency quantities.
8. **Coverage/paired**: nemotron 500, llama 150, GLM 32 scenarios; 3-way overlap = 32. GLM is preliminary (n<100). Cross-model tests only on the nested paired subsets: llama-nemotron (117-148/150 by condition), glm-nemotron and glm-llama (26-30/32).