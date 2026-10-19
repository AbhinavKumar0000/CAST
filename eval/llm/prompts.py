"""Prompt builders, output parsing, and crop alias normalisation (STEP 4)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Canonical crop names = the repo registry (crop_log.csv).
CANONICAL_CROPS = [
    "Soybean", "Wheat", "Rice", "Maize", "Cotton", "Jowar", "Gram", "Sugarcane",
    "Mustard", "Groundnut", "Moong", "Urad", "Lentil", "Barley", "Bajra",
    "Sesame (Til)", "Sunflower", "Arhar (Tur)", "Pea", "Kodo-Kutki", "Watermelon",
]

ALIASES = {
    "paddy": "Rice", "dhan": "Rice", "rice": "Rice",
    "wheat": "Wheat", "gehu": "Wheat",
    "maize": "Maize", "corn": "Maize", "makka": "Maize",
    "cotton": "Cotton", "kapas": "Cotton",
    "jowar": "Jowar", "sorghum": "Jowar", "jowar (sorghum)": "Jowar",
    "gram": "Gram", "chana": "Gram", "channa": "Gram", "bengal gram": "Gram",
    "chickpea": "Gram", "chick pea": "Gram",
    "sugarcane": "Sugarcane", "ganna": "Sugarcane", "sugar cane": "Sugarcane",
    "mustard": "Mustard", "rai": "Mustard", "rapeseed": "Mustard",
    "groundnut": "Groundnut", "peanut": "Groundnut", "moongphali": "Groundnut",
    "moong": "Moong", "mung": "Moong", "green gram": "Moong", "moong bean": "Moong",
    "urad": "Urad", "urd": "Urad", "black gram": "Urad", "urad dal": "Urad",
    "lentil": "Lentil", "masoor": "Lentil", "masur": "Lentil",
    "barley": "Barley", "jau": "Barley",
    "bajra": "Bajra", "pearl millet": "Bajra", "bajara": "Bajra",
    "sesame": "Sesame (Til)", "sesame (til)": "Sesame (Til)", "til": "Sesame (Til)",
    "sunflower": "Sunflower", "surajmukhi": "Sunflower",
    "arhar": "Arhar (Tur)", "arhar (tur)": "Arhar (Tur)", "tur": "Arhar (Tur)",
    "toor": "Arhar (Tur)", "pigeon pea": "Arhar (Tur)", "pigeonpea": "Arhar (Tur)",
    "pea": "Pea", "matar": "Pea",
    "kodo-kutki": "Kodo-Kutki", "kodo kutki": "Kodo-Kutki", "kodo": "Kodo-Kutki",
    "kutki": "Kodo-Kutki",
    "watermelon": "Watermelon", "tarbooz": "Watermelon",
}

def _norm_key(name: str) -> str:
    key = re.sub(r"[^a-z0-9 ]", " ", name.strip().lower())
    return re.sub(r"\s+", " ", key).strip()


# Normalise both lookup sides, so parenthesised canonical names
# ("Sesame (Til)", "Arhar (Tur)") match their punctuation-stripped input form.
_CANON_LOWER = {_norm_key(c): c for c in CANONICAL_CROPS}
_ALIASES_NORM = {_norm_key(k): v for k, v in ALIASES.items()}


def normalize_crop(name: str) -> str | None:
    """Return the canonical registry name, or None if out of registry."""
    if not name:
        return None
    key = _norm_key(name)
    if key in _ALIASES_NORM:
        return _ALIASES_NORM[key]
    if key in _CANON_LOWER:
        return _CANON_LOWER[key]
    return None


OUTPUT_CONTRACT = (
    'CRITICAL: Your entire response must be a SINGLE JSON object and NOTHING ELSE.\n'
    'Do NOT include any explanatory text, markdown, code fences, or prose.\n'
    'Do NOT write "Here is the JSON:" or any introduction.\n'
    'Do NOT write "The user wants..." or "I need to consider..." or any reasoning.\n'
    'Output EXACTLY this format:\n'
    '{"top5": ["Soybean", "Wheat", "Rice", "Maize", "Cotton"], "explanation": "Brief reason <=60 words"}\n'
    "Use EXACT crop names from the candidate list. No invented names. Rank best-first."
)

# Harness-fix (PROTOCOL ss8.10, 2026-10-13): appended ONLY to tool-condition prompts
# (C1a/C2a/C2b/C1b). C0/C0b prompts are intentionally untouched so cached records stay
# reusable. Reinforces the system message: JSON object only, no prose around it.
FINAL_JSON_ONLY = (
    '\nReply with the final JSON object only; no analysis or explanation text '
    'outside the JSON.'
)

CROP_LIST_TEXT = "Candidate crops (use these exact names): " + ", ".join(CANONICAL_CROPS) + "."


def prompt_c0(scenario: dict[str, Any]) -> str:
    return (
        "You are an agronomy advisor for Madhya Pradesh, India.\n"
        f"District: {scenario['district']}. Coordinates: {scenario['lat']:.4f}, {scenario['lon']:.4f}. "
        f"Date: {scenario['as_of_date']}.\n"
        "Recommend the best crops to grow for this district around this date.\n"
        f"{CROP_LIST_TEXT}\n{OUTPUT_CONTRACT}"
    )


def prompt_c0b(scenario: dict[str, Any]) -> str:
    return (
        "You are an expert agronomist for Madhya Pradesh, India.\n"
        f"District: {scenario['district']}. Coordinates: {scenario['lat']:.4f}, {scenario['lon']:.4f}. "
        f"Date: {scenario['as_of_date']}.\n"
        "Consider: soil type, cropping season (Kharif/Rabi/Zaid), rainfall, temperature, drought/heatwave/flood risk.\n"
        f"{CROP_LIST_TEXT}\n{OUTPUT_CONTRACT}"
    )


def _compact(obj: Any, max_len: int = 4000) -> str:
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return s if len(s) <= max_len else s[:max_len] + "...(truncated)"


def prompt_c1(scenario: dict[str, Any], evidence: dict[str, Any]) -> str:
    return (
        "You are an agronomy advisor for Madhya Pradesh, India.\n"
        f"District: {scenario['district']}. Coordinates: {scenario['lat']:.4f}, {scenario['lon']:.4f}. "
        f"Date: {scenario['as_of_date']}.\n"
        "The following deterministic tool outputs are provided as evidence. Base your recommendation "
        "strictly on them; do not invent numbers.\n"
        f"WEATHER: {_compact(evidence.get('weather'))}\n"
        f"CLIMATE_NORMALS: {_compact(evidence.get('climate'))}\n"
        f"SEASON: {_compact(evidence.get('season'))}\n"
        f"SOIL: {_compact(evidence.get('soil'))}\n"
        f"RISK: {_compact(evidence.get('risk'))}\n"
        f"CROP_SCORE: {_compact(evidence.get('crop_score'))}\n"
        f"{CROP_LIST_TEXT}\n{OUTPUT_CONTRACT}{FINAL_JSON_ONLY}"
    )


def _load_candidate_requirements() -> list[dict[str, str]]:
    import csv

    path = Path(__file__).resolve().parent.parent.parent / "crop_log.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def candidate_requirements_text() -> str:
    """Raw candidate crop requirements (registry), NO scores, NO ranking, NO match flags."""
    rows = _load_candidate_requirements()
    lines = []
    for i, r in enumerate(rows, 1):
        lines.append(
            _compact({
                "crop": r.get("Crop", ""),
                "season_supported": r.get("season_supported", ""),
                "rainfall_range_mm": r.get("Rainfall", ""),
                "temperature_range_c": r.get("Tempreture", ""),
                "soil_type": r.get("Soil Type", ""),
                "sowing_window_weeks": f"{r.get('sowing_start_week', '')}..{r.get('sowing_end_week', '')}",
                "days_to_harvest": r.get("days_to_harvest", ""),
                "peak_water_week": r.get("peak_water_week", ""),
                "risk_sensitivity": r.get("risk_sensitivity", ""),
            })
        )
    return "\n".join(f"{i}. {line}" for i, line in enumerate(lines, 1))


# Phase 8 STEP B: raw candidate requirements (no scores/ranking/match flags).
_CANDIDATE_REQUIREMENTS_TEXT = candidate_requirements_text()


def prompt_c1a(scenario: dict[str, Any], evidence: dict[str, Any]) -> str:
    """Fair stuffing (C1a): the same raw evidence the tools would return, WITHOUT the
    CROP_SCORE ranking, suitability scores, or per-crop match flags."""
    return (
        "You are an agronomy advisor for Madhya Pradesh, India.\n"
        f"District: {scenario['district']}. Coordinates: {scenario['lat']:.4f}, {scenario['lon']:.4f}. "
        f"Date: {scenario['as_of_date']}.\n"
        "The following raw tool outputs are provided as evidence. Base your recommendation "
        "strictly on them; do not invent numbers.\n"
        f"WEATHER: {_compact(evidence.get('weather'))}\n"
        f"CLIMATE_NORMALS: {_compact(evidence.get('climate'))}\n"
        f"SEASON: {_compact(evidence.get('season'))}\n"
        f"SOIL: {_compact(evidence.get('soil'))}\n"
        f"RISK: {_compact(evidence.get('risk'))}\n"
        f"CANDIDATE_CROP_REQUIREMENTS:\n{_CANDIDATE_REQUIREMENTS_TEXT}\n"
        f"{CROP_LIST_TEXT}\n{OUTPUT_CONTRACT}{FINAL_JSON_ONLY}"
    )


def prompt_c1b(scenario: dict[str, Any], evidence: dict[str, Any]) -> str:
    """Oracle (C1b): the current C1 prompt, i.e. the C3 ranking injected. Relabelled
    per Phase 8 STEP B; upper bound, leaks the answer - never a fair baseline."""
    return prompt_c1(scenario, evidence)


def prompt_c2(scenario: dict[str, Any], tools: list[str] | None = None) -> str:
    tool_names = tools or [
        "weather_tool", "climate_tool", "season_tool", "risk_tool",
        "get_soil_by_coordinates", "crop_score",
    ]
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(tool_names))
    must = "You MUST call ALL of the following tools with the given latitude and longitude "
    if len(tool_names) == 6:
        must += "before making any recommendation."
    else:
        must += "before making any recommendation. Do NOT call any other tool."
    return (
        "You are an agronomy advisor for Madhya Pradesh, India, with access to agricultural tools.\n"
        f"District: {scenario['district']}. Coordinates: {scenario['lat']:.4f}, {scenario['lon']:.4f}. "
        f"Date: {scenario['as_of_date']}.\n"
        f"{must}\n{numbered}\n"
        "Call them in any order, but you must call ALL of the listed tools. After receiving "
        "all tool outputs, base your final recommendation strictly on the tool outputs. Do not "
        "invent soil, weather, climate, season, risk, or crop suitability values.\n"
        f"{CROP_LIST_TEXT}\n{OUTPUT_CONTRACT}{FINAL_JSON_ONLY}"
    )


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_output(text: str) -> dict[str, Any]:
    """Extract {top5, explanation} from a model reply. Robust to stray text/fences."""
    result: dict[str, Any] = {"top5_raw": [], "top5": [], "explanation": "", "valid_json": False, "out_of_registry": []}
    if not text:
        return result
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    candidates = [cleaned]
    m = _JSON_RE.search(cleaned)
    if m:
        candidates.insert(0, m.group(0))
    obj = None
    for cand in candidates:
        try:
            obj = json.loads(cand)
            break
        except json.JSONDecodeError:
            continue
    if obj is None:
        return result
    result["valid_json"] = True
    raw = obj.get("top5") or obj.get("Top5") or obj.get("crops") or []
    if isinstance(raw, str):
        raw = [raw]
    result["top5_raw"] = [str(x) for x in raw][:5]
    result["explanation"] = str(obj.get("explanation") or obj.get("reason") or "")[:600]
    canonical: list[str] = []
    oor: list[str] = []
    for name in result["top5_raw"]:
        c = normalize_crop(name)
        if c is None:
            oor.append(name)
        else:
            canonical.append(c)
    result["top5"] = canonical[:5]
    result["out_of_registry"] = oor
    return result
