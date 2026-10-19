# SUPERSEDED / ARCHIVED figures

## Canonical set (current headline)

`eval/figures/n500/Fig_N01..N07` (produced by `eval/scripts/n500_figures.py`) are the canonical
headline figures for the final pre-registered evaluation (n=500, 51 districts). See
`eval/report/N500_FIGURES.md`.

## Archived (superseded)

Moved to `eval/figures/archive_v1/` on the eval close-out. These are **not** to be used for the
paper.

- `archive_v1/E_series/Fig_E01..E06` — legacy deterministic figures from
  `eval/scripts/generate_figures.py`; E01–E04/E06 carry hardcoded legacy numbers (`n=8,628`) and
  do not read the canonical grid. Only E05 was data-driven. Superseded.
- `eval/figures/archive_v1/cross_model_M/Fig_M01..M10` — cross-model figures from
  `eval/scripts/analyze_cross_model.py`; use the older C1/C2 condition naming and the partial
  cross-model run (llama 150, glm 32). Superseded as headline by the n=500 set.
- `eval/figures/archive_v1/paper/Fig01..Fig14` + `T1_metrics.*` / `T2_coverage.*` — paper_v2 set
  from `figures_paper.py` reading `master_long.csv`; same superseded naming/scope.

Provenance: files were MOVED, not deleted. Re-running the originating scripts regenerates them in
the old locations (`eval/figures/`, `eval/figures/paper/`).
