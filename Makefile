# Makefile for AgroLLaMA MCP Evaluation Pipeline
# All targets work offline using stored outputs; no API calls unless explicitly requested.

.PHONY: all test eval figures scenarios deterministic clean help

# Default target
all: test eval figures

# Run unit tests (offline, no API calls)
test:
	python -m pytest tests/ -v --tb=short

# Full evaluation pipeline (offline, uses stored LLM outputs)
eval: deterministic real-data s-series db-v2 correction

# Generate all figures from result files (offline)
figures: figures-n500 figures-real figures-s figures-cross-model

# ---- Data & Scenario Generation ----

scenarios:
	python -m eval.scenarios.generate

stress-set:
	python -m eval.scripts.build_stress_set

llm-subset:
	python -m eval.scripts.finalize_stress_and_subset

# ---- Deterministic Pipeline (C3 + Ablations) ----

deterministic:
	python -m eval.scripts.run_deterministic_v2

deterministic-fast:
	python -m eval.scripts.run_deterministic_fast

analyze-deterministic:
	python -m eval.scripts.analyze_deterministic_v2

# ---- LLM Evaluation (requires API keys, uses cached results by default) ----

# Nemotron-3-Ultra (n=500)
eval-nemotron-b1:
	python -m eval.scripts.run_model --model nvidia/nemotron-3-ultra-550b-a55b --scenarios 150 --workers 4 --conditions C1a,C2a,C2b

eval-nemotron-b2:
	python -m eval.scripts.run_model --model nvidia/nemotron-3-ultra-550b-a55b --scenario-start 150 --scenarios 350 --workers 4 --conditions C1a,C2a,C2b --run-suffix _b2

eval-nemotron-c0:
	python -m eval.scripts.run_model --model nvidia/nemotron-3-ultra-550b-a55b --scenarios 500 --workers 4 --conditions C0,C0b

# Llama-3.2-11B (n=150)
eval-llama:
	python -m eval.scripts.run_model --model meta/llama-3.2-11b-vision-instruct --scenarios 150 --workers 4 --conditions C0,C0b,C1a,C1b,C2a,C2b

# MCP transport equivalence (optional)
eval-mcp-c2a:
	python -m eval.scripts.run_model --model nvidia/nemotron-3-ultra-550b-a55b --scenarios 50 --conditions C2a --tool-transport mcp --run-suffix _mcp_c2a50

# ---- Analysis & Metrics ----

# Stage A interim metrics (no API calls)
stage-a:
	python -m eval.scripts.stage_a_interim_metrics

# Nemotron primary metrics (n=150)
nemotron-primary:
	python -m eval.scripts.nemotron_primary_metrics

# n=500 primary metrics (merged B1+B2)
n500-primary:
	python -m eval.scripts.n500_primary_metrics

# Heterogeneity & season stratification
n500-heterogeneity:
	python -m eval.scripts.n500_heterogeneity

n500-season:
	python -m eval.scripts.n500_heterogeneity_season

# District-clustered inference
n500-clustered:
	python -m eval.scripts.n500_clustered_inference

# Divergent crop impact
n500-divergent:
	python -m eval.scripts.n500_divergent_crop_impact

# HTTP / tool-round reconciliation
recon-http:
	python -m eval.scripts.recon_http_rounds

# GT provenance audit
gt-provenance:
	python -m eval.scripts.gt_provenance_audit

# Gaps analysis
gaps:
	python -m eval.scripts.gaps_analysis

# Offline contrasts
offline-contrasts:
	python -m eval.scripts.offline_contrasts

# ---- Real-World Independent Evaluation (offline) ----

real-data:
	python -m eval.scripts.real_eval

real-data-figures:
	python -m eval.scripts.real_eval_figures

# ---- DB v2 Study (offline) ----

db-v2:
	python -m eval.scripts.build_db_v2
	python -m eval.scripts.dbv2_deterministic
	python -m eval.scripts.dbv2_metrics
	python -m eval.scripts.dbv2_combined_table
	python -m eval.scripts.dbv2_cost_estimate

# ---- S-Series (Simulated Scenarios) ----

s-evidence:
	python -m eval.scripts.build_s_evidence

s-series:
	python -m eval.scripts.run_s_series --models nemotron llama

s-scoring:
	python -m eval.scripts.score_s

s-figures:
	python -m eval.scripts.s_figures

s-followup:
	python -m eval.scripts.s_followup_b6
	python -m eval.scripts.s_followup_real_impact
	python -m eval.scripts.s_followup_cases

# ---- Instrument Correction (C3t) ----

correction:
	python -m eval.scripts.c3t_recompute
	python -m eval.scripts.c3t_correction

# ---- Figure Generation (offline, from result files) ----

figures-n500:
	python -m figures.scripts.n500_figures

figures-real:
	python -m figures.scripts.real_eval_figures

figures-s:
	python -m figures.scripts.s_figures

figures-cross-model:
	python -m figures.scripts.analyze_cross_model

figures-deterministic:
	python -m figures.scripts.generate_figures

# ---- Verification ----

verify:
	python -m eval.scripts.verify_reuse
	python -m eval.scripts.verify_stage_a
	python -m eval.scripts.verify_b1_nemotron

# ---- Cleanup ----

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov 2>/dev/null || true

# Full clean (removes generated outputs but NOT registered results)
clean-all: clean
	rm -rf eval/runs/eval_* eval/runs/s_* 2>/dev/null || true
	rm -rf eval/cache/llm/ eval/cache/weather/ 2>/dev/null || true
	rm -rf figures/out/*.pdf figures/out/*.png 2>/dev/null || true

# ---- Help ----

help:
	@echo "AgroLLaMA MCP Evaluation Pipeline"
	@echo ""
	@echo "Main targets:"
	@echo "  all              - Run tests, eval, figures (offline)"
	@echo "  test             - Run unit tests"
	@echo "  eval             - Full evaluation pipeline"
	@echo "  figures          - Generate all figures"
	@echo ""
	@echo "Sub-pipelines:"
	@echo "  deterministic    - C3 + ablations on 10k scenarios"
	@echo "  real-data        - Real-world independent evaluation"
	@echo "  db-v2            - Database version study"
	@echo "  s-series         - Simulated scenario study"
	@echo "  correction       - Instrument correction (C3t)"
	@echo ""
	@echo "Individual targets (see Makefile for full list):"
	@echo "  eval-nemotron-b1, eval-nemotron-b2, eval-llama"
	@echo "  n500-primary, n500-heterogeneity, n500-clustered"
	@echo "  real-data-figures, s-figures, figures-n500, etc."
	@echo ""
	@echo "Cleanup:"
	@echo "  clean            - Remove __pycache__, .pyc, .pytest_cache"
	@echo "  clean-all        - Also remove run dirs, caches, figure outputs"