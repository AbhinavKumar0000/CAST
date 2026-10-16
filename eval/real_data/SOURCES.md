# Real-world data sources (STEP 1)

Purpose: independent, real-world evaluation of AgroLLaMA crop recommendations against
actual district-level cropping patterns in Madhya Pradesh. All data here is public and
downloaded without any model/LLM call.

Retrieval date: 2026-10-16 (all downloads).
Retrieval method: `Invoke-WebRequest` over HTTPS, no authentication, no scraping of
login-gated pages.

Raw files are stored byte-for-byte under `eval/real_data/raw/` and are never edited.
Integrity hashes (SHA-256) are recorded below.

---

## 1. Used sources

### S1. UPAG district APY (PRIMARY)
- Title: Crop-wise Area, Production & Yield (UPAG)
- Upstream publisher: Directorate of Economics & Statistics (DES), Ministry of
  Agriculture & Farmers Welfare (MoA&FW), via `https://agriwelfare.gov.in/`
- Distribution: India Data Portal (CKAN), Indian School of Business (ISB), instance
  `https://ckandev.indiadataportal.com`
- Dataset page: `https://ckandev.indiadataportal.com/dataset/f2bbc28c-6c7c-462b-9064-ea4c4213d466`
- Resource page: `https://ckandev.indiadataportal.com/dataset/f2bbc28c-6c7c-462b-9064-ea4c4213d466/resource/6f70d961-3a4f-4caa-b08f-f72f708791e1`
- Download URL: `https://ckandev.indiadataportal.com/dataset/f2bbc28c-6c7c-462b-9064-ea4c4213d466/resource/6f70d961-3a4f-4caa-b08f-f72f708791e1/download/cropwise-area-production-yield-upag.csv`
- Licence: Open Data Commons Attribution License (ODC-By) (as declared by the portal)
- File: `raw/upag_district_apy.csv` (16,945,448 bytes, sha256
  `1318e848ef00bfb7e268930145a779054b8b4b5ea2f9bb2765c538fd5152cf6c`)
- Rows: 156,189. Columns: `id, year, state_name, state_code, district_name,
  district_code, season, crop_category, crop_name, crop_code, area, production, yield`
- Granularity: state, district, year, season, crop
- Units: area in Hectares, production in Tonnes, yield in Tonnes/Hectare
  (verified by internal consistency, see QA.md)
- Years: 2013-2014 to 2024-2025 (12 years)
- Seasons: Kharif, Rabi, Summer
- MP coverage: 11,968 rows, all 12 years, 55 district labels (see mapping notes)
- Why primary: it is the DES district series distributed from the MoA&FW domain, it
  covers the full target window 2015-16 to 2024-25, and its values reproduce
  independently (Wheat Rabi 2022-23 = 9,781,013 ha; Soybean Kharif 2022-23 =
  5,974,024 ha also appear in S2).

### S2. DES district APY, crop-wise (SUPPORT, horticulture + long history)
- Title: Area, Production, Yield (APY) (Crop-wise)
- Upstream publisher: DES via `https://data.desagri.gov.in` (APY report)
- Distribution: same India Data Portal (CKAN) dataset page as S1
- Resource page: `https://ckandev.indiadataportal.com/dataset/f2bbc28c-6c7c-462b-9064-ea4c4213d466/resource/f980409d-49a2-42ae-9eb0-182365005c04`
- Download URL: `https://ckandev.indiadataportal.com/dataset/f2bbc28c-6c7c-462b-9064-ea4c4213d466/resource/f980409d-49a2-42ae-9eb0-182365005c04/download/crop-wise-area-production-yield.csv`
- Licence: Open Data Commons Attribution License
- File: `eval/real_data/raw/isdp_apy_district_1997-2023.csv`
  (56,222,102 bytes, sha256 `fe10fbf129b3501bbb3d282c7600402a8ed7248c116f2cc9428bc2b573d1d4a9`)
- Granularity: state, district, year, season, crop
- Units: area in Hectare, production in Tonnes (explicit `area_unit`,
  `production_unit`, `yield_unit` columns)
