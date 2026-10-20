# Evaluation Progress Checklist

Last updated: 2026-10-13

### Phase 7: Paper Figure Redesign (data-only, no new API calls)
- [x] STEP 0 diagnostics: `eval/report/DIAGNOSTICS.md`; fixed `normalize_crop` bug; before/after
- [x] STEP 1 master_long.csv (3,228 rows × 31 cols)
- [x] STEP 2/3 figures Fig01-Fig14 + T1/T2 (+ per-figure data CSVs, forest_stats.json)
- [x] STEP 4 FIGURE_GUIDE.md + .docx (figures embedded)
- [x] Archive Fig_M01-M10 to eval/figures/archive_v1/

## Legend: [ ] pending | [~] in progress | [x] done | [!] blocked

### Phase 8: Fix C2 harness, fair baselines, independent metrics, re-run
- [x] STEP A C2 time-anchoring: `eval/time_anchored.py` (frozen clock + cached weather,
      real tool code, normals before as_of); wired into `NvidiaProvider` + `run_model.py`;
      per-call tool log + finish_reason + error_type; max_tool_rounds 10->15 (config)
- [x] STEP A tests (`eval/scripts/test_step_a.py`): season 12 months PASS; no datetime.now/
      live API PASS; equivalence 30 scenarios PASS (v1->v2 drift: climate normals 30/30,
      crop ranking 64/500)
- [x] STEP A v2 evidence: 500-subset + FULL 10k bundles -> eval/runs/archive_v2/evidence/ (2026-10-13)
- [x] STEP A point 1 (independent equivalence): eval/scripts/test_step_a_independent.py — raw-cache
      slicer vs real tools, frozen clock; 180 field comparisons on 30 scenarios, 0 failures; 5 hand-verified
- [x] STEP A point 3 (10k rerun under v2): run_deterministic_v2.py + drift_v1_v2.py + analyze_deterministic_v2.py
      -> C3 top5 drift 1502/10000 (15%); new eval/results/c3_deterministic_summary.json (phase 8, ev v2);
      Fig14 regenerated; v1 archived to eval/runs/archive_v2/previous_v1/
- [x] STEP A point 2 + 4 recorded in PROTOCOL.md (Phase 8 addendum): normals windows v1/v2/paper exact
      dates, SPI 2019-2023, 64/500-why + 5 examples, Niwari audit (0 scenarios; soil_tool returns empty +
      note, no default soil)
- [x] STEP B fair baselines: prompt_c1a (raw evidence + candidate requirements, no scores/ranking),
      prompt_c1b (oracle = C1 relabelled, points to prompt_c1), prompt_c2(scenario, tools) C2a=6/C2b=5;
      NvidiaProvider allowed_tools (schema filter + execution guard); run_model CONDITIONS +
      build_prompt 3-tuple + evidence gate for C1/C1a/C1b; PROTOCOL.md addendum written; offline smoke-tested
- [x] STEP C independent metrics: eval/data/ground_truth/{crop_season_table,hard_constraints,expert_rating_template}.csv
      + GT_SOURCES.md (SLBC-MP, evikas, DPD summer pulses, TNAU, ICAR-CRIDA DACP URLs); cited-season recompute
      -> eval/results/c3_season_validity_cited.json (validity 0.7695; Zaid 0.5293; hard-viol 0.0814);
      finding [RETRACTED 2026-10-13, see §8.13]: the original "C3 recommends Barley first in ALL
      3,319 Rabi scenarios" is NOT reproduced by any source; on the frozen v2 grid Barley is top-5
      in 100% of Rabi but #1 in only 163/3319 (4.9%);
      rename Accuracy@5/Jaccard vs C3 -> 'Fidelity to C3' + Fig_M05 title/file
- [x] STEP D model smoke table (13 candidates in eval/models/MODELS.md) + proposal.
      AUTHOR DECISION (a): DROP GLM-5.3; final set = Nemotron-3-Ultra (PRIMARY, n=500) +
      Llama-3.2-11b (SMALL, n=150); GLM cells excluded, kept as preliminary/supplementary.
- [ ] STEP E run plan dry run (WAIT for approval)
- [ ] STEP F run + rebuild master_long + figures + guides

### STEP E pilots (harness-fix ss8.10, 2026-10-13)
- [x] Item 1 harness fix implemented + offline tests (`eval/scripts/test_harness_fix.py`, 5/5 PASS):
      unknown-tool error with valid-tool list + "reply JSON now"; stall fallback (2 consecutive
      unknown OR round 12 -> one tools-disabled request, `forced_final` + reason); FINAL_JSON_ONLY
      appended to C1a/C1(C1b)/C2 prompts ONLY (C0/C0b untouched, hashes verified unchanged via
      verify_reuse.py); `max_output_tokens_tools` 2048->8192 (tool conds; C0/C0b stay 4096);
      per-response metrics {valid_json, truncated, forced_final, unknown_tool_calls, max_rounds_reached}.
      PROTOCOL.md ss8.10 written (deviation, asymmetry, ITT + per-protocol analysis defs, abort rules).
- [x] Pilot v1 (pre-fix, 2026-10-13): 60 Nemotron + 20 Llama calls; Nemotron 60/60 ok (C2b 11/20 valid,
      9 trunc `length`; root cause = 2048 tool cap on final response); Llama C2a 14/20, 6/20
      `max_rounds_reached` stuck on hallucinated top5/top5_crops/top_crops -> abort rule (d) 30% > 10%.
      Records kept ONLY for appendix "pre-fix failure modes".
- [x] Pilot v2 (post-fix, 20 NEW scenarios `eval/results/pilot_v2_scenarios.json`, 7/7/6 Kharif/Rabi/Zaid;
      first attempt ABORTED by rule (f) then resolved, 2026-10-13):
      - ATTEMPT 1: Nemotron C1a 16/20 valid (80%), 4/20 truncated finish=length @4096 -> rule (f) FAIL.
        ROOT CAUSE: C1a runs WITHOUT tools in payload (use_mcp=False, no allowed_tools), so the provider
        chose max_output_tokens=4096, NOT the raised 8192 tool cap.
        FIX (ss8.10 d-amendment): run_model.py now passes max_output_tokens=8192 explicitly for
        C1a/C1b/C2a/C2b incl. tool-less C1a/C1b; provider run() honours the override;
        stale C1a pilot-dev cache purged; results file purged for re-run.
      - FINAL: Nemotron 60/60 valid_json (C1a 20/20 @8192, C2a 20/20, C2b 20/20), 0 trunc, 0 forced,
        0 unknown; C2a 7.0 HTTP/scen/6 tools, C2b 6.0/5 tools; Llama C2a 20/20 valid, C2b 19/20
        (1 invalid: S000733), 1 forced_final (S000544, round12 -> was valid), 0 max_rounds_reached
        (vs 6/20 pilot v1 — stall fix WORKED), 10+10 unknown top5_crops calls recovered in-run.
      - Abort checks: (a) PASS 0/20 season mismatch, (b) PASS 0 live/network, (c) PASS 0 crop_score
        in C2b, (e) PASS 0% 429, (f) PASS all Nemotron tool conditions 100% valid / 0% forced.
      - Measured HTTP/scenario for plan recompute: Nemotron C1a 1.0 / C2a 7.0 / C2b 6.0;
        Llama C2a 7.5 / C2b 6.9.
