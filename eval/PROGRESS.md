# Evaluation Progress Checklist

Last updated: 2026-10-10 03:13 UTC

## Legend: [ ] pending | [~] in progress | [x] done | [!] blocked

---

### Phase 0: Audit & Protocol
- [x] REPO_AUDIT.md written (2026-10-09)
- [x] PROTOCOL.md written (2026-10-09)
- [x] config.yaml frozen (2026-10-09)
- [x] config SHA256: 2fe37c276ce663f3d1db6cbc5f3b6c2553e35c1ddeec6952bc16c344c5f82b6f

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
- [ ] Part 4: Cross-model comparison design (Fig_M01-M10)
- [ ] Part 5: Report template updates

### Phase 4: LLM Experiments (per selected model)
- [~] PRIMARY model: nvidia/nemotron-3-ultra-550b-a55b
  - [x] Pilot: 30 scenarios × 4 conditions (C0, C0b, C1, C2) - PARTIAL (cache has 52/120 calls)
  - [ ] Full: 500 scenarios × 4 conditions (paired subset)
  - [ ] Consistency: 100 scenarios × 3 repeats × 4 conditions
- [ ] SECOND_FAMILY model: z-ai/glm-5.3
  - [ ] Pilot + Full on paired subset (150 scenarios)
  - [ ] Consistency on 50 scenarios
- [ ] SMALL model: meta/llama-3.2-11b-vision-instruct
  - [ ] Pilot + Full on paired subset (150 scenarios)
  - [ ] Consistency on 50 scenarios

### Phase 5: Analysis & Figures
- [ ] Quality/safety/specificity/reliability/consistency/efficiency metrics (all conditions, all models)
- [ ] Bootstrap CIs, paired tests, effect sizes (STEP 7)
- [ ] Figures E07-E17 (original plan)
- [ ] Figures M01-M08 (cross-model comparison)
- [ ] All aggregates as CSV + LaTeX

### Phase 6: Report
- [ ] RESULTS_REPORT.md + .docx with all sections
- [ ] Claims audit table
- [ ] Paper-ready replacement text
- [ ] Reproduction instructions

---

**Total tasks: ~38 | Completed: 17 | In progress: 1 | Blocked: 0 | Progress: 45%**