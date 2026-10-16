"""
STEP 2: build the clean real-world reference dataset.

Reads the untouched raw files in eval/real_data/raw/ and writes:
  - eval/real_data/district_map.csv
  - eval/real_data/clean/area_by_district_season_year.csv

Design decisions (see QA.md and PROTOCOL.md for the rationale):
  * Primary source S1 (UPAG, DES/MoA&FW), seasons Kharif/Rabi/Summer,
    Summer mapped to Zaid.
  * Secondary source S2 (DES crop-wise APY) used ONLY to fill the vocab crops
    that S1 lacks (currently Pea). S2 seasons are mapped Rabi/Rabi and
    Summer/Whole Year -> Zaid, everything else dropped.
  * Years kept: 2015-16 .. 2024-25.
  * District labels are mapped onto the 51 geometry districts of
    data/processed/mp_districts.geojson. Post-2018 districts are folded back
    into their parent (Niwari->Tikamgarh, Maihar->Satna, Mauganj->Rewa,
    Pandhurna->Chhindwara).

No model/LLM call is made. Raw files are opened read-only.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "eval" / "real_data" / "raw"
CLEAN = ROOT / "eval" / "real_data" / "clean"
GEO = ROOT / "data" / "processed" / "mp_districts.geojson"
CROP_LOG = ROOT / "crop_log.csv"

CLEAN.mkdir(parents=True, exist_ok=True)

KEEP_YEARS = {
    "2015-2016", "2016-2017", "2017-2018", "2018-2019", "2019-2020",
    "2020-2021", "2021-2022", "2022-2023", "2023-2024", "2024-2025",
}

DISTRICT_ALIAS = {
    "Agar-Malwa": "Agar Malwa",
    "Khandwa (East Nimar)": "East Nimar",
    "Khargone (West Nimar)": "West Nimar",
    "Narmadapuram": "Hoshangabad",
    "Niwari": "Tikamgarh",
    "Maihar": "Satna",
    "Mauganj": "Rewa",
    "Pandhurna": "Chhindwara",
}

VOCAB_ALIAS = {
    "Soyabean": "Soybean",
    "Soybean": "Soybean",
    "Cotton(Lint)": "Cotton",
    "Cotton": "Cotton",
    "Rapeseed & Mustard": "Mustard",
    "Rapeseed &Mustard": "Mustard",
    "Moong(Green Gram)": "Moong",
    "Moong": "Moong",
    "Masoor": "Lentil",
    "Lentil": "Lentil",
    "Sesamum": "Sesame (Til)",
    "Tur": "Arhar (Tur)",
    "Arhar/Tur": "Arhar (Tur)",
    "Peas & Beans (Pulses)": "Pea",
    "Water Melon": "Watermelon",
}


def load_vocab() -> set[str]:
    with open(CROP_LOG, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return {r["Crop"].strip() for r in rows}


def load_target_districts() -> list[str]:
    with open(GEO, encoding="utf-8") as fh:
        gj = json.load(fh)
    return sorted({ft["properties"]["NAME_2"].strip() for ft in gj["features"]})


def map_district(name: str) -> str:
    n = name.strip()
    return DISTRICT_ALIAS.get(n, n)


def map_crop(name: str, vocab: set[str]) -> tuple[str, bool]:
    n = name.strip()
    if n in vocab:
        return n, True
    v = VOCAB_ALIAS.get(n)
    if v and v in vocab:
        return v, True
    return "", False


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def build_d1(vocab: set[str]) -> pd.DataFrame:
    df = pd.read_csv(RAW / "upag_district_apy.csv")
    df = df[df["state_name"].astype(str).str.strip() == "Madhya Pradesh"].copy()
    df = df[df["year"].isin(KEEP_YEARS)].copy()
    df["season"] = df["season"].map({"Kharif": "Kharif", "Rabi": "Rabi", "Summer": "Zaid"})
    df = df[df["season"].notna()].copy()
    df["district"] = df["district_name"].map(map_district)
    rows = []
    for r in df.itertuples(index=False):
        vocab_crop, in_vocab = map_crop(r.crop_name, vocab)
        rows.append({
            "district": r.district,
            "season": r.season,
            "year": r.year,
            "source_crop": r.crop_name,
            "crop_vocab": vocab_crop,
            "in_vocab": in_vocab,
            "area_ha": float(r.area),
            "production_t": float(r.production),
            "source": "S1_upag",
        })
    return pd.DataFrame(rows)


def build_d2_fills(vocab: set[str], existing: pd.DataFrame) -> pd.DataFrame:
    """Add vocab crops missing from D1 (currently Pea), from S2, Rabi only."""
    df = pd.read_csv(RAW / "isdp_apy_district_1997-2023.csv")
    df = df[df["state_name"].astype(str).str.strip() == "Madhya Pradesh"].copy()
    df = df[df["year"].isin(KEEP_YEARS)].copy()
    df["season"] = df["season"].map({"Rabi": "Rabi"})
    df = df[df["season"].notna()].copy()
    df["district"] = df["district_name"].map(map_district)
    have = set(existing.loc[existing["in_vocab"], "crop_vocab"])
    rows = []
    for r in df.itertuples(index=False):
        vocab_crop, in_vocab = map_crop(r.crop_name, vocab)
        if not in_vocab or vocab_crop in have:
            continue
        rows.append({
            "district": r.district,
            "season": r.season,
            "year": r.year,
            "source_crop": r.crop_name,
            "crop_vocab": vocab_crop,
            "in_vocab": True,
            "area_ha": float(r.area),
            "production_t": float(r.production),
            "source": "S2_des",
        })
    return pd.DataFrame(rows)


def main() -> None:
    vocab = load_vocab()
    targets = load_target_districts()
    target_set = set(targets)

    d1 = build_d1(vocab)
    d2 = build_d2_fills(vocab, d1)
    allrows = pd.concat([d1, d2], ignore_index=True)

    unknown = sorted(set(allrows["district"]) - target_set)
    if unknown:
        raise SystemExit(f"Unmapped districts (fix DISTRICT_ALIAS): {unknown}")

    out = (
        allrows.groupby(
            ["district", "season", "year", "source_crop", "crop_vocab", "in_vocab"],
            as_index=False,
        )
        .agg(area_ha=("area_ha", "sum"), production_t=("production_t", "sum"),
             sources=("source", lambda s: "+".join(sorted(set(s)))))
    )
    out = out.sort_values(["district", "season", "year", "source_crop"]).reset_index(drop=True)
    out.to_csv(CLEAN / "area_by_district_season_year.csv", index=False)

    src_districts = sorted(set(d1["district"]) | set(d2["district"]))
    with open(ROOT / "eval" / "real_data" / "district_map.csv", "w",
              encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["source_label", "target_district", "kind"])
        for s in sorted(set(pd.read_csv(RAW / "upag_district_apy.csv")["district_name"].unique())):
            t = map_district(s)
            w.writerow([s, t, "alias" if s != t else "identity"])

    print(f"vocab crops: {len(vocab)}")
    print(f"target districts: {len(targets)}; source districts mapped: {len(src_districts)}")
    print(f"clean rows: {len(out)}")
    print(f"in-vocab vocab crops seen: {sorted(set(out.loc[out.in_vocab,'crop_vocab']))}")
    missing = sorted(vocab - set(out.loc[out.in_vocab, "crop_vocab"]))
    print(f"vocab crops with NO real series: {missing}")
    for f in sorted(RAW.glob("*.csv")):
        print(f"  raw {f.name} sha256={sha256(f)}")


if __name__ == "__main__":
    main()