- [x] STAGE A (Llama, 2026-10-13): C1a/C2a/C2b on llm_subset[:150] -> eval/runs/eval_llama-3.2-11b/results.json
      (450/450 ok, 0 err, 37.6 min; v1 C0/C0b/C1/C2 rows intact in same file).
      Verify (eval/scripts/verify_stage_a.py): C1a 150/150 valid (100%), C2a 148/150 (98.7%, 1 trunc
      `length`, 3 forced round12), C2b 134/150 (89.3%, 9 forced round12); max_rounds_reached = 0
      (stall fallback prevents it); unknown-tool calls 56 (C2a) / 75 (C2b), all recovered in-run;
      HTTP/scen C1a 1.0 / C2a 7.5 / C2b 7.0; Llama C2b validity gap is a REAL result for step E
      (per-protocol n vs ITT sensitivity required).
- [x] PRE-B1 CLOSEOUT (2026-10-13):
  - [x] 2b: PROTOCOL.md §8.11 CONFIRMED primary-analysis pre-registration, timestamped
        2026-10-13T21:12:30Z BEFORE computing any primary metric (hard-violation + season-validity,
        LENIENT headline / STRICT sensitivity, 4 primary contrasts as ONE Holm family per model
        per metric, paired within scenario, per-protocol vs ITT - claim only if both hold).
  - [x] 2a: build_master_long.py adds `pilot_dev` column (1 for the 40 pilot scenarios v1+v2,
        derived from eval/results/pilot_scenario_sets.json, applied even to cache-reused/cacheless
        records); rebuild produced 3678 rows -> eval/results/master_long.csv.
  - [x] 2c item 1 evidence collected (see eval/scripts/_llm_c0_validity.py output, barley_top1_margins.csv,
        analyze_barley_problem.py, GT_SOURCES.md 4 barley refs, UNVERIFIED_FOR_REVIEW.csv = 13 rows).
  - [x] BUDGET: today = 3,372 HTTP of 4,000/day (84.3%); B1 (Nemotron C1a/C2a/C2b ×150) ≈ 2,100 HTTP
        EXCEEDS the 628 remaining -> B1 scheduled for next day, not launched today.
        §8.12 records the boundary = UTC calendar day (reset 2026-10-14T00:00:00Z = 05:30 IST);
        provider reads daily_request_budget but does not enforce it (status.py counter is approximate).
- [x] STAGE A INTERIM METRICS GATE (2026-10-13, no API calls) -> eval/results/stage_a_interim_metrics.txt:
      cell table (C0/C0b/C1a/C2a/C2b/C3) STRICT+LENIENT x per-protocol+ITT with 95% bootstrap CIs + n,
      and the 4 pre-registered paired contrasts (C2a-C0b, C2a-C1a, C2b-C0b, C2b-C1a) with paired diffs,
      95% CIs, Cliff's delta and Holm-adjusted p — reported WITH and WITHOUT the 40 pilot_dev scenarios.
      Key pattern: C2a >> C0b/C1a (huge, survives all corrections); C2b is WORSE than C0b/C1a under
      per-protocol but NOT distinguishable under ITT (its 65 invalid responses are dropped in PP).
- [x] §8.11 timestamp CORRECTED: recorded "2026-10-13T21:12:30Z" was IST mislabelled as UTC;
      true UTC = 2026-10-13T15:42:30Z (21:12:30 IST - 05:30).
- [x] STALE-SOURCE AUDIT (§8.13, eval/results/stale_source_audit.json): stale = adhoc/evidence
      crop_score bundles (no _v); frozen = archive_v2/deterministic full_repo grid (_v=2).
      Barley#1 Rabi 303(9.1%)->163(4.9%); Barley top-5 Rabi 2914(87.8%)->3319(100%); C3 top-1
      agreement 8333/10000. "Barley first in ALL 3,319 Rabi" retracted (no source supports it).
- [x] §8.14 RABI RAINFALL: rainfall_match == 0.00 for all 18 crops in 3,319/3,319 Rabi scenarios;
      0.20 rainfall weight inert in Rabi; rankings decided by remaining 0.80, median margin 0.004.
- [x] UNKNOWN-TOOL result: C2a 56/150 scenarios (all exactly 1), C2b 75/150 (all exactly 1);
      invented names top5_crops (129) + top5 (2). C2b also more stalls (9 forced vs 3) and lower
      validity (134 vs 148).

---

### Phase 0: Audit & Protocol
- [x] REPO_AUDIT.md written (2026-10-09)
- [x] PROTOCOL.md written (2026-10-09); Phase 8 addendum (protocol v2, 2026-10-13)
- [x] config.yaml frozen (2026-10-09)
- [x] config SHA256: 2fe37c276ce663f3d1db6cbc5f3b6c2553e35c1ddeec6952bc16c344c5f82b6f
  (STEP A added max_tool_rounds=15; new hash stamped in v2 runs)

### Phase 1: Scenarios & Ground Truth
- [x] 10,000 scenarios generated (2026-10-10 00:05 UTC)
- [x] Bulk weather archive cached (21/51 districts, 2026-10-10 01:30 UTC)
- [x] Stress set identified (4,212 scenarios, 2026-10-10 01:45 UTC)
- [x] LLM subset created (500 scenarios, 150 stress, 2026-10-10 01:45 UTC)
- [ ] External ground truth obtained (ICAR-CRIDA / data.gov.in)
- [ ] Hard-constraint table built (STEP 3b)
- [ ] Expert rating template created (STEP 3c)

### Phase 2: Deterministic Pipeline (C3 + Ablations)
- [x] Evidence bundles built (8,628/10,000 scenarios, 2026-10-10 02:00 UTC)
- [x] C3 full_repo run on all 8,628 (2026-10-10 02:30 UTC)
- [x] All 7 tool ablations on 8,628 (2026-10-10 02:30 UTC)
- [x] Weight sensitivity (±20% per weight) on 8,628 (2026-10-10 02:30 UTC)
- [x] Deterministic analysis + figures E01-E06 (2026-10-10 02:45 UTC)

### Phase 3: LLM Provider Switch (NEW - replaces Gemini)
- [x] Part 1: Provider-agnostic LLM client for NVIDIA NIM
- [x] Part 2: Model discovery & registry (models.yaml, MODELS.md)
- [x] Part 3: Quota probe per model + plan (QUOTA.md written)
- [x] Part 4: Cross-model comparison design (Fig_M01-M10) + analysis + figures
- [x] Part 5: Report template updates

