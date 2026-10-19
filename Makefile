# Evaluation Makefile
# Usage: make <target>
# Main targets: status, watch, audit, scenarios, deterministic, pilot, llm-run, analyze, figures, report

.PHONY: help status watch audit scenarios deterministic pilot llm-run analyze figures report clean

# Configuration
PY := python
EVAL_DIR := eval
PROGRESS := $(EVAL_DIR)/runs/progress.json

help:
	@echo "Evaluation targets:"
	@echo "  make status       - Show current job progress"
	@echo "  make watch        - Watch progress (refreshes every 5s)"
	@echo "  make audit        - Run repo audit (STEP 0)"
	@echo "  make scenarios    - Generate 10k scenarios + stress + LLM subset (STEP 2)"
	@echo "  make weather      - Bulk fetch Open-Meteo archive for all districts"
	@echo "  make deterministic - Run C3 + ablations on all 10k (STEP 4, free)"
	@echo "  make analyze      - Compute metrics, statistics, bootstrap CIs"
	@echo "  make figures      - Generate all figures (Fig_E01-E17, Fig_M01-M08)"
	@echo "  make report       - Build RESULTS_REPORT.md + .docx"
	@echo "  make pilot        - Run 30-scenario pilot for LLM conditions"
	@echo "  make llm-run      - Run full LLM experiments (after pilot approval)"
	@echo "  make clean        - Remove caches and run outputs (keep results/figures/report)"

status:
	@$(PY) -m eval.status

watch:
	@$(PY) -m eval.status --watch

audit:
	@echo "STEP 0: Repo audit already in eval/REPO_AUDIT.md"
	@echo "Config SHA256: $$($(PY) -c 'from eval.common import config_sha256; print(config_sha256())')"

scenarios:
	@echo "STEP 2: Generating scenarios..."
	$(PY) -m eval.scenarios

weather:
	@echo "Fetching bulk weather archive..."
	$(PY) -c "from eval.weather_cache import load_all; load_all(force=False)"

deterministic:
	@echo "STEP 4: Running deterministic C3 + ablations (canonical writer)..."
	$(PY) $(EVAL_DIR)/scripts/analyze_deterministic_v2.py

analyze:
	@echo "STEP 6-7: Computing metrics and statistics..."
	# TODO: implement full analysis pipeline

figures:
	@echo "STEP 8: Generating figures..."
	$(PY) $(EVAL_DIR)/scripts/generate_figures.py

report:
	@echo "STEP 9: Building report..."
	# TODO: implement report generation

pilot:
	@echo "STEP 5: Running 30-scenario pilot..."
	# TODO: implement pilot runner

llm-run:
	@echo "STEP 5: Running full LLM experiments..."
	# TODO: implement full LLM runner

clean:
	@echo "Cleaning caches and run outputs..."
	rm -rf $(EVAL_DIR)/cache $(EVAL_DIR)/runs $(EVAL_DIR)/.tmp
	@echo "Kept: $(EVAL_DIR)/results $(EVAL_DIR)/figures $(EVAL_DIR)/report $(EVAL_DIR)/data"