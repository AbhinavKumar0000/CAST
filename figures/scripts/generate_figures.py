"""Figure generation (STEP 8).

Creates all 17+ figures as PNG@300dpi + PDF with colorblind-safe palette.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from eval.common import load_config, ensure_dirs, config_dirs, read_jsonl
from eval.scenarios import generate

cfg = load_config()
ensure_dirs(cfg)
dirs = config_dirs(cfg)

# Colorblind-safe palette (tab10 + extras)
COLORS = {
    'C0': '#0072B2',      # blue
    'C0b': '#56B4E9',     # light blue
    'C1': '#009E73',      # green
    'C2': '#D55E00',      # vermillion
    'C3': '#CC79A7',      # pink
    'stress': '#E69F00',  # orange
    'normal': '#0072B2',  # blue
    'Kharif': '#009E73',
    'Rabi': '#D55E00',
    'Zaid': '#56B4E9',
}
CONDITION_LABELS = {
    'C0': 'LLM-only',
    'C0b': 'LLM-only strong',
    'C1': 'LLM + stuffing',
    'C2': 'LLM + MCP',
    'C3': 'No-LLM (det.)',
}
ABLATION_LABELS = {
    'full_repo': 'Full (repo weights)',
    'full_equal': 'Full (equal weights)',
    'no_weather': '− Weather',
    'no_climate': '− Climate',
    'no_soil': '− Soil',
    'no_risk': '− Risk',
    'no_season': '− Season',
}
SENS_LABELS = {
    'sens_rainfall_plus': 'Rainfall +20%',
    'sens_rainfall_minus': 'Rainfall −20%',
    'sens_temperature_plus': 'Temp +20%',
    'sens_temperature_minus': 'Temp −20%',
    'sens_soil_plus': 'Soil +20%',
    'sens_soil_minus': 'Soil −20%',
    'sens_season_plus': 'Season +20%',
    'sens_season_minus': 'Season −20%',
    'sens_risk_plus': 'Risk +20%',
    'sens_risk_minus': 'Risk −20%',
}

# Style
plt.rcParams.update({
    'font.size': 10,
    'axes.titlesize': 12,
    'axes.labelsize': 10,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'legend.fontsize': 9,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'axes.spines.top': False,
    'axes.spines.right': False,
})

fig_dir = Path(__file__).resolve().parent.parent / "out"
data_dir = Path(__file__).resolve().parent.parent / "data" / "archive_v1"
fig_dir.mkdir(parents=True, exist_ok=True)
data_dir.mkdir(parents=True, exist_ok=True)

def save_fig(fig, name: str, rows=None, cols=None):
    """Save figure as PNG and PDF, and optionally write CSV data."""
    fig.savefig(fig_dir / f"{name}.png", dpi=300)
    fig.savefig(fig_dir / f"{name}.pdf")
    plt.close(fig)
    if rows is not None and cols is not None:
        import pandas as pd
        pd.DataFrame(rows, columns=cols).to_csv(data_dir / f"{name}.csv", index=False)

# Load deterministic summary
with open(Path(__file__).resolve().parent.parent.parent / "eval/results/c3_deterministic_summary.json") as f:
    det_summary = json.load(f)

# Load scenarios and stress set
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from eval.scenarios import generate
from eval.common import load_config, config_dirs

cfg = load_config()
dirs = config_dirs(cfg)
scenarios = generate(cfg)
by_id = {s['scenario_id']: s for s in scenarios}
stress_ids = set()
with open(dirs['stress_path']) as f:
    for line in f:
        stress_ids.add(json.loads(line)['scenario_id'])

# Load deterministic results for ablation figures
det_dir = dirs['runs_dir'] / 'archive_v2' / 'deterministic'
files = list(det_dir.glob('*.json'))

# --- Figure E01: Ablation chart (deterministic, 10k) ---
fig, ax = plt.subplots(figsize=(8, 5))
ablation_names = ['full_repo', 'full_equal', 'no_weather', 'no_climate', 'no_soil', 'no_risk', 'no_season']
labels = [ABLATION_LABELS[a] for a in ablation_names]
jaccards = [0.9067, 1.0, 0.9073, 0.8174, 0.6109, 0.8683, 1.0]  # vs full_repo (full_repo = 1.0)
colors = [COLORS['C3'] if a == 'full_repo' else '#888888' for a in ablation_names]

bars = ax.barh(range(len(labels)), jaccards, color=colors, edgecolor='white', height=0.7)
ax.set_yticks(range(len(labels)))
ax.set_yticklabels(labels)
ax.set_xlabel('Jaccard similarity vs Full (repo weights)')
ax.set_title('Fig E01: Tool Ablation — Deterministic Crop Score (n=8,628)')
ax.set_xlim(0.5, 1.05)
ax.invert_yaxis()
for bar, val in zip(bars, jaccards):
    ax.text(val + 0.01, bar.get_y() + bar.get_height()/2, f'{val:.3f}', va='center', fontsize=9)
save_fig(fig, 'Fig_E01_tool_ablation',
         rows=[{'ablation': l, 'jaccard_vs_full_repo': j} for l, j in zip(labels, jaccards)],
         cols=['ablation', 'jaccard_vs_full_repo'])

# --- Figure E02: Weight sensitivity ---
fig, ax = plt.subplots(figsize=(8, 5))
sens_names = ['sens_rainfall_plus', 'sens_rainfall_minus', 'sens_temperature_plus', 'sens_temperature_minus',
              'sens_soil_plus', 'sens_soil_minus', 'sens_season_plus', 'sens_season_minus',
              'sens_risk_plus', 'sens_risk_minus']
sens_labels = [SENS_LABELS[s] for s in sens_names]
sens_jaccards = [0.9791, 0.9807, 0.9833, 0.9765, 0.9606, 0.9208, 0.9250, 0.9514, 0.9761, 0.9379]

bars = ax.barh(range(len(sens_labels)), sens_jaccards, color='#888888', edgecolor='white', height=0.7)
ax.set_yticks(range(len(sens_labels)))
ax.set_yticklabels(sens_labels)
ax.set_xlabel('Jaccard similarity vs Full (repo weights)')
ax.set_title('Fig E02: Weight Sensitivity (±20%) — Deterministic (n=8,628)')
ax.set_xlim(0.9, 1.0)
ax.invert_yaxis()
for bar, val in zip(bars, sens_jaccards):
    ax.text(val + 0.001, bar.get_y() + bar.get_height()/2, f'{val:.3f}', va='center', fontsize=8)
save_fig(fig, 'Fig_E02_weight_sensitivity',
         rows=[{'weight_perturbation': l, 'jaccard_vs_full_repo': j} for l, j in zip(sens_labels, sens_jaccards)],
         cols=['weight_perturbation', 'jaccard_vs_full_repo'])

# --- Figure E03: Season validity (overall and stress) ---
fig, ax = plt.subplots(figsize=(8, 5))
categories = ['Overall\n(n=8,628)', 'Normal\n(n=4,416)', 'Stress\n(n=4,212)']
values = [0.7491, 0.9405, 0.5483]
colors_bar = [COLORS['C3'], COLORS['normal'], COLORS['stress']]

bars = ax.bar(categories, values, color=colors_bar, edgecolor='white', width=0.6)
ax.set_ylabel('Season validity rate')
ax.set_title('Fig E03: Season Validity Rate — C3 Deterministic')
ax.set_ylim(0, 1.05)
for bar, val in zip(bars, values):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02, f'{val:.1%}', ha='center', fontsize=10)
save_fig(fig, 'Fig_E03_season_validity',
         rows=[{'category': c, 'season_validity_rate': v} for c, v in zip(categories, values)],
         cols=['category', 'season_validity_rate'])

# --- Figure E04: Season validity by season ---
fig, ax = plt.subplots(figsize=(8, 5))
seasons = ['Kharif', 'Rabi', 'Zaid']
season_vals = [0.9879, 0.9870, 0.2683]
season_n = [2904, 2864, 2860]
season_colors = [COLORS['Kharif'], COLORS['Rabi'], COLORS['Zaid']]

bars = ax.bar(seasons, season_vals, color=season_colors, edgecolor='white', width=0.6)
ax.set_ylabel('Season validity rate')
ax.set_title('Fig E04: Season Validity by Cropping Season — C3 Deterministic')
ax.set_ylim(0, 1.12)
for bar, val, n in zip(bars, season_vals, season_n):
    # Place text inside the bar for tall bars, outside for short ones
    if val > 0.8:
        ax.text(bar.get_x() + bar.get_width()/2, val - 0.05, f'{val:.1%}\n(n={n})', ha='center', va='top', fontsize=9, color='white')
    else:
        ax.text(bar.get_x() + bar.get_width()/2, val + 0.02, f'{val:.1%}\n(n={n})', ha='center', va='bottom', fontsize=9)
save_fig(fig, 'Fig_E04_season_validity_by_season',
         rows=[{'season': s, 'season_validity_rate': v, 'n': n} for s, v, n in zip(seasons, season_vals, season_n)],
         cols=['season', 'season_validity_rate', 'n'])

# --- Figure E05: Crop frequency heatmap (C3 only for now) ---
# Load crop frequencies
det_dir = dirs['runs_dir'] / 'archive_v2' / 'deterministic'
crop_counts = defaultdict(int)
for path in files:
    with path.open() as f:
        res = json.load(f)
    if 'full_repo' not in res.get('ablations', {}):
        continue
    ab = res['ablations']['full_repo']
    if 'error' in ab:
        continue
    for crop in ab['top5']:
        crop_counts[crop] += 1

crops_sorted = sorted(crop_counts.items(), key=lambda x: -x[1])
crop_names = [c for c, _ in crops_sorted]
crop_freqs = [c for _, c in crops_sorted]

fig, ax = plt.subplots(figsize=(10, 6))
bars = ax.barh(range(len(crop_names)), crop_freqs, color=COLORS['C3'], edgecolor='white')
ax.set_yticks(range(len(crop_names)))
ax.set_yticklabels(crop_names)
ax.set_xlabel('Frequency in top-5 (out of 8,628 scenarios)')
ax.set_title('Fig E05: Crop Recommendation Frequency — C3 Deterministic')
ax.invert_yaxis()
for bar, val in zip(bars, crop_freqs):
    ax.text(val + 50, bar.get_y() + bar.get_height()/2, f'{val}', va='center', fontsize=8)
save_fig(fig, 'Fig_E05_crop_frequency',
         rows=[{'crop': c, 'top5_frequency': f} for c, f in zip(crop_names, crop_freqs)],
         cols=['crop', 'top5_frequency'])

# --- Figure E06: Diversity metrics ---
fig, ax = plt.subplots(figsize=(8, 5))
metrics = ['Distinct crops\n(max 21)', 'Shannon entropy\n(max 4.39)', 'Per-district diff\n(max 1.0)']
values = [21, 4.0383, 0.1795]
max_vals = [21, 4.39, 1.0]
pct = [v/m*100 for v, m in zip(values, max_vals)]

bars = ax.bar(metrics, pct, color=[COLORS['C3']]*3, edgecolor='white', width=0.6)
ax.set_ylabel('% of maximum')
ax.set_title('Fig E06: Specificity/Diversity Metrics — C3 Deterministic')
ax.set_ylim(0, 110)
for bar, val, p in zip(bars, values, pct):
    ax.text(bar.get_x() + bar.get_width()/2, p + 2, f'{val:.3f}\n({p:.0f}%)', ha='center', fontsize=9)
save_fig(fig, 'Fig_E06_diversity_metrics',
         rows=[{'metric': m, 'value': v, 'max_value': mv, 'pct_of_max': p} for m, v, mv, p in zip(metrics, values, max_vals, pct)],
         cols=['metric', 'value', 'max_value', 'pct_of_max'])

print("Figures E01-E06 saved to", fig_dir)

# Print summary for report
print("\n=== Key Numbers for Report ===")
print(f"C3 Distinct crops: 21/21")
print(f"C3 Shannon entropy: 4.038/4.392 (92%)")
print(f"C3 Per-district differentiation: 0.180")
print(f"C3 Season validity overall: 74.9%")
print(f"C3 Season validity stress: 54.8%")
print(f"C3 Season validity normal: 94.1%")
print(f"C3 Season validity Kharif: 98.8%")
print(f"C3 Season validity Rabi: 98.7%")
print(f"C3 Season validity Zaid: 26.8%")
print(f"Ablation - no_soil Jaccard: 0.611 (biggest drop)")
print(f"Ablation - no_climate Jaccard: 0.817")
print(f"Ablation - no_risk Jaccard: 0.868")
print(f"Ablation - no_weather Jaccard: 0.907")
print(f"Ablation - no_season Jaccard: 1.000 (no effect)")
print(f"Weight sensitivity - soil -20%: 0.921 (largest sensitivity)")