### Phase 4: LLM Experiments (per selected model)
- [x] PRIMARY model: nvidia/nemotron-3-ultra-550b-a55b
  - [x] Pilot: 30 scenarios × 4 conditions (C0, C0b, C1, C2)
  - [x] Full: 500 scenarios × 4 conditions = 2,000 calls (0 errors; results.json)
  - [ ] Consistency: 100 scenarios × 3 repeats × 4 conditions (pending)
- [~] SECOND_FAMILY model: z-ai/glm-5.3  (paused at 32/50 scenarios)
  - [x] Pilot on paired subset (probes + 32 scenarios captured)
  - [~] Full on paired subset (50 scenarios) - paused; endpoint degraded (900-2200s, 504s)
  - [ ] Consistency on 50 scenarios
- [x] SMALL model: meta/llama-3.2-11b-vision-instruct
  - [x] Pilot: probes
  - [x] Full on paired subset (150 scenarios, 600 calls; 18 C2 tool-round failures)
  - [ ] Consistency on 50 scenarios

### Phase 5: Analysis & Figures
- [x] Quality/safety/specificity/reliability/consistency/efficiency metrics (all conditions, all models)
- [x] Bootstrap CIs, paired tests, effect sizes (STEP 7)
- [x] Figures E01-E06 (deterministic, original plan)
- [x] Figures M01-M10 (cross-model comparison)
- [x] All aggregates as JSON (`eval/results/llm_aggregates.json`, `llm_paired_stats.json`)

### Phase 6: Report
- [x] RESULTS_REPORT.md + .docx with all sections (`eval/report/`)
- [ ] Claims audit table
- [~] Paper-ready replacement text (skeleton in report §4)
- [x] Reproduction instructions (report §7)

---

**Total tasks: ~38 | Completed: 25 | In progress: 2 | Blocked: 0 | Progress: 66%**

---

## 2026-10-14 - Canonical-source closeout (PROTOCOL 8.15)

- [x] Repoint all analysis/figure/replay readers to `archive_v2/{deterministic,evidence}`:
      the named 4 + `generate_figures.py` + `finalize_stress_and_subset.py` + `mcp_eval/server.py`
      default + `_pre_pilot_season_check.py` + Makefile `deterministic` target.
- [x] Writer collision fixed: canonical `c3_deterministic_summary.json` sole writer =
      `analyze_deterministic_v2.py`; the two v1 writers retired to `eval/scripts/archive_v1/`
      (output `c3_deterministic_summary.v1.json`). `figure_stats.json` sole writer =
      `eval/figures_paper.py`.
- [x] adhoc-reader audit closed - full disposition list in `eval/results/adhoc_reader_audit.json`.
- [x] Grid equivalence + repoint before/after recorded: `full_repo.top5` differs in 1502/10000;
      `_grid_semantic_diff.json`, `_det_source_before_after.json`.
- [x] Fig_E01-E06 marked SUPERSEDED (`eval/figures/SUPERSEDED.md`); kept, not deleted.
- [x] Budget enforcement (PROTOCOL 8.12 amendment): `eval/llm/budget.py`; `NvidiaProvider.post`
      reserves per HTTP attempt and hard-stops `budget_exceeded`; `run_model.py` stops cleanly with a
      resume message; `status.py` prints the real counter. Seeded 3,372 for 2026-10-13 (628 left).
- [x] Offline items 5-8 (PROTOCOL 8.16, no API calls) -> `eval/results/offline_contrasts.{txt,json}`:
      item 5 hard-violation contrasts; item 6 exploratory C1a-C0b (~0) + C2a-C2b (large); item 7
      Fidelity-to-C3 diagnostic (Jaccard 0.685 PP / top-1 0.787 PP, but C2a usually loses to C3);
      item 8 unknown-tool rate C2a 37.3% / C2b 50.0%, C2b-C2a +0.127 [+0.013,+0.240] p=0.030.
- [x] B1 DONE (Nemotron C1a/C2a/C2b x150, 2026-10-14): launched 05:30:19 IST, finished 07:53:57
      IST; 450/450 ok, 0 err, 142.9 min; budget 824/4000 on 2026-10-14. Results:
      `eval/runs/eval_nemotron-3-ultra/results.json` (150 scenarios x 3 conds). Verify
      (`eval/scripts/verify_b1_nemotron.py`): C1a 145/150 valid (96.7%, 9 trunc @8192 - cap
      confirmed applied, genuine over-length; PP-usable 141), C2a 150/150 (100%, 7.0 HTTP/scen),
      C2b 149/150 (99.3%, 1 trunc, 6.0 HTTP/scen); 0 unknown-tool, 0 forced_final, 0 max_rounds,
      crop_score in C2b = 0, 429 = 0.
- [x] Nemotron primary metrics on the 150 (PROTOCOL 8.18) -> `eval/results/nemotron_primary_metrics.{txt,json}`.
      Reuse check: C0/C0b prompt_hash recomputed from current builders matches stored in 300/300 ->
      0 re-runs. Disclosed asymmetry: C0/C0b reused pre-fix (2026-10-10..10-12, prompt-identical,
      tool-less, 4096 unchanged; config SHA 2C5BC2A7...), C1a/C2a/C2b fresh (2026-10-14). C1a
      8192-truncation 9/150 (6.0%) vs Llama 0/150; reported PP (n=141) + ITT (n=150). Key: STRICT|PP
      C2a .801 > C2b .722 > C1a .665 ~ C0b .663 > C0 .530 (C3 .863); pre-registered sv C2a-C0b +0.150
      Holm 5.1e-04, C2a-C1a +0.133 Holm 5.5e-06, C2b-C0b/-C1a +0.061 n.s. at PP but all significant
      under ITT; exploratory C1a-C0b ~ 0 (replicates Llama); Fidelity-to-C3 C2a Jaccard 0.820 / top-1
      0.827.
- [x] B1 pre-launch hygiene (PROTOCOL 8.17): run_model caches by (model,condition,prompt,sid,rep) and
      the harness fix did not change those keys, so B1 would have silently reused 120 pre-fix Nemotron
      records (40 pilot_dev scenarios x C1a/C2a/C2b; 2 C1a finish=length @4096; the C2a/C2b batch
      predates time-anchoring). Quarantined to `eval/cache/llm/_quarantine_nemotron_prefix_20261014`
      (moved, not deleted) via `eval/scripts/_purge_b1_stale_cache.py`; cache now 0 for these -> B1 ran
      all 450 clean. Launcher `eval/scripts/_b1_launch.ps1` waited for 00:00Z then ran B1 detached;
      logs `eval/runs/logs/b1_nemotron_20261014.{log,status}`.
