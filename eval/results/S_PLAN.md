# S-series run plan (STEP 5) — AWAITING APPROVAL

Status: **STOP — no model call has been or will be made until the user approves this plan.**
Pre-registration: `eval/PROTOCOL.md` §8.32 (2026-10-16 07:25 UTC). Design: `S_SCOPE.md`,
`S_PERTURBATIONS.md`, `S_ORACLE.md`. All counts below are ESTIMATES (not measured).

## 1. Question and design
Paired design: for each base scenario, run each condition at **base** and at each **perturbed** set,
then compare the SAME condition's advice base→perturbed. Prediction: tool conditions
(C1a/C2a/C2b/C3) move (Stale@5 falls, Shift@5 rises) under perturbation; no-tool conditions
(C0/C0b) do not move (identical prompt → reused, expected Shift@5 = 0).

Conditions (PROTOCOL §): C0 (plain, no tool), C0b (strong prompt, no tool), C1a (evidence pasted
into prompt, no function calling), C2a (all tools incl. crop_score), C2b (tools minus crop_score),
C3 (deterministic scorer, no LLM).

## 2. Base scenario set (to be fixed, deterministic)
- **Tier A base set `B_A`: 40 scenarios** = the `pilot_dev` split (deterministically sampled,
  seed 42), stratified to cover Kharif / Rabi / Zaid. This matches the real series' pilot discipline.
- **Optional Tier B (scale-up)**: extend to 150 for the primary sets only, if Tier A shows signal.
- `as_of_date` is FIXED per scenario across all sets (so C0/C0b prompts are identical → reusable);
  only the weather copy (and, for S·O1/O2, the as_of month if it crosses a season boundary) differs.

## 2b. Which sets need fresh model calls
- Reused (no new calls): **C0, C0b** (prompt unchanged; reuse cached base outputs per PROTOCOL reuse policy).
- Deterministic (no model call): **C3** (scorer; recomputed on perturbed evidence).
- Perturbation sets that require fresh model runs (C1a/C2a/C2b): S·W1, W2, W3, R1, R2, R3, O1, O2,
  H1, C1, plus control S·N1 → **11 sets**; plus **base** itself → **12 run columns**.
  - S·N0 (identity) needs no model run: verified by asserting replay()==base evidence on 5 scenarios.
  - S·NE15 (natural experiment) is a **separate optional block** (real 2015-year replay), not in the core 12.

## 2b. Condition/model matrix
Models: nemotron-3-ultra (primary), llama-3.2-11b-vision (secondary, 40 `pilot_union`).
Conditions run fresh per column: C1a, C2a, C2b (+ C3 free). C0/C0b reused.

## 3. Call / token / time estimate (ESTIMATE ONLY)
Per scenario per column: C1a = 1 completion; C2a ≈ 7 (6 tool calls + final); C2b ≈ 6 → ~14 completions.
Tier A (nemotron only): 40 scenarios × 12 columns × 14 ≈ **6,700 completions**.
Add llama (40 pilot_union × 12 × (C1a + C2a{+top5-stall} + C2b)) ≈ ~4,000. **Both models ≈ 10–11k completions.**

| item | low | high | basis |
|---|---|---|---|
| completions | 6,000 | 18,000 | Tier A only (nemotron) → Tier A both models w/ retries |
| prompt+output tokens | ~15 M | ~45 M | ≈3.5k tokens/completion
| wall-clock | ~4 h | ~14 h | 2–5 s/completion incl. tool round-trips/retries
| provider cost | $0 (archived runs used free tier) — **confirm current quota** | | `eval/models/QUOTA.md` |

These are rough; the run step will log actuals. **No payment/credits decision is implied; user
approval of wall-clock + quota is required.**

## 4. Abort rules (inherited from §8.30; fixed before run)
Abort a batch on: (a) any provider error ≥ threshold; (b) invalid-JSON rate < 90%; (c) any
hallucinated/unknown tool call; (d) any S·N0 mismatch (harness invalidity); (e) 429 rate > 10%;
(f) NEMOTRON valid-JSON < 90% at the 4096 cap. A failed batch is re-run up to the documented limit,
then recorded as failed (not silently dropped).

## 5. Outputs
- `eval/results/S_REPORT.md` — headline Stale@5 / Violation@5 / Shift@5 with CIs and the four
  pre-registered contrasts (per-protocol + ITT), STRICT primary + LENIENT secondary.
- `eval/results/S_ORACLE_STRICT.csv`, `S_ORACLE_LENIENT.csv` — oracle feasible sets per scenario×set.
- Per-set `eval/runs/S_<set>/` artifacts; `eval/PROGRESS.md` updated. Report ends awaiting approval.

## 6. Decision requested from the user (pick one / adjust)
1. **Tier A only** (|B| = 40, 11 sets, both models) — smallest informative run; ~6k–12k completions. *(Recommended)*
2. Tier A + Tier B scale-up (|B| = 150 on 4 primary sets).
3. Extend Tier A with S·NE15 (natural experiment) and/or a soil/KB extra arm.
4. Reduce models to nemotron only.
Also: confirm the beyond-range arms (W3, R2, O2) may run, or hold them for a second batch.

**Until one is chosen, STEP 5 is complete and we stop here.**
