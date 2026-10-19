"""Evaluation-specific season tool using pre-cached weather data."""

from __future__ import annotations

from eval.common import load_config, config_dirs
from mcp_server.season_tool import MONTH_TO_SEASON, IST
from datetime import datetime

def run(latitude: float, longitude: float) -> dict:
    """Determine the current cropping season for a given latitude and longitude.
    
    This evaluation version uses local time calculation instead of API calls.
    """
    cfg = load_config()
    dirs = config_dirs(cfg)
    
    # Determine season based on current month in IST
    now = datetime.now(IST)
    current_month = now.month
    
    # Find which season the current month falls into
    current_season = MONTH_TO_SEASON.get(current_month, "Unknown")
    
    return {
        "tool": "season_detection",
        "current_season": current_season,
        "current_month": current_month,
        "latitude": latitude,
        "longitude": longitude,
    }


if __name__ == "__main__":
    # Quick test
    result = run(23.2599, 77.4126)
    print(result)