- [x] Four offline gaps on the Nemotron result (PROTOCOL 8.19) ->
      `eval/results/gaps_analysis.{txt,json}` (`eval/scripts/gaps_analysis.py`). (1) ITT contrasts +
      claimability: direction under ITT sv C2b-C0b +0.143, C2b-C1a +0.092 (both sig) -> C2b is BETTER
      than baseline under ITT (Llama was -0.210); C2b sv pair is the only cell whose claimability flips
      by strict/lenient and with/without pilot; hv all 8 claimable with pilot. (2) hv cells + all four
      contrasts every cell (all sig at PP strict; no C2b sign reversal). (3) Fidelity-to-C3 both models
      (Nemotron Jaccard 0.820 / top-1 0.827; Llama 0.685 / 0.787) with per-scenario match/beat/lose
      counts+%. (4) C1a truncation-bias: no material systematic difference (stress 44.4% vs 40.4%,
      risk 22.2% vs 20.6%, len -12 chars on n=9); PP C1a not materially biased, report PP+ITT.
- [ ] Stage B2 (Nemotron C1a/C2a/C2b on remaining 350, to n=500) - PROPOSED ONLY, not launched
      (PROTOCOL 8.20). Pre-planned second half of n=500 grid (not optional stopping); main value
      resolving n.s. C2b sv contrast. Est: 1,050 calls, ~4,900 HTTP (1.23 days -> 2 UTC-days),
      ~3.99M in / 2.23M out tokens, ~5.5h @4 workers. Needs pre-launch stale-cache + C0/C0b reuse
      re-verification for 151..500.
- [x] Real MCP-client transport option + equivalence (PROTOCOL 8.21). `eval/mcp_runtime.py::McpToolRuntime`
      is a persistent `mcp.ClientSession` -> `eval/mcp_eval/server.py` (streamable-http), serving the
      SAME frozen `TimeAnchoredBuilder` bundles (no `datetime.now`/live Open-Meteo). `run_model.py`
      gained `--tool-transport {inprocess,mcp}` (default `inprocess`) + `--run-suffix`; MCP runs use a
      transport-scoped cache/run dir; in-process path and all existing results untouched.
      Stage 1.5 schema diff (`eval/scripts/mcp_schema_diff.py`): after adding `Annotated[float,Field(...)]`
      param descriptions to the server, 0 differences vs `_build_tools` on all six tools.
      Stage 1.6 equivalence (`eval/scripts/test_mcp_equivalence.py`): 300/300 model-visible payloads
      byte-identical; `output_hash` differs only for climate_tool (int-vs-str keys under sort_keys,
      cosmetic). C2b gate over MCP (`eval/scripts/test_mcp_transport.py`): all 8 checks pass
      (crop_score forbidden in C2b, never reaches the runtime; C2a serves it). `ToolRuntime`/
      `McpToolRuntime` now interchangeable. Env: `eval/anyio_compat.py` shim (anyio 3.7.1 lacks
      `create_memory_object_stream[T]`); regenerated `evidence/index.json` (10,000 keys, 0 collisions).
- [x] Stage 2 MCP C2a x50 run DONE (2026-10-14): `run_model --conditions C2a --scenarios 50
      --tool-transport mcp --run-suffix _mcp_c2a50` (Nemotron; 50/50 ok, 0 err, 6.9 min; keys loaded
      from `.env` NVIDIA_API_KEY_1..4 via `load_dotenv()`). Compared vs in-process B1 C2a for the
      same 50 ids (`eval/scripts/compare_mcp_transport.py` ->
      `eval/results/mcp_transport_comparison.json`): top-5 exact order 50/50; all metric cells
      (strict/lenient x PP/ITT x sv/hv) max |diff| = 0.0; fidelity-to-C3 identical (Jaccard 0.848,
      top-1 0.80); flags identical; only latency differs (median 28.5s MCP vs 19.4s in-process).
      Transport equivalence confirmed; in-process results untouched.
- [x] MCP freshness audit + HTTP-accounting correction (PROTOCOL 8.22; `eval/scripts/_recon_transport_audit.py`).
      (1) cache KEY omits transport, but the cache DIR is transport-scoped (`<short>_mcp`), so the
      MCP run used a fresh empty namespace: **0/50 cache-served, 50/50 fresh**. (2) counter counts
      every HTTP attempt incl. retries; the "7.0/scen C2a" figure was wrong (model emits all 6 tools
      in ONE response): B1 C2a 2.19/scen, MCP C2a 2.12/scen -> 106 base + 17 retries = 123 observed.
      **B2 corrected to ~1,860 HTTP (one UTC day), not ~4,900.** (3) records store no response id;
      freshness shown by timestamps (MCP 12:39-12:47Z vs B1 00:0xZ, 0 overlap). (4) no purge/re-run
      needed. Equivalence framed as a METHODS-VALIDATION check, not a finding.
- [x] B2 pre-launch hygiene (`eval/scripts/_b2_hygiene.py`): 151..500 -> C0/C0b 700/700 reusable;
      C1a/C2a/C2b stale-cache 0/1050. `run_model.py` gained `--scenario-start` for the contiguous slice.
- [~] B2 LAUNCHED (2026-10-14, detached via `eval/scripts/_b2_launch.ps1`): Nemotron C1a/C2a/C2b on
      llm_subset[150:500] (350 scenarios) into `eval/runs/eval_nemotron-3-ultra_b2/` (`--run-suffix _b2`),
      in-process, 4 workers, resumable + waits for UTC reset only if the budget is hit. Log/status:
      `eval/runs/logs/b2_nemotron_20261014.{log,status}`. Targets 1,050 calls (~1,860 HTTP).
      ENV NOTE: the machine slept (on battery, DC idle-timeout = 600s) at ~03:40 IST for ~2.85h,
      freezing the process; on resume 3 calls completed with absurd latencies (~10.4-10.5k s) --
      B2_RECORDS S004671/C2a, S004642/C2b, S004652/C2b. These are environmental, not model behaviour;
      latency (reported as median) is unaffected, but flag/exclude these 3 for any latency stat.
      A non-persistent keep-awake (`eval/scripts/_keepawake.ps1`, holds SetThreadExecutionState
      SYSTEM_REQUIRED until run_model exits; changes no power settings) now prevents recurrence.
- [x] B2 hygiene passed (C0/C0b 700/700 reusable; 0 stale C1a/C2a/C2b) and B2 launched (4 workers,
      in-process, `--scenario-start 150 --scenarios 350 --run-suffix _b2`). B2 COMPLETED: 1,050
      records (350x3), 0 errors, 350 distinct sids. Exit=1 was a benign watcher file-lock race on the
      final `os.replace`; results.json intact. status=`B2_FINISHED`.
