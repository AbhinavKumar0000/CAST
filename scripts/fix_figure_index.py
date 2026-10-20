import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

rows = [
    {
        "figure_id": "F1",
        "title": "Precision@5 per condition (both models)",
        "script": "figures/scripts/real_eval_figures.py",
        "data_csv": "figures/data/real/fig1_agreement_levels.csv",
        "output_pdf": "figures/out/fig1_agreement_levels.pdf",
        "output_png": "figures/out/fig1_agreement_levels.png",
        "protocol_section": "PROTOCOL 8.30",
        "condition_palette": "C0:#0072B2 C0b:#56B4E9 C1a:#009E73 C2a:#D55E00 C2b:#E69F00 C3:#000000",
        "models": "nemotron llama",
        "notes": "Headline R_prim reference; district-clustered bootstrap CIs"
    },
    {
        "figure_id": "F2",
        "title": "Contrast forest (nDCG@5 contrasts vs baselines)",
        "script": "figures/scripts/real_eval_figures.py",
        "data_csv": "figures/data/real/fig2_contrast_forest.csv",
        "output_pdf": "figures/out/fig2_contrast_forest.pdf",
        "output_png": "figures/out/fig2_contrast_forest.png",
        "protocol_section": "PROTOCOL 8.30",
        "condition_palette": "C0:#0072B2 C0b:#56B4E9 C1a:#009E73 C2a:#D55E00 C2b:#E69F00 C3:#000000",
        "models": "nemotron llama",
        "notes": "Forest plot of registered contrasts"
    },
    {
        "figure_id": "F3",
        "title": "Reference-definition sensitivity (R_prim, R_full, R_all, R_prod)",
        "script": "figures/scripts/real_eval_figures.py",
        "data_csv": "figures/data/real/fig3_reference_sensitivity.csv",
        "output_pdf": "figures/out/fig3_reference_sensitivity.pdf",
        "output_png": "figures/out/fig3_reference_sensitivity.png",
        "protocol_section": "PROTOCOL 8.30",
        "condition_palette": "C0:#0072B2 C0b:#56B4E9 C1a:#009E73 C2a:#D55E00 C2b:#E69F00 C3:#000000",
        "models": "nemotron llama",
        "notes": "Sensitivity to reference definition"
    },
    {
        "figure_id": "F4",
        "title": "Season validity & hard violation per condition (C3 + C3t)",
        "script": "figures/scripts/n500_figures.py",
        "data_csv": "figures/data/n500/Fig_N01_condition_quality.csv",
        "output_pdf": "figures/out/Fig_N01_condition_quality.pdf",
        "output_png": "figures/out/Fig_N01_condition_quality.png",
        "protocol_section": "PROTOCOL 8.11/8.35",
        "condition_palette": "C0:#0072B2 C0b:#56B4E9 C1a:#009E73 C2a:#D55E00 C2b:#E69F00 C3:#000000 C3t:#555555",
        "models": "nemotron",
        "notes": "Reconciled C3/C3t numbers from CORRECTION_NOTE.md"
    },
    {
        "figure_id": "F5",
        "title": "Per-district spread of registered effect (51 districts)",
        "script": "figures/scripts/n500_figures.py",
        "data_csv": "figures/data/n500/Fig_N04_district_variation.csv",
        "output_pdf": "figures/out/Fig_N04_district_variation.pdf",
        "output_png": "figures/out/Fig_N04_district_variation.png",
        "protocol_section": "PROTOCOL 8.29b",
        "condition_palette": "C0:#0072B2 C0b:#56B4E9 C1a:#009E73 C2a:#D55E00 C2b:#E69F00 C3:#000000",
        "models": "nemotron",
        "notes": "District-level C2b-C0b effect distribution"
    },
    {
        "figure_id": "F6",
        "title": "Tool vs pipeline top-5 agreement (B6: C3, C3t, stored bundle)",
        "script": "figures/scripts/n500_figures.py",
        "data_csv": "figures/data/n500/Fig_N07_c2a_vs_c3.csv",
        "output_pdf": "figures/out/Fig_N07_c2a_vs_c3.pdf",
        "output_png": "figures/out/Fig_N07_c2a_vs_c3.png",
        "protocol_section": "PROTOCOL 8.34/8.35",
        "condition_palette": "C0:#8c8c8c C0b:#4d4d4d C1a:#1f77b4 C2a:#d62728 C2b:#ff7f0e C3:#2ca02c",
        "models": "nemotron llama",
        "notes": "C3 vs C3t vs stored bundle crop_score"
    },
    {
        "figure_id": "F7",
        "title": "db_v1 vs db_v2 (Linseed) test-window diagnostic",
        "script": "figures/scripts/n500_figures.py",
        "data_csv": "figures/data/n500/dbv2_diagnostic.csv",
        "output_pdf": "figures/out/dbv2_diagnostic.pdf",
        "output_png": "figures/out/dbv2_diagnostic.png",
        "protocol_section": "PROTOCOL 8.31",
        "condition_palette": "C0:#8c8c8c C0b:#4d4d4d C1a:#1f77b4 C2a:#d62728 C2b:#ff7f0e C3:#2ca02c",
        "models": "nemotron llama",
        "notes": "Test window P@5/nDCG@5; Linseed false positives"
    },
    {
        "figure_id": "F8",
        "title": "Coverage and usable-run rates per condition",
        "script": "figures/scripts/n500_figures.py",
        "data_csv": "figures/data/n500/coverage_rates.csv",
        "output_pdf": "figures/out/coverage_rates.pdf",
        "output_png": "figures/out/coverage_rates.png",
        "protocol_section": "PROTOCOL 8.11",
        "condition_palette": "C0:#8c8c8c C0b:#4d4d4d C1a:#1f77b4 C2a:#d62728 C2b:#ff7f0e C3:#2ca02c",
        "models": "nemotron llama",
        "notes": "pp vs ITT cells"
    },
    {
        "figure_id": "F9",
        "title": "S-series Violation@5 per condition (both models)",
        "script": "figures/scripts/s_figures.py",
        "data_csv": "figures/data/s/violation_by_set.csv",
        "output_pdf": "figures/out/violation_by_set.pdf",
        "output_png": "figures/out/violation_by_set.png",
        "protocol_section": "PROTOCOL 8.32/8.33",
        "condition_palette": "C0:#8c8c8c C0b:#4d4d4d C1a:#1f77b4 C2a:#d62728 C2b:#ff7f0e C3:#2ca02c",
        "models": "llama nemotron",
        "notes": "pp and ITT"
    },
    {
        "figure_id": "F10",
        "title": "S-series Shift@5 per condition per perturbation set",
        "script": "figures/scripts/s_figures.py",
        "data_csv": "figures/data/s/shift_by_set.csv",
        "output_pdf": "figures/out/shift_by_set.pdf",
        "output_png": "figures/out/shift_by_set.png",
        "protocol_section": "PROTOCOL 8.32/8.33",
        "condition_palette": "C0:#8c8c8c C0b:#4d4d4d C1a:#1f77b4 C2a:#d62728 C2b:#ff7f0e C3:#2ca02c",
        "models": "llama nemotron",
        "notes": "All 13 perturbation sets"
    },
    {
        "figure_id": "F11",
        "title": "S-series Stale@5 conditional (|D|>0) with n exposed",
        "script": "figures/scripts/s_figures.py",
        "data_csv": "figures/data/s/stale_conditional.csv",
        "output_pdf": "figures/out/stale_conditional.pdf",
        "output_png": "figures/out/stale_conditional.png",
        "protocol_section": "PROTOCOL 8.32/8.33/8.34",
        "condition_palette": "C0:#8c8c8c C0b:#4d4d4d C1a:#1f77b4 C2a:#d62728 C2b:#ff7f0e C3:#2ca02c",
        "models": "llama nemotron",
        "notes": "Conditional on signal cells; n_exposed shown"
    },
    {
        "figure_id": "F12",
        "title": "S-series Stale@5 as-scored (0-filled)",
        "script": "figures/scripts/s_figures.py",
        "data_csv": "figures/data/s/stale_by_set.csv",
        "output_pdf": "figures/out/stale_by_set.pdf",
        "output_png": "figures/out/stale_by_set.png",
        "protocol_section": "PROTOCOL 8.32/8.33",
        "condition_palette": "C0:#8c8c8c C0b:#4d4d4d C1a:#1f77b4 C2a:#d62728 C2b:#ff7f0e C3:#2ca02c",
        "models": "llama nemotron",
        "notes": "As-scored 0-filled version"
    },
    {
        "figure_id": "F13",
        "title": "Exposure-conditioned retention with CIs",
        "script": "figures/scripts/s_figures.py",
        "data_csv": "figures/data/s/retention.csv",
        "output_pdf": "figures/out/retention.pdf",
        "output_png": "figures/out/retention.png",
        "protocol_section": "PROTOCOL 8.34",
        "condition_palette": "C0:#8c8c8c C0b:#4d4d4d C1a:#1f77b4 C2a:#d62728 C2b:#ff7f0e C3:#2ca02c",
        "models": "llama nemotron",
        "notes": "Strict/lenient; pp/ITT"
    },
    {
        "figure_id": "F14",
        "title": "Delta-violation (signal vs all cells)",
        "script": "figures/scripts/s_figures.py",
        "data_csv": "figures/data/s/delta_violation.csv",
        "output_pdf": "figures/out/delta_violation.pdf",
        "output_png": "figures/out/delta_violation.png",
        "protocol_section": "PROTOCOL 8.34",
        "condition_palette": "C0:#8c8c8c C0b:#4d4d4d C1a:#1f77b4 C2a:#d62728 C2b:#ff7f0e C3:#2ca02c",
        "models": "llama nemotron",
        "notes": "Shift minus baseline"
    },
    {
        "figure_id": "F15",
        "title": "Movement not explained by hard constraints",
        "script": "figures/scripts/s_figures.py",
        "data_csv": "figures/data/s/false_change.csv",
        "output_pdf": "figures/out/false_change.pdf",
        "output_png": "figures/out/false_change.png",
        "protocol_section": "PROTOCOL 8.34",
        "condition_palette": "C0:#8c8c8c C0b:#4d4d4d C1a:#1f77b4 C2a:#d62728 C2b:#ff7f0e C3:#2ca02c",
        "models": "llama nemotron",
        "notes": "P(Shift>0 | |D|=0)"
    },
    {
        "figure_id": "F16",
        "title": "Tool-output overlap (crop_score echo)",
        "script": "figures/scripts/s_figures.py",
        "data_csv": "figures/data/s/overlap.csv",
        "output_pdf": "figures/out/overlap.pdf",
        "output_png": "figures/out/overlap.png",
        "protocol_section": "PROTOCOL 8.34",
        "condition_palette": "C0:#8c8c8c C0b:#4d4d4d C1a:#1f77b4 C2a:#d62728 C2b:#ff7f0e C3:#2ca02c",
        "models": "llama nemotron",
        "notes": "C2a vs stored bundle crop_score"
    },
    {
        "figure_id": "F17",
        "title": "Oracle signal per perturbation set",
        "script": "figures/scripts/s_figures.py",
        "data_csv": "figures/data/s/oracle_signal.csv",
        "output_pdf": "figures/out/oracle_signal.pdf",
        "output_png": "figures/out/oracle_signal.png",
        "protocol_section": "PROTOCOL 8.33",
        "condition_palette": "C0:#8c8c8c C0b:#4d4d4d C1a:#1f77b4 C2a:#d62728 C2b:#ff7f0e C3:#2ca02c",
        "models": "llama nemotron",
        "notes": "Strict vs lenient |D|>0"
    },
    {
        "figure_id": "F18",
        "title": "Contrast forest for S-series",
        "script": "figures/scripts/s_figures.py",
        "data_csv": "figures/data/s/contrasts_forest.csv",
        "output_pdf": "figures/out/contrasts_forest.pdf",
        "output_png": "figures/out/contrasts_forest.png",
        "protocol_section": "PROTOCOL 8.32/8.33",
        "condition_palette": "C0:#8c8c8c C0b:#4d4d4d C1a:#1f77b4 C2a:#d62728 C2b:#ff7f0e C3:#2ca02c",
        "models": "llama nemotron",
        "notes": "pp and ITT; Holm"
    },
    {
        "figure_id": "F19",
        "title": "Deterministic ablation & diversity (E01-E06)",
        "script": "figures/scripts/generate_figures.py",
        "data_csv": "",
        "output_pdf": "figures/out/Fig_E01_tool_ablation.pdf",
        "output_png": "figures/out/Fig_E01_tool_ablation.png",
        "protocol_section": "PROTOCOL 8.5-8.9",
        "condition_palette": "C3:#000000",
        "models": "C3 deterministic only",
        "notes": "Tool ablation; weight sensitivity; season validity; crop frequency"
    },
    {
        "figure_id": "F20",
        "title": "Per-season Precision@5",
        "script": "figures/scripts/n500_figures.py",
        "data_csv": "figures/data/n500/Fig_N05_season_contrasts.csv",
        "output_pdf": "figures/out/Fig_N05_season_contrasts.pdf",
        "output_png": "figures/out/Fig_N05_season_contrasts.png",
        "protocol_section": "PROTOCOL 8.26",
        "condition_palette": "C0:#0072B2 C0b:#56B4E9 C1a:#009E73 C2a:#D55E00 C2b:#E69F00 C3:#000000",
        "models": "nemotron",
        "notes": "Per-season contrasts Kharif/Rabi/Zaid"
    }
]

# Write CSV with proper quoting
out_path = ROOT / "docs" / "FIGURE_INDEX.csv"
fieldnames = ["figure_id", "title", "script", "data_csv", "output_pdf", "output_png",
              "protocol_section", "condition_palette", "models", "notes"]

with out_path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)

print(f"Wrote {len(rows)} rows to {out_path}")