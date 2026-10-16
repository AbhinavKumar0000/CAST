# QA: real-world reference dataset (STEP 2)

Everything below is derived from the raw files by
`eval/real_data/scripts/build_dataset.py`. No value was hand-entered, estimated, or
imputed.

## 1. Inputs

| id | file | rows | role |
|---|---|---|---|
| S1 | `raw/upag_district_apy.csv` | 156189 | primary (UPAG/DES) |
| S2 | `raw/isdp_apy_district_1997-2023.csv` | 455359 | Pea fill + cross-check |
| S3 | `raw/des_district_2023-24.csv` | 23442 | cross-check only |
| -  | `raw/des_district_2024-25.csv` | 537 | unused (Punjab only) |

SHA-256 values are recorded in SOURCES.md and reprinted by the build script.

## 2. Output

`eval/real_data/clean/area_by_district_season_year.csv`
- rows: 10,304
- key: (district, season, year, source_crop), 0 duplicates
- districts: 51 (all geometry districts)
- seasons: Kharif, Rabi, Zaid
- years: 2015-2016 .. 2024-2025 (10 years)
- columns: district, season, year, source_crop, crop_vocab, in_vocab, area_ha,
  production_t, sources
- in-vocab rows: 8,781; out-of-vocab rows: 1,523

`eval/real_data/district_map.csv`: source district label -> target district (51 rows).

## 3. Harmonisation rules

Districts: label -> 51 geometry districts. Aliases applied:
Agar-Malwa -> Agar Malwa; Khandwa (East Nimar) -> East Nimar;
Khargone (West Nimar) -> West Nimar; Narmadapuram -> Hoshangabad.
Post-2018 districts folded into parents: Niwari -> Tikamgarh; Maihar -> Satna;
Mauganj -> Rewa; Pandhurna -> Chhindwara. All 51 targets were reached; the build
script aborts if any label is unmapped.

Seasons: source Kharif -> Kharif; Rabi -> Rabi; Summer -> Zaid. No other S1 seasons
exist. S2 fill (Pea) uses Rabi -> Rabi only.

Crops: mapped to the 21-crop registry vocab via an explicit alias table. The
following registry crops have real series in the clean dataset (19):
Arhar (Tur), Bajra, Barley, Cotton, Gram, Groundnut, Jowar, Lentil, Maize, Moong,
Mustard, Pea, Rice, Sesame (Til), Soybean, Sugarcane, Sunflower, Urad, Wheat.
Registry crops with NO real series: Kodo-Kutki, Watermelon (see 6).

Years: 2015-2016 .. 2024-2025 kept.

Units: area_ha in hectares, production_t in tonnes (S1 and S2 both use these; S2
states them explicitly). The S3 2023-24 file uses Lakh Ha / Lakh Tonnes and is not
fed into the clean dataset.

## 4. Source-consistency checks

- S1 and S2 agree exactly on overlapping values, e.g. MP Wheat Rabi 2022-23 =
  9,781,013 ha and MP Soybean Kharif 2022-23 = 5,974,024 ha appear in both.
- S3 (DES 2023-24) MP Wheat total = 74.99 Lakh Ha = 7,497,000 ha, which equals S1's
  2023-24 MP Wheat value (7,497,000 ha). Independent agreement.
- Yield check: MP Wheat 2022-23 production / area = 34,977,038 t / 9,781,013 ha =
  3.58 t/ha, a plausible wheat yield.

## 5. Known anomalies and caveats

- MP Wheat Rabi area jumps to ~10.2 M ha in 2019-20 and ~9.8 M ha in 2022-23, then
  drops to ~7.5 M ha in 2023-24. The per-district values remain plausible (max ~0.4 M
  ha) and both S1 and S2 carry the same figures, so this is how the DES/UPAG series
  is published. Reported here for transparency; no adjustment was applied.
- Zaid reference lists are short: 2 to 5 in-vocab crops per district (UPAG reports
  only a few summer crops). Kharif lists are 12 to 14 crops; Rabi lists 6 to 9.
  Metrics for Zaid must therefore be read alongside the shortness of its reference.
- "Small Millets" in S1 is not mapped to Kodo-Kutki (the category is broader than the
  registry crop), so it stays out-of-vocab. See 6.

## 6. Missing data and how it is handled

- Kodo-Kutki and Watermelon: no usable district series in the target window.
  Watermelon appears only in 2003-04 (699 ha, "Whole Year") in S2; Kodo-Kutki is
  subsumed under "Small Millets" in S1. Neither is in the reference. Consequences:
  a model that recommends Kodo-Kutki or Watermelon scores them as non-matches against
  the area reference; this is disclosed in the report.
- Pea is sourced from S2 and therefore covers 2015-16 .. 2022-23 only (8 years), all
  51 districts. Its mean is over 8 years, other crops over 10 years where available.
- 2024-25 exists only in S1 (US2 has no 2023-24/2024-25). Every district-season pair
  (153) has at least one row; there are no empty cells.

## 7. Out-of-vocab crops present in the clean data

Other Pulses (482 rows), Linseed (391), Small Millets (239), Nigerseed (185),
Mesta (62), Safflower (61), Jute (54), Castorseed (49). These are retained so the
out-of-vocab share of the real top-5 can be measured.