- [x] n=500 Nemotron primary metrics (`eval/scripts/n500_primary_metrics.py` ->
      `eval/results/n500_primary_metrics.{txt,json}`, PROTOCOL 8.23). Merge B1(150)+B2(350)
      C1a/C2a/C2b; C0/C0b from verified-reusable cache; C3 archive_v2. 500 distinct sids/cond.
      **All four pre-registered contrasts CLAIMABLE** (PP & ITT agree, Holm<0.05) on sv & hv,
      strict & lenient, with & without pilot. **C2b-C0b** sv strict PP +0.128 Holm 3.6e-12 / ITT
      +0.193 Holm 5.9e-22; **C2b-C1a** sv strict PP +0.105 Holm 2.5e-11 / ITT +0.138 Holm 2.6e-15
      (both were n.s. at n=150 -> now decisive). Exploratory C1a-C0b & C2a-C2b NOT claimable.
      Fidelity C2a-vs-C3 Jaccard 0.831, top-1 0.85. C1a truncation 30/500 (6.0%). Nemotron n=500,
      Llama n=150 (cross-model at 150).
- [x] GT provenance audit (items 8-11) (`eval/scripts/gt_provenance_audit.py` ->
      `eval/results/gt_provenance_audit.{txt,json}`, PROTOCOL 8.23a). C3 scorer reads UNCITED
      `crop_log.csv`; LLM sv/hv metrics read the cited GT tables v1.1 -> independent sources. They
      diverge on 3 crops (Groundnut/Urad/Sunflower Zaid cited by GT but not in crop_log). Scorer
      season weight = 0.30 (config.yaml:137); the 0.35 is the risk-sensitivity `low` weight. 13
      UNVERIFIED rows (10 unverified + 3 cited-v1.1).
- [x] HTTP / tool-round reconciliation (`eval/scripts/recon_http_rounds.py` ->
      `eval/results/recon_http_rounds.{txt,json}`, PROTOCOL 8.24). Nemotron C2a 2.19 / C2b 2.12 base
      requests/scen (all 6 tools in one response). **The "7.0/scen" number is Llama's**: Llama C2a
      7.49 / C2b 7.04 (6.49/6.04 tool-rounds, one tool per response) -> ~3.4x request overhead vs
      Nemotron on the identical tool task (reportable efficiency finding).
- [~] Consistency repeats launched (PROTOCOL 8.25): 100 scen x {C0b,C1a,C2a} x 3 repeats, repeat 0
      exists, repeats 1-2 fresh (600/model), Nemotron then Llama. Launcher
      `eval/scripts/_consistency_launch.ps1` (detached, resumable, UTC-reset aware), status
      `eval/runs/logs/consistency.status`, keep-awake `eval/scripts/_keepawake_consistency.ps1`.
      Started 2026-10-15T10:56 IST.
