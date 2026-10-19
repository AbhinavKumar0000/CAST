# Ground-truth table changelog (Phase 8 STEP C)

Convention: frozen tables are never edited in place. Any change ships as a new
versioned file (e.g. `crop_season_table_v1.1.csv`) with a dated entry here, and
metric recomputation reports BOTH the frozen v1 results and the new version
(see `eval/results/c3_season_validity_cited_v2.json`).

## 2026-10-13 — v1.1 (Barley citation found)

Added:
- `crop_season_table_v1.1.csv`
- `hard_constraints_v1.1.csv`

Changed rows (only Barley):

| table | row | v1 status | v1.1 status | evidence |
|---|---|---|---|---|
| crop_season_table | Barley/Rabi | unverified | cited | IIWBR pocket guide EB-53 (2023) "Barley Cultivation in India" — barley is a rabi (winter) crop grown in UP, Rajasthan, MP, Bihar, Punjab, Haryana, HP, J&K; KhetiVyapar (MP state rabi 2024-25): barley sowing target 36,000 ha; Indiastat "Area, Production and Productivity of Barley (Rabi) in Madhya Pradesh" series |
| hard_constraints | Barley/Kharif | unverified | cited | corollary of the rabi-only citing above (no kharif/zaid barley in India) |
| hard_constraints | Barley/Zaid | unverified | cited | corollary of the rabi-only citing above (no kharif/zaid barley in India) |

Source URLs (accessed 2026-10-13):
- IIWBR: https://iiwbr.org.in/wp-content/uploads/2023/08/EB-53-Barley-Cultivation-in-India-Pocket-Guide.pdf
- KhetiVyapar MP rabi targets: https://www.khetivyapar.com/en/rabi-crop-target-set-at-14-million-hectares-in-the-state-for-2024-25-4145
- Indiastat MP Barley (Rabi): https://www.indiastat.com/Madhya-Pradesh-state/data/agriculture/barley-17201

Unchanged, still unverified (see `UNVERIFIED_FOR_REVIEW.csv`): Rice/Rabi, Maize/Rabi,
Jowar/Rabi, Arhar/Rabi season rows; drought Rice, drought Sugarcane, flood Moong,
flood Sesame, flood Groundnut, flood Watermelon constraint rows.

## v1.2 - DES real-area correction of contradicted UNVERIFIED rows (2026-10-16)

Created `crop_season_table_v1.2.csv`. **v1.1 is untouched.** Adjudicated the season
rows against the DES/MoA&FW UPAG real district area series
(`eval/real_data/clean/area_by_district_season_year.csv`, 10,304 rows; 51 MP
districts; years 2015-16..2024-25), per `PROTOCOL.md` 8.30.

| crop | season | v1.1 status | v1.2 status | evidence (DES UPAG, MP) |
|---|---|---|---|---|
| Jowar | Rabi | unverified | **contradicted** | 0 ha rabi jowar in every year 2015-16..2024-25 (no district-season row) |
| Arhar (Tur) | Rabi | unverified | **contradicted** | 0 ha rabi arhar in every year 2015-16..2024-25 |
| Rice | Rabi | unverified | unverified (note updated) | nonzero only in 2024-25 (53,000 ha); zero in 2015-16..2023-24 - ambiguous, not contradicted |
| Maize | Rabi | unverified | unverified (note updated) | nonzero only in 2024-25 (222,000 ha); zero in 2015-16..2023-24 - ambiguous, not contradicted |

`contradicted` is a determinate negative: the crop is treated as NOT valid for the
season under both STRICT and LENIENT season-validity modes.

Unchanged, still unverified: drought Rice, drought Sugarcane, flood Moong, flood
Sesame, flood Groundnut, flood Watermelon constraint rows (the area series cannot
adjudicate environment constraints).

Recompute: `eval/scripts/recompute_season_validity_v1_2.py` ->
`eval/results/c3_season_validity_v1.2_vs_v1.1.{txt,json}`. Effect:
STRICT overall unchanged (0.83590; contradicted rows were already counted in STRICT);
LENIENT overall 0.83608 -> 0.83590, Rabi 0.98704 -> 0.98650 (Jowar/Arhar rarely enter
the C3 Rabi top-5). Hard-violation rate unchanged.

Out-of-scope observation (not changed here; flagged for review): Barley has nonzero
Kharif area in MP in 2015-16..2018-19 (369,098 ha, 4 years), in tension with the v1.1
hard-constraint rows `Barley/Kharif` and `Barley/Zaid` ("barley strictly rabi"). Those
rows were 'cited-v1.1', not 'unverified', so they are outside the scope of this
correction.

Source URLs (accessed 2026-10-16): DES/MoA&FW UPAG via India Data Portal / ISB CKAN
`https://ckandev.indiadataportal.com/dataset/f2bbc28c-6c7c-462b-9064-ea4c4213d466`
(resource `6f70d961-3a4f-4caa-b08f-f72f708791e1`; ODC-By). See `eval/real_data/SOURCES.md`.