- Years: 1997-1998 to 2022-2023 (26 years)
- Seasons include: Autumn, Kharif, Rabi, Summer, Winter, Whole Year, Total
- MP coverage: 34,714 rows, 52 district labels
- Why used: broader crop list (includes "Peas & Beans (Pulses)" and "Water Melon"
  which UPAG lacks) and an independent long history for cross-checks.

### S3. DES district data 2023-24 (SUPPORT, cross-check only)
- Title: DES District Data For 2023-24
- Upstream publisher: DES/MoA&FW
- Distribution: mirror at `https://www.global-agriculture.com/wp-content/uploads/2025/03/DES-District-Data-For-2023-24.csv`
- File: `eval/real_data/raw/des_district_2023-24.csv`
  (1,641,326 bytes,
  sha256 `265659944f239be33cfbafe6a3b021fdf22a7f2a9f2689a8b184ba13d85bba03`)
- Columns: State, District, Crop, Season, Area-2023-24, Production-2023-24, Yield-2023-24
- Units: Area in Lakh Ha, Production in Lakh Tonnes (per publisher description)
- MP: 2,036 rows, 52 district labels, seasons Kharif/Rabi/Summer/Total, only 18 crop
  labels (missing Soybean, Cotton, Sugarcane, horticulture)
- Why kept: it independently reproduces UPAG's 2023-24 MP Wheat total
  (74.99 Lakh Ha = 7,497,000 ha). Used only as a cross-check, not as an input.

---

## 2. Rejected sources

- `https://dataful.in/datasets/5634` (MP district-season-crop APY 1997-98 to 2024-25):
  REJECTED. Download requires account login and a paid plan.
- `https://www.global-agriculture.com/.../DES-District-Data-For-2024-25.csv`:
  REJECTED (as an input). Downloaded
  (`eval/real_data/raw/des_district_2024-25.csv`, 537 rows) but the file contains only
  Punjab at district level. No MP rows, so it is unusable. Kept on disk for the record.
- Kaggle "India Agriculture Crop Production" and similar: REJECTED. Download requires a
  Kaggle account (login-gated).
- Indiastat and other paywalled aggregators: REJECTED. Login/subscription gated.

---

## 3. Coverage vs the evaluation target

Target: 51 MP districts (from `data/processed/mp_districts.geojson`), 2015-16 to 2024-25,
district x season x crop.

- Years 2015-16 to 2024-25: fully covered by S1 (UPAG).
- Years 2015-16 to 2022-23: also covered by S2, adding Pea and Watermelon.
- 2023-24 and 2024-25: covered only at district level by S1 (UPAG) for field crops;
  the standalone DES 2024-25 district file is incomplete (Punjab only).
- Crop vocabulary: S1 covers 20 of the 21 registry crops; "Watermelon" is horticultural
  and only appears in S2. "Pea" appears only in S2. "Kodo-Kutki" maps to "Small Millets".

---

## 4. Raw file integrity (SHA-256)

| file | bytes | rows | sha256 |
|---|---|---|---|
| upag_district_apy.csv | 16945448 | 156189 | 1318e848ef00bfb7e268930145a779054b8b4b5ea2f9bb2765c538fd5152cf6c |
| isdp_apy_district_1997-2023.csv | 56222102 | 455359 | fe10fbf129b3501bbb3d282c7600402a8ed7248c116f2cc9428bc2b573d1d4a9 |
| des_district_2023-24.csv | 1641326 | 23442 | 265659944f239be33cfbafe6a3b021fdf22a7f2a9f2689a8b184ba13d85bba03 |
| des_district_2024-25.csv | 36091 | 537 | 3af9e695ca2b693234625c137a334f8939789df9f9112fe69b05609e220dcb11 |

Regenerate hashes with `Get-FileHash -Algorithm SHA256 eval/real_data/raw/*.csv`.

---

## 5. Compliance

- No paywalled or login-gated content was accessed.
- Requests used a plain research User-Agent, sequential and rate-limited, HTTPS only.
- Raw data is retained unmodified; all cleaning happens in
  `eval/real_data/scripts/` and writes to `eval/real_data/clean/`.
- No model or LLM API call was made in producing this file.