- [x] Heterogeneity + season stratification (`eval/scripts/n500_heterogeneity.py` ->
      `eval/results/n500_heterogeneity.{txt,json}`, PROTOCOL 8.26). B1 (150) and B2 (350) disjoint;
      season mix B1 47/60/43 vs B2 143/117/90 (unbalanced). Strict sv: **C2b-C0b interaction
      +0.094 [+0.019,+0.169] perm p=0.019** (B1 +0.062 vs B2 +0.156, replicates author's ~0.061/0.157);
      C2b-C1a interaction +0.062 (p=0.078); C2a contrasts stable (p>=0.74); hv interactions n.s. Season
      stratification (n=500, strict PP sv): Kharif all four large+signif (C2b-C1a +0.142); Rabi C2a-C1a
      -0.012 n.s. and C2b-C1a **-0.067 (Holm 0.014)**; Zaid C2a-C1a +0.167, C2b-C1a +0.276. Season-
      dependent; merged +0.105 is a Kharif/Zaid composition effect.
- [x] Divergent-crop provenance impact (`eval/scripts/n500_divergent_crop_impact.py` ->
      `eval/results/n500_divergent_crop_impact.{txt,json}`, PROTOCOL 8.27). Divergent crops
      (Groundnut/Urad/Sunflower) appear in C3 top-5 in 437/500 (87.4%), C2a 414/500 (82.8%), other
      conds 31-43%. Stripping them from every top-5: headline contrasts move <=0.03, no sign flip,
      **all 16 claimability cells preserved** -> conclusions robust; provenance is a methods note.
- [x] 0.35-vs-0.30 season-weight check (PROTOCOL 8.28). Confirmed scorer season weight = 0.30
      (config.yaml:137); 0.35 is the risk-sensitivity `low` weight. Repo-wide grep: no file states
      0.35 as the season weight (the two prior occurrences were already corrected). The "Barley
      analysis" is PROTOCOL 8.5, already correct (0.30).
- [x] Close-out checks (`eval/scripts/n500_heterogeneity_season.py` ->
      `eval/results/n500_heterogeneity_season.{txt,json}`, PROTOCOL 8.29).
      (1) C2b-C0b half gap NOT explained by season: isB2 coef +0.094 (p=0.015) -> +0.087 (p=0.024)
      adj season -> +0.105 (p=0.017, isPilot p=0.39); within-season B1->B2 gap in every season
      (Kharif +0.081->+0.197, Rabi +0.038->+0.073, Zaid +0.077->+0.203) => genuine B1/B2 batch effect,
      report it. C2b-C1a half gap IS explained by season (R2 0.007->0.167; Rabi -0.205 p=4.6e-9).
      (2) Four contrasts by season, n=500 EXPLORATORY table (Kharif/Rabi/Zaid; sv STRICT PP).
      (3) Rabi anomaly vs inert rainfall channel: **NOT SUPPORTED** - rainfall_match inert in BOTH
      Rabi (frac0=1.000) and Zaid (frac0=1.000) yet C2b-C1a = -0.067 vs +0.276; corr ~0 (r=+0.04,
      p=0.38). C1a/C2b see the same rainfall values, so inertness cannot explain the divergence.
      (4) Consistency repeats still running; then run consistency_analysis.py and fill PROTOCOL 8.29.
- [x] Selection-variable audit (`eval/scripts/n500_heterogeneity_selection.py` ->
      `eval/results/n500_heterogeneity_selection.{txt,json}`, PROTOCOL 8.29 cont.). B1 vs B2 differ in
      DISTRICT (perm_p=0.0005; only 1 shared district -> halves near district-disjoint) and
      stress.jsonl membership (0.407 vs 0.254, p=0.0008). drought/flood/C3 margins/n_seasvalid/
      n_crops do NOT differ. Re-test C2b-C0b: isB2 +0.105 -> +0.088 (add stress, p=0.044) -> still n.s.
      under district FE (collinear, uninterpretable). **No variable absorbs it -> UNEXPLAINED and
      confounded with the nested district selection.** Per-half C2b-C0b: B1 +0.062, B2 +0.156, merged
      +0.128 (interaction +0.094, perm_p=0.0186); C2b-C1a B1 +0.061, B2 +0.124, merged +0.105.
- [x] District-clustered inference (`eval/scripts/n500_clustered_inference.py` ->
      `eval/results/n500_clustered_inference.{txt,json}`, PROTOCOL 8.29b; METHODS/LIMITATIONS in
      RESULTS_REPORT updated). 51 districts (m_bar=9.8). ICC sv/hv: C2a 0.166/0.241 (DEFF 2.5/3.1, ESS
      203/160), C2b 0.084/0.070, C0/C0b/C1a/C3 ~0. ICC of the paired DIFF ~0 (C2b-C0b 0.000); cluster
      CIs widen modestly, all contrasts hold; **0/16 claimability cells change**. B1 C2b-C1a sv -> n.s.
      under clustering ([-0.004,+0.139], p=0.091); B1 C2b-C0b borderline. District-level C2b-C0b: mean
      +0.123, SD 0.134, range -0.171..+0.400; B1/B2 gap = 0.70 SD -> reframed as district variation.
      C2a-vs-C3 sv match 72.2%/beat 2.6%/lose 25.2%. C2a-C0b +0.1614, C2a-C1a +0.1353 (strict PP sv).

### Phase 8.30: Real-world independent evaluation (offline; no new API calls)
- [x] STEP 1 sources (`eval/real_data/SOURCES.md`): DES/MoA&FW UPAG (ODC-By) via India Data
      Portal/ISB CKAN; S2 DES APY; S3 2023-24 cross-check; 2024-25 district file REJECTED.
- [x] STEP 2 build (`eval/scripts/... build_dataset.py` -> `clean/area_by_district_season_year.csv`,
      10,304 rows; `QA.md`): 51/51 districts mapped; 19/21 registry crops have series (Kodo-Kutki,
      Watermelon absent); out-of-vocab share of R_all top-5 = 0.085.
- [x] STEP 3 circularity (`eval/real_data/CIRCULARITY.md`): reference held out from system; F3
      (vocab restriction) mitigated by R_all; F5 (pretraining contamination) inherent, disclosed.
- [x] STEP 4 pre-registration (`eval/PROTOCOL.md` 8.30, 2026-10-16 05:40 UTC) committed `e70b333`.
- [x] STEP 5 scoring (`eval/scripts/real_eval.py` -> `eval/results/real_eval.{json,txt}`): R_prim
      headline + R_full/R_all/R_prod sensitivity; district-clustered bootstrap; Holm over 5 contrasts.
      Headline (R_prim, PP, WITH pilot, Precision@5): nemotron C2b **0.622** best (C2b-C1a +0.123
      Holm 5e-4; C3-C2b -0.120 Holm 5e-4; C2a contrasts n.s.); llama C2a **0.506** best (C2a-C1a
      +0.185 Holm 5e-4; C2b contrasts n.s.). C3: nemotron 0.503 (n=500), llama 0.525 (n=150). UNVERIFIED
      check: only Barley/Rabi supported by real area; 4 season rows have zero real area (consistent
      with UNVERIFIED). No ground-truth file edited.
- [x] STEP 6 figures (`eval/scripts/real_eval_figures.py` -> `eval/figures/real/`): fig1 levels,
      fig2 contrast forest, fig3 reference sensitivity (+data CSVs).
- [x] STEP 7 report (`eval/results/REAL_EVAL_REPORT.md`). **AWAITING USER APPROVAL.**
      Follow-ups (2026-10-16, offline):
  - [x] §9 bug log (2 scoring-code bugs, neither changed a conclusion).
  - [x] §10 C2a/C2b vs scorer ranking (`real_eval_scorer_vs_final.{json,txt}`).
  - [x] §11 ground-truth v1.2 + season-validity old vs new
        (`crop_season_table_v1.2.csv`, `c3_season_validity_v1.2_vs_v1.1.{txt,json}`).
        Only Jowar/Rabi and Arhar/Rabi are contradicted (0 ha all years); Rice/Maize
        Rabi appear only in 2024-25 -> kept unverified. STRICT unchanged; LENIENT
        0.83608->0.83590. v1.1 untouched.
  - [x] §12 the two OOV measures (28.1% cells/10y vs 8.5% crops/8y).
      Limitation: llama C2b coverage n=85/150; cluster-bootstrap p floor 1e-4.

### Phase 8.31: DB-version study (update database only; offline)
- [x] STEP 1 scope (`eval/results/DB_SCOPE.md`): db_v1 sha256 `58185292...ea304`; C3 ranking
      uses 7 fields (Crop, Rainfall, Tempreture, Soil Type, season_supported, risk_sensitivity,
      peak_water_week); sowing_start/end_week never affect C3; Zone/humidity never read.
- [x] STEP 2 pre-registration (`eval/PROTOCOL.md` 8.31, 2026-10-16 06:24 UTC): X=3; build
      2015-16..2019-20, test 2020-21..2022-23, sensitivity 2023-24/2024-25; primary ref =
      test-period unrestricted top-5; P@5 + nDCG@5, paired cluster bootstrap, Holm.
- [x] STEP 3 build (`eval/scripts/build_db_v2.py` -> `crop_log_v2.csv` sha256 `dadcb160...4e6e6`,
      `eval/results/DB_V2_DIFF.md`): **added Linseed** (Rabi); excluded "Other Pulses" (aggregate);
      Barley kept Rabi (IIWBR EB-53; Kharif-barley block flagged as anomaly).
- [x] STEP 4 (`eval/scripts/dbv2_deterministic.py`): db_v1 verify 10,000/10,000 match; db_v2 ->
      `eval/runs/db_v2/deterministic/`.
- [x] STEP 5 (`eval/scripts/dbv2_metrics.py` -> `eval/results/db_v2_test.{json,txt}`): db_v2 did
      NOT improve. Primary P@5 0.4396->0.4304, delta **-0.0092** [-0.0159,-0.0031] Holm 9.4e-3;
      nDCG@5 -0.0065 Holm 9.4e-3. Cause: Linseed recommended in 69/500 vs 46 reference cells
      (47 false positives), all in Rabi. Ceiling 0.0876->0.0706.
- [x] STEP 6 (`eval/scripts/dbv2_combined_table.py`): C3 db_v2 beside LLM db_v1 results on the
      same test reference; LLM conditions NOT re-run.
- [x] STEP 7 (`eval/scripts/dbv2_cost_estimate.py`): re-running 5 LLM conditions on db_v2 = ~10,630
      requests / 10.7M in / 4.34M out tokens / ~17.7 h (no dollar cost; no citable price). NOT run.
- [x] STEP 8 report (`eval/results/DB_V2_REPORT.md`). **AWAITING USER APPROVAL.**
      Season validity (10,000 C3, GT v1.2): STRICT 0.83590->0.81132 (Linseed unknown counts
      against strict), LENIENT 0.83590->0.83736.
## S series ("simulated scenarios") — started 2026-10-16
- [x] S-STEP 1 scope note (`eval/results/S_SCOPE.md`): per-tool data sources + harness injection
      points; perturbation FEASIBLE at eval layer (copies only; `mcp_server/` untouched); out-of-scope
      list; forward plan. Weather cache `eval/cache/weather/*.json` (51 files, 2013-12-01..2026-01-15).
- [x] S-STEP 2 perturbation sets (`eval/results/S_PERTURBATIONS.md`): S.W1/W2/W3 (+1/+2/+3 C),
      S.R1/R2/R3 (x0.80/x0.60/x1.30), S.O1/O2 (+14/+28 d onset), S.H1 (sowing-window heat),
      S.C1 (+2 C & -30%), controls S.N0 (identity) / S.N1 (cool-wet), natural exp S.NE15 (2015).
      Each magnitude sourced (PLOS Climate 2025; IMD press release/norms/FAQ; Rohini 2016/2019).
- [x] S-STEP 3 offline oracle (`eval/results/S_ORACLE.md`): feasible set from
      `hard_constraints_v1.1.csv` + `crop_season_table_v1.2.csv`; STRICT (cited) primary + LENIENT
      secondary; contradicted rows invalid; independence from `crop_log.csv` (CIRCULARITY F1/F4).
- [x] S-STEP 4 pre-registration (`eval/PROTOCOL.md` 8.32, 2026-10-16 07:25 UTC): metrics
      Stale@5 (primary) / Violation@5 / Shift@5; contrasts C2a-C0b, C2b-C0b, C2a-C1a, C3-C2b;
      cluster bootstrap; run gate requires approved S_PLAN.
- [x] S-STEP 5 run plan (`eval/results/S_PLAN.md`): tiered; recommended Tier A |B|=40, 11 sets,
      2 models, C0/C0b reused, ~6k-12k completions. **STOP — AWAITING USER APPROVAL before any model call.**
- [x] S-STEP 6 harness built (`eval/s_series/`: perturbations.py, builder.py, oracle.py, base_set.py;
      `eval/scripts/build_s_evidence.py`, `eval/scripts/run_s_series.py`) + base set B=40
      (`eval/results/s_base_set.json`, stratified seed 42). S.N0 reproduces archive_v2/evidence
      exactly (flag delta 0). No model call made.
- [x] S-STEP 7 pre-run signal audit (`eval/results/S_SIGNAL_CHECK.md`): **PROBLEM FOUND.**
      Temperature arms (W1/W2/W3/H1) + uniform-rain arms (R1/R2/R3/C1) move the oracle ~0 -> Stale@5
      (primary) undefined (|D|=0) for 8/11 run sets. Cause: (1) oracle has no heatwave term;
      (2) SPI-1 is exactly scale-invariant to uniform rain multipliers (max |dz| = 0.00 vs x1.30).
      Only O1/O2/NE15 have signal. **STOP - user decision required (amend oracle/perturbations =
      new pre-registration, or run as-is).**
- [x] RUN (blocked → resolved by S-STEP 8 user approval): needs (a) user decision on the
      S_SIGNAL_CHECK finding, (b) eval-layer route for the perturbed cache without touching
      `mcp_server/` (risk tool hardcodes `eval/cache/weather`).
- [x] S-STEP 8 amendment (user approved option 1): oracle v2 adds a sourced heatwave term
      (`eval/data/series/s_heatwave_constraints_v1.0.csv`, `eval/results/S_ORACLE_V2.md`);
      perturbations v2 replace the scale-invariant rain multipliers with shape/intensity arms
      (`eval/s_series/perturbations.py`; `eval/results/S_PERTURBATIONS_V2.md`); N1 is cooling-only.
      New pre-registration `eval/PROTOCOL.md` 8.33 (2026-10-16 08:53 UTC). Re-audited offline:
      every arm moves the oracle correctly (`eval/results/s_oracle_signal.json`).
- [x] S-STEP 9 RUN STARTED (user approved "all 13 arms, both models" 2026-10-16). Launched
      `eval/scripts/run_s_series.py --models nemotron llama`. **NEMOTRON PROVIDER OUTAGE** found.
- [x] S-STEP 9a NPC-1 BUG/INCIDENT (found 2026-10-16 ~23:20 IST, workaround applied):
      `nvidia/nemotron-3-ultra-550b-a55b` returned HTTP **404 "Function id ... is not found"**
      for all 4 keys / all accounts (still listed by `GET /v1/models`). During the outage window
      it degraded first (504 gateway timeouts, then 400s) then went hard-404.
      Consequence: set W1/nemotron completed with **ok=1 err=119** (99% failure) and consumed
      ~9 h, burning budget (failed attempts still reserve budget). Llama unaffected (0.3 s, ok=540).
      Detection: set W1 results.json `error_type` census (model_failure 504 x51, api_status_400
      x45, model_failure 404 x18, DNS/conn x5). Direct probe reproduces the 404 in 0.3 s.
      Bug fix: `run_s_series.py` heartbeat thread now stops on set completion (`stop_hb` event) -
      previously a zombie daemon thread kept printing stale "120/120" heartbeats for hours, which
      made the log look like nemotron was still working.
      TODO fix before next nemotron launch: add a **preflight model health check** to abort a set
      immediately on 404 instead of burning budget/seconds.
- [x] RUN (completed → see S-STEP 9b): llama at 540/1560 ok (W1,W2,W3,H1 COMPLETE; D1 59/120);
      budget `eval/runs/_http_budget.json` = 4000/4000 for UTC 2026-10-16 (resets 05:30 IST).
      Remaining: llama D1-D2,WET1-WET2,O1,O2,C1,NE15,N1; nemotron all 13 sets. Resume after
      UTC-midnight reset (llama) and after the nemotron endpoint recovers.
- [x] S-STEP 9b RUN COMPLETE (2026-10-18): all 13 sets x 2 models x 40 sids x 6 tool conds =
      3120/3120 records present. Retry audit (`eval/results/s_retry_audit.json/.md`,
      2026-10-18T22:12Z): 119 infra failure records (nemotron W1 only: model_failure 74,
      api_status_400 45), ALL re-acquired successfully (119/119). Nemotron recovered after
      NPC-1; raw `s_W1/eval_nemotron-3-ultra` keeps its 119 historical error records next to
      120 ok ones (scorer prefers non-error records on load).
- [x] S-STEP 10 pre-scoring validity (2026-10-19): **20/20 checks PASS**
      (`eval/results/s_sanity.json`). Scoring-time fixes (all offline, no model call, no
      frozen file changed): N0 KeyError; c0 prompt-hash separator (U+241F vs \x1f -> 160/160);
      climate chain-of-custody int-vs-str key hashing (dual-hash rule -> 11660/11660);
      `t0` shadowing crash; coverage reframed presence-vs-usability (119 unusable run cells:
      llama invalid_json 65, nemo invalid 32 + truncated 22); nemotron C0/C0b baseline
      enrichment from canonical runs (3 sids have no usable record anywhere);
      **C3 instrument fix**: registered C3 = run_deterministic_v2 full_repo recompute
      (`eval/scripts/s_c3_recompute.py`, base gate 40/40 vs archive, 560 cells incl. N0) —
      bundle crop_score disagrees on 17/40 base scenarios and is kept only for C2a
      chain-of-custody + overlap. Full bug log: S_REPORT.md section 17.
- [x] S-STEP 10a metric tests (`eval/tests/test_s_metrics.py`): 11/11 pass.
- [x] S-STEP 11 SCORING (2026-10-19T01:25Z, `eval/scripts/score_s.py`, offline): outputs
      `eval/results/s_scores.json`, `s_scores_cells.csv`, `s_sanity.json`. Headline
      (pp, STRICT, WITH_pilot, Stale@5, |D|=0->0 convention): llama C2a-C0b +0.032
      (Holm 0.0012), C2a-C1a +0.030 (0.0004), C3-C2b +0.035 (0.0012) hold under pp AND ITT;
      C2b-C0b ITT-only (+0.010, Holm 0.0348) fails the both-rule; nemotron all 4 contrasts
      null. N0 controls all pass (identity, Shift=0, oracle D=0); N1 direction control
      INCONCLUSIVE (8.32.5 underspecified; both readings shown). Supplementary
      registered-formula (|D|>0) view: `s_score_conditional_supp.py` ->
      `s_scores_conditional.json` (llama C2a-C0b +0.294, same verdicts; 9.1x dilution
      explained in S_REPORT section 5).
- [x] S-STEP 11a FIGURES (2026-10-19, `eval/scripts/s_figures.py`, renders s_scores.json
      only): 5 figures x PDF+PNG+CSV in `eval/results/figures/` (stale/violation/shift by
      set, contrasts forest, movement-not-explained (§14.3 display rename; machine
      keys/filenames unchanged)), CSV rows 156/156/156/16/156.
- [x] S-STEP 12 REPORT (`eval/results/S_REPORT.md`): all tables/CIs, controls, deviations
      (section 16), dated bug log (section 17), plain-word limitations (18), provenance
      table (19), figures list (20). **STOP - AWAITING USER APPROVAL; no commit made.**
- [x] S-STEP 13 EXPLORATORY FOLLOW-UP (PROTOCOL 8.34, registered 2026-10-19 02:44:25 UTC
      BEFORE computation; offline, NO model calls; frozen inputs and registered outputs
      `s_scores.json`/`s_scores_cells.csv`/S_REPORT numbers unchanged). Output:
      `eval/results/S_FOLLOWUP.md` + `s_followup_b6.json`, `s_followup_real_impact.json`,
      `s_followup.json`, `s_followup_cases.json` (scripts `eval/scripts/s_followup*.py`).
      All 8 registered items: (1) B6 root cause = season handling ONLY (17/17;
      `run_deterministic_v2.py:201-203` drops sowing windows; variant==tool 17/17,
      scores 102/102) + real-series impact (242/500 ordered top-5s differ proxy-vs-tool;
      C2a ordered-identical 0.516->0.998, positions 3.34->5.00; scorer P@5 0.5035->0.4833;
      final-answer P@5 unchanged); (2) exposure-conditioned retention (strict exposure
      1.9-6.1%; nemotron C1a 0.39/0.48, C2b lenient 0.33/0.35, C3 0.795 both models);
      (3) delta-violation (no significant increases anywhere; reductions ll C1a/C2a,
      nemotron lenient C2b signal pp+ITT); (4) headline swap - conditional PRIMARY,
      verdicts unchanged (llama 3 hold both-rule, C2b-C0b fails, nemotron strict null) +
      "higher = worse" on every Stale/Violation table & figure title + pooled registered-
      lenient disclosure gap CLOSED (S_FOLLOWUP 4.5 -> S_REPORT 16.11; nemotron C3-C2b
      holds both-rule under lenient only); (5) power/MDD (llama claimable ratios 1.34-1.49;
      nemotron strict nulls underpowered MDD80 0.25-0.37 - not equivalence); (6) five WET
      case studies (all 45 strict candidates are Urad/flood-cited; scorer has NO hard-
      constraint table - flood enters only via 0.15-weighted risk penalty; C2a stored
      top-6 cross-check PASS); (7) display rename "false-change" -> "movement not
      explained by hard-constraint changes" (machine keys/filenames unchanged; figures
      re-rendered for labels only, CSV rows 156/156/156/16/156); (8) methods disclosure
      paragraph (nemotron baseline enrichment + registered-vs-scored Stale@5 convention).
      Reconstruction gate PASS 12 480 cells / 0 mismatch at 1e-6 (bug F1; iteration log
      F1-F3 in S_FOLLOWUP section 11). **STOP - AWAITING USER APPROVAL; no commit made.**

