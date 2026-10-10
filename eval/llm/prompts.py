"""Prompt builders, output parsing, and crop alias normalisation (STEP 4)."""

from __future__ import annotations

import json
import re
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

_CANON_LOWER = {c.lower(): c for c in CANONICAL_CROPS}


def normalize_crop(name: str) -> str | None:
    """Return the canonical registry name, or None if out of registry."""
    if not name:
        return None
    key = re.sub(r"[^a-z0-9 ]", " ", name.strip().lower())
    key = re.sub(r"\s+", " ", key).strip()
    if key in ALIASES:
        return ALIASES[key]
    if key in _CANON_LOWER:
        return _CANON_LOWER[key]
    return None


OUTPUT_CONTRACT = (
    'Return ONLY a single JSON object, no markdown, no prose outside it:\n'
    '{"top5": ["<crop1>", "<crop2>", "<crop3>", "<crop4>", "<crop5>"], '
    '"explanation": "<60 words max>"}\n'
    "Use the exact crop names from the list above. Do not invent crop names. "
    "Rank them best-first."
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
        f"Date: {scenario['as_of_date']} (season is determined by the month).\n"
        "Carefully consider all of the following before choosing crops: soil type and suitability "
        "for the district, the current cropping season (Kharif/Rabi/Zaid) and sowing window, seasonal "
        "rainfall and temperature suitability, and the risk of drought, heatwave, and flood/waterlogging.\n"
        "Weigh these factors together and produce the most agronomically sound ranking.\n"
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
        f"{CROP_LIST_TEXT}\n{OUTPUT_CONTRACT}"
    )


def prompt_c2(scenario: dict[str, Any]) -> str:
    return (
        "You are an agronomy advisor for Madhya Pradesh, India, with access to agricultural tools.\n"
        f"District: {scenario['district']}. Coordinates: {scenario['lat']:.4f}, {scenario['lon']:.4f}. "
        f"Date: {scenario['as_of_date']}.\n"
        "Use the available tools to gather evidence before deciding:\n"
        "call weather_tool, climate_tool, season_tool, risk_tool, and get_soil_by_coordinates with the "
        "given latitude and longitude, then call crop_score. Base your decision on the tool outputs and "
        "do not invent soil, weather, or risk values.\n"
        f"{CROP_LIST_TEXT}\n{OUTPUT_CONTRACT}"
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
