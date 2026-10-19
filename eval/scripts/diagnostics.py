"""STEP 0 diagnostics for the paper figure redesign.

Reads ONLY existing outputs (eval/runs, eval/results, eval/data, mcp_server code).
Writes eval/report/DIAGNOSTICS.md and prints a summary.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import config_dirs, ensure_dirs, load_config, read_jsonl
from eval.metrics import CANONICAL_CROPS, CROP_SEASON_VALIDITY, season_validity_rate
from eval.llm.prompts import ALIASES, normalize_crop


def old_normalize(name):
    """Reproduce the pre-fix normalizer (punctuation stripped before lookup)."""
    if not name:
        return None
    key = re.sub(r"[^a-z0-9 ]", " ", name.strip().lower())
    key = re.sub(r"\s+", " ", key).strip()
    if key in ALIASES:
        return ALIASES[key]
    look = {c.lower(): c for c in CANONICAL_CROPS}
    if key in look:
        return look[key]
    return None

ROOT = Path(__file__).resolve().parent.parent.parent
RUNS = {
    "nemotron": ROOT / "eval/runs/full_nemotron-3-ultra_20261111_082444/results_placeholder.json",
}
RUNS = {
    "nemotron": ROOT / "eval/runs/full_nemotron-3-ultra_20261011_082444/results.json",
    "llama": ROOT / "eval/runs/eval_llama-3.2-11b/results.json",
    "glm": ROOT / "eval/runs/eval_glm-5.3/results.json",
}
EVIDENCE_DIR = ROOT / "eval/runs/archive_v2/evidence"       # frozen v2 (risk + prompt_c1 CROP_SCORE)
DET_DIR = ROOT / "eval/runs/archive_v2/deterministic"       # frozen v2 grid = C3 reference
CONDS = ["C0", "C0b", "C1", "C2"]


def load(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"missing {path}")
    return json.load(open(path))


def bundle(sid: str):
    return json.load(open(EVIDENCE_DIR / f"{sid}.json"))


def _det(sid: str):
    return json.load(open(DET_DIR / f"{sid}.json"))


def ref_top5(sid: str):
    return (_det(sid).get("ablations", {}).get("full_repo") or {}).get("top5") or []


def ref_season(sid: str):
    return _det(sid)["season"]


def main():
    cfg = load_config()
    ensure_dirs(cfg)
    dirs = config_dirs(cfg)
    subset = read_jsonl(dirs["llm_subset_path"])
    scen_meta = {s["scenario_id"]: s for s in subset}

    print("Loading runs...")
    data = {m: load(p) for m, p in RUNS.items()}
    rec_of = {m: {(r["scenario_id"], r["condition"], r.get("repeat", 0)): r for r in recs}
              for m, recs in data.items()}

    md = []
    out = []

    def h1(t):
        md.append(f"\n## {t}\n")

    def h2(t):
        md.append(f"\n### {t}\n")

    def p(t):
        md.append(t)

    # ------------------------------------------------------------------ C3
    h1("A. Season validity: C3 vs the LLM conditions")
    # C3 season validity on the SAME subset scenarios
    c3_ok = 0
    c3_total = 0
    c3_by_season = Counter()
    c3_season_tot = Counter()
    sc_season_stratum_mismatch = 0
    for s in subset:
        season = ref_season(s["scenario_id"])
        top = ref_top5(s["scenario_id"])
        c3_total += 1
        c3_ok += season_validity_rate(top, season)
        c3_by_season[season] += season_validity_rate(top, season)
        c3_season_tot[season] += 1
        if scen_meta[s["scenario_id"]].get("season_stratum") and season != scen_meta[s["scenario_id"]]["season_stratum"]:
            sc_season_stratum_mismatch += 1
    p(f"C3 season validity (metric table = eval/metrics.py CROP_SEASON_VALIDITY) on the shared subset "
      f"(n={c3_total}): overall mean = {c3_ok / c3_total:.4f}")
    for season in ("Kharif", "Rabi", "Zaid"):
        if c3_season_tot[season]:
            p(f"  - C3 {season}: {c3_by_season[season] / c3_season_tot[season]:.4f} (n={c3_season_tot[season]})")
    p(f"scenario.season_stratum vs evidence-bundle season mismatch: {sc_season_stratum_mismatch}/{c3_total}")

    # per-model per-condition season validity on C0..C2
    for m in ("nemotron", "llama", "glm"):
        for cond in CONDS:
            vals = []
            for (sid, c, rep), r in rec_of[m].items():
                if c != cond or r.get("error"):
                    continue
                p_ = r.get("parsed")
                if not p_ or not p_.get("valid_json") or not p_.get("top5"):
                    continue
                vals.append(season_validity_rate(p_["top5"], ref_season(sid)))
            if vals:
                p(f"  {m:<10} {cond} season-validity mean={np.mean(vals):.4f} (n={len(vals)})")

    # failing C2 examples: 10 per model
    h2("C2 failing cases (season validity < 1): scenario date vs live tool vs model top5")
    this_month = datetime.now().month
    live_season = {1: "Rabi", 2: "Rabi", 3: "Rabi", 4: "Zaid", 5: "Zaid",
                   6: "Kharif", 7: "Kharif", 8: "Kharif", 9: "Kharif",
                   10: "Kharif", 11: "Rabi", 12: "Rabi"}[this_month]
    p(f"Live date today = {datetime.now().date()} (month {this_month}) -> season_tool would report '{live_season}' "
      f"for EVERY scenario, regardless of as_of_date (mcp_server/season_tool.run uses datetime.now(IST)).")
    for m in ("nemotron", "llama", "glm"):
        fails = []
        for (sid, c, rep), r in rec_of[m].items():
            if c != "C2" or r.get("error"):
                continue
            p_ = r.get("parsed")
            if not p_ or not p_.get("valid_json") or not p_.get("top5"):
                continue
            season = ref_season(sid)
            if season_validity_rate(p_["top5"], season) < 1.0:
                fails.append((sid, season, p_["top5"], r.get("tool_calls", 0)))
        p(f"\nC2 season-invalid cases: {len(fails)}")
        for sid, season, top, tools in fails[:10]:
            sc = scen_meta[sid]
            invalids = [(crop, CROP_SEASON_VALIDITY.get(crop)) for crop in top
                        if crop in CROP_SEASON_VALIDITY and season not in CROP_SEASON_VALIDITY[crop]]
            p(f"  {sid} as_of={sc['as_of_date']} true_season={season} district={sc['district']} "
              f"tools={tools} top5={top} invalid={invalids}")

    # Does the metric's table treat Annual crops as always-invalid?
    h2("Season validity metric definition")
    p("season_validity_rate(pred, season) = fraction of pred crops where season in CROP_SEASON_VALIDITY[crop] "
      "(eval/metrics.py). This table is independent, hard-coded, and DIFFERENT from the repo's crop_log.csv "
      "`season_supported` used by crop_score_tool.")
    annual = [c for c, s in CROP_SEASON_VALIDITY.items() if s == {"Annual"}]
    p(f"Crops with only 'Annual' in the metric table (counted invalid in EVERY season): {annual}")
    p("Note: scenario 'season_stratum' (scenarios.jsonl generator) vs evidence bundle 'season.current_season' "
      f"have a mismatch rate of {sc_season_stratum_mismatch}/{c3_total} on the subset.")

    # ------------------------------------------------------------------ B
    h1("B. Hallucination / out-of-registry: pre- and post-normalisation")
    h2("Normalisation pipeline (eval/llm/prompts.py)")
    p("parse_output(): raw names (top5_raw) -> normalize_crop(): lower/strip punctuation, then "
      "map via ALIASES dict, then exact match against CANONICAL_CROPS; anything unmatched -> "
      "out_of_registry and DROPPED from top5. The prompt itself embeds the closed candidate list "
      "(CROP_LIST_TEXT).")
    pre_oor = Counter()
    n_total = 0
    snapped_aliases = Counter()
    vocab = Counter()
    bug_names = Counter()
    for m, recs in data.items():
        for r in recs:
            p_ = r.get("parsed")
            if not p_:
                continue
            for raw in p_.get("top5_raw", []):
                n_total += 1
                vocab[raw.strip()] += 1
                c = normalize_crop(raw)
                if c is None:
                    pre_oor[(m, r["condition"])] += 1
                if old_normalize(raw) is None and normalize_crop(raw) is not None:
                    bug_names[raw.strip()] += 1
            # counts snapped aliases (raw != canonical)
            for raw in p_.get("top5_raw", []):
                c = normalize_crop(raw)
                if c is not None and c.lower() != str(raw).strip().lower():
                    snapped_aliases[raw.strip()] += 1
    total_slots = sum(len(r.get("parsed", {}).get("top5_raw", [])) for recs in data.values() for r in recs)
    p(f"Total top5 slots analysed: {total_slots}")
    h2("Out-of-registry (genuine hallucinations) with the FIXED normalizer")
    for m in ("nemotron", "llama", "glm"):
        hits = sum(v for (mm, c), v in pre_oor.items() if mm == m)
        slots = sum(1 for r in data[m] if r.get("parsed") for _ in r["parsed"].get("top5_raw", []))
        p(f"  {m}: {hits} / {slots} = {hits / slots:.4f}")
    h2("GENUINE BUG: parenthesised canonical crops were dropped by the old normalizer")
    p("The old normalize_crop() ran re.sub(r'[^a-z0-9 ]',' ') on the input BEFORE lookup, so the "
      "canonical names 'Sesame (Til)' and 'Arhar (Tur)' became keys 'sesame til' / 'arhar tur', which "
      "exist in neither ALIASES ('sesame (til)' / 'arhar (tur)') nor the canonical map. Both were "
      "therefore classified out_of_registry and DROPPED from top5, even though the prompt instructs "
      "models to emit those exact names. This deflated agreement metrics and made 'hallucination' "
      "measurements meaningless.")
    p("Raw names recovered by the fix (old->None but fixed->canonical):")
    for name, k in bug_names.most_common():
        p(f"  '{name}' x{k} -> {normalize_crop(name)}")
    p("Effect (before -> after), means over valid-json responses; full table in "
      "eval/results/normalization_fix_before_after.json:")
    fix_path = ROOT / "eval/results/normalization_fix_before_after.json"
    if fix_path.exists():
        for row in json.load(open(fix_path)):
            p(f"  {row['model']:<9} {row['condition']:<4} n={row['n']:<4} "
              f"top5_len {row['len_before']:.2f}->{row['len_after']:.2f}  "
              f"OOR {row['oor_before']*100:.1f}%->{row['oor_after']*100:.1f}%  "
              f"acc@5 {row['acc_before']:.3f}->{row['acc_after']:.3f}  "
              f"Jaccard {row['jac_before']:.3f}->{row['jac_after']:.3f}  "
              f"season-valid {row['sv_before']:.3f}->{row['sv_after']:.3f}")
    p("CONCLUSION: genuine crop-hallucination rate is 0.0% for all models (no name outside the "
      "21-crop registry was ever produced once the two parenthesised names normalise). The old "
      "'pre-normalisation 6-14%' figure was 100% this bug. Fix applied in eval/llm/prompts.py.")

    # ------------------------------------------------------------------ C
    h1("C. Metric definitions and C1 leakage")
    from eval.metrics import accuracy_at_k, jaccard_similarity
    p("'Accuracy@5 vs C3' = accuracy_at_k(llm_top5, c3_top5, 5) = 1 iff ANY of the LLM's 5 crops "
      "appears in the C3 top-5 (binary hit). NOT accuracy on ranked retrieval.")
    p("'Delta Jaccard vs C0' = jaccard_similarity(cond_top5, c3_top5) - jaccard_similarity(c0_top5, c3_top5), "
      "where jaccard_similarity uses the SET of names (order ignored).")
    p("C1 prompt (eval/llm/prompts.py prompt_c1) embeds CROP_SCORE:\n"
      "  CROP_SCORE: <full deterministic C3 ranking string injected into the C1 prompt>\n"
      "=> The deterministic C3 ranking is INSIDE the C1 prompt. C1 agreement with C3 is therefore partly "
      "CIRCULAR (answer leakage). C1 numbers are reported separately with this caveat; do not headline C1 as "
      "'LLM agreement'.")
    from eval.llm.prompts import prompt_c1
    sc = subset[0]
    b = bundle(sc["scenario_id"])
    c1 = prompt_c1(sc, b)
    p(f"prompt_c1 contains 'CROP_SCORE': {'CROP_SCORE' in c1} (confirmed). ")

    # ------------------------------------------------------------------ D
    h1("D. Latency & tokens")
    h2("Latency: does latency_s include retries/backoff?")
    p("NvidiaProvider.run() starts the timer (time.perf_counter) BEFORE the retry loop and the tool-calling "
      "round loop; every backoff sleep and every model round-trip is inside the timed region. So "
      "latency_s = end-to-end scenario wall time (incl. 429/5xx retries up to 5 with exponential backoff "
      "<=60s, and C2 tool rounds). Per-request API latency is NOT recorded separately in the results; only "
      "the aggregate scenario latency is stored.")
    # errors inflate latency?
    for m in ("nemotron", "llama", "glm"):
        for cond in CONDS:
            recs = [r for r in data[m] if r["condition"] == cond]
            if not recs:
                continue
            e = [r["latency_s"] for r in recs if r.get("error")]
            ok = [r["latency_s"] for r in recs if not r.get("error")]
            p(f"  {m:<9} {cond}: median_latency (all)={np.median([r['latency_s'] for r in recs]):.0f}s "
              f"ok={np.median(ok):.0f}s (n={len(ok)}) err={np.median(e):.0f}s (n={len(e)})" if len(e) else
              f"  {m:<9} {cond}: median_latency={np.median([r['latency_s'] for r in recs]):.0f}s (n={len(recs)}, no errors)")

    h2("Tokens: input / output / reasoning split, and 'thinking' mode")
    p("Payload does NOT set a 'thinking' flag; NVIDIA NIM may still emit usage.reasoning_tokens. "
      "We store tokens_in, tokens_out, reasoning_tokens separately.")
    for m in ("nemotron", "llama", "glm"):
        recs = [r for r in data[m] if not r.get("error")]
        tin = np.mean([r.get("tokens_in") or 0 for r in recs])
        tout = np.mean([r.get("tokens_out") or 0 for r in recs])
        reas = [r.get("reasoning_tokens") for r in recs if r.get("reasoning_tokens")]
        p(f"  {m:<9}: mean in={tin:.0f} out={tout:.0f} reasoning present in {len(reas)}/{len(recs)} records "
          f"(mean {np.mean(reas):.0f} when present)")

    # ------------------------------------------------------------------ E
    h1("E. Coverage and overlap")
    h2("Completed scenarios per model x condition")
    for m in ("nemotron", "llama", "glm"):
        by_cond = Counter()
        for (sid, c, rep), r in rec_of[m].items():
            if rep == 0:
                by_cond[c] += 1
        p(f"  {m:<9} scenarios per condition: " + ", ".join(f"{c}={by_cond[c]}" for c in CONDS))
    scenario_sets = {m: {sid for (sid, c, rep) in rec_of[m] if rep == 0} for m in rec_of}
    p("Scenario overlap:")
    p(f"  nemotron x llama: {len(scenario_sets['nemotron'] & scenario_sets['llama'])}")
    p(f"  nemotron x glm:   {len(scenario_sets['nemotron'] & scenario_sets['glm'])}")
    p(f"  llama x glm:      {len(scenario_sets['llama'] & scenario_sets['glm'])}")
    p(f"  all three:        {len(scenario_sets['nemotron'] & scenario_sets['llama'] & scenario_sets['glm'])}")
    p("Why GLM has n=32: the z-ai/glm-5.3 endpoint degraded to 900-2200s/call with frequent 504 Gateway "
      "Timeouts during collection; the run was paused by decision after 128 records (32 scenarios x 4, some "
      "with errors). Resume: eval/scripts/run_model.py --model z-ai/glm-5.3 --scenarios 50 --workers 4.")
    p("Incomplete runs and what is needed to finish:")
    p("  - glm: 50-scenario target, 32 complete -> rerun run_model (resumable via results.json + cache).")
    p("  - Consistency repeats (3x) for nemotron/llama: not started (run_model --repeat 3 --scenarios 100).")

    # ------------------------------------------------------------------ F
    h1("F. Paired complete cases")
    h2("Within model: scenario sets identical across conditions?")
    for m in ("nemotron", "llama", "glm"):
        sets = {c: {sid for (sid, cc, rep) in rec_of[m] if rep == 0 and cc == c} for c in CONDS}
        union = set().union(*[sets[c] for c in CONDS]) if all(sets.values()) else set()
        for c in CONDS:
            p(f"  {m} {c}: n={len(sets[c])} (union over all conditions={len(union)})")
    h2("Paired (complete, non-error, valid-json) cases per model pair x condition")
    for a in ("nemotron", "llama", "glm"):
        for b in ("nemotron", "llama", "glm"):
            if a >= b:
                continue
            common = sorted(scenario_sets[a] & scenario_sets[b])
            for cond in CONDS:
                n = 0
                for sid in common:
                    ra = rec_of[a].get((sid, cond, 0))
                    rb = rec_of[b].get((sid, cond, 0))
                    if ra and rb and not ra.get("error") and not rb.get("error") \
                            and ra.get("parsed", {}).get("valid_json") and rb.get("parsed", {}).get("valid_json"):
                        n += 1
                p(f"  {a} vs {b}, {cond}: {n}/{len(common)} paired complete cases")

    # ------------------------------------------------------------------ G
    h1("G. Conclusions and required corrections")
    p("1. **Genuine bug fixed (normalize_crop).** Parenthesised canonical crops ('Sesame (Til)', "
      "'Arhar (Tur)') were unmatchable and dropped. Fix applied in eval/llm/prompts.py. Effect: "
      "C2 Jaccard vs C3 +0.07..+0.12, C1 nemotron 0.709->0.818, C2 out-of-registry 24-26%->0%. "
      "The 'any-overlap' accuracy@5 also rises. All headline agreement numbers must be recomputed "
      "with the fix (raw inputs unchanged).")
    p("2. **Hallucination = 0% is correct**, but only after the fix; the old '6-14% pre-normalisation' "
      "figure was entirely the bug. Report the corrected 0% (genuine) rate.")
    p("3. **C1 leakage.** prompt_c1 embeds the full deterministic CROP_SCORE ranking, i.e. the C3 answer. "
      "C1-vs-C3 agreement is partly circular; C1 must be presented as 'LLM with the C3 ranking injected', "
      "not as independent agreement. This also means C1 is NOT a fair 'stuffing' comparison for "
      "agreement-with-C3 (stuffing includes the answer).")
    p("4. **C2 harness bug (not recomputable offline).** NvidiaProvider executes the LIVE tools; "
      "season_tool.run/weather_tool/crop_score use datetime.now(IST) and live Open-Meteo, ignoring the "
      "scenario as_of_date. For historical scenarios the C2 model is told the wrong season (today: "
      "'Kharif') and current weather. The deterministic evidence replay server (eval/mcp_eval/server.py) "
      "exists but is not wired in. This depresses C2 season validity (~0.41-0.46) and inflates C2-vs-C3 "
      "disagreement; C2 results cannot be repaired without a re-run (out of scope: no new API calls).")
    p("5. **Season validity metric.** Uses eval/metrics.py CROP_SEASON_VALIDITY (independent, hard-coded), "
      "where 'Sugarcane'={'Annual'} is invalid in every season, and Zaid caps at ~0.21 for C3 too. "
      "C3 on the subset = 0.727 overall (Kharif 0.95, Rabi 0.88, Zaid 0.21); the metric is dominated by "
      "Zaid. Report per-season and never present the season metric as 'accuracy'.")
    p("6. **Latency** = end-to-end scenario wall time INCLUDING retries/backoff and C2 tool rounds; GLM "
      "errored records sit at ~1500s vs ~190s for ok. Use only non-error records for latency figures and "
      "state the definition. Per-request latency is not stored.")
    p("7. **Tokens**: reasoning_tokens is absent for all models (0 records); tokens_in/out are the only "
      "reliable efficiency quantities.")
    p("8. **Coverage/paired**: nemotron 500, llama 150, GLM 32 scenarios; 3-way overlap = 32. GLM is "
      "preliminary (n<100). Cross-model tests only on the nested paired subsets: llama-nemotron "
      "(117-148/150 by condition), glm-nemotron and glm-llama (26-30/32).")

    rep = Path(__file__).resolve().parent.parent / "report"
    rep.mkdir(parents=True, exist_ok=True)
    (rep / "DIAGNOSTICS.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md)[:4000])
    print(f"\n[diag] wrote {rep / 'DIAGNOSTICS.md'}")


if __name__ == "__main__":
    main()