---

### Phase 8.35: Instrument Correction (C3t) — COMPLETED 2026-10-20

- [x] Delete `eval/scripts/test_multikey.py` (exposed 3 real NVIDIA API keys)
- [x] Add `.env.example` with placeholder env var names only
- [x] Register PROTOCOL §8.35 (instrument correction, not tuning) at 2026-10-19 22:56:19 UTC
- [x] Run `c3t_recompute.py` — all gates PASS:
    - g_det_v1 (C3 replica == archive det, db_v1): 10000/10000
    - g_det_v2 (C3 replica == db_v2 det, db_v2): 10000/10000
    - g_tool (C3t == stored bundle crop_score): 10000/10000 (base40: 40/40)
    - g_s_base (C3t N0 == C3t archive base): 40/40
- [x] Run `c3t_correction.py` — full metric recomputation:
    - Season validity (10k): C3 0.9999 → C3t 0.9048 (strict); Hard violation: C3 0.6893 → C3t 0.8051 (strict)
    - Real-data P@5 (R_prim, n=500): C3 0.5035 → C3t 0.4833
    - S-series: 560 cells recomputed with C3t
    - 45 WET candidates: 14 C3 + 31 C2a (all Urad/flood-cited)
- [x] Write `eval/reports/CORRECTION_NOTE.md` with old-vs-new table
- [x] Append cross-references to `REAL_EVAL_REPORT.md` §10 and `S_REPORT.md` §16.7
- [x] Commit: `5efd9db security: remove exposed test script, add .env.example; register instrument correction`

**Total tasks: ~38 | Completed: 26 | In progress: 1 | Blocked: 0 | Progress: 68%**
