"""Evaluation-specific tool wrappers that use pre-cached weather data."""

from eval.tools.eval_climate_tool import run as climate_tool_run
from eval.tools.eval_risk_tool import run as risk_tool_run
from eval.tools.eval_season_tool import run as season_tool_run

# Export the run functions
__all__ = ["climate_tool_run", "risk_tool_run", "season_tool_run"]

# Convenience aliases
run_climate = climate_tool_run
run_risk = risk_tool_run
run_season = season_tool_run