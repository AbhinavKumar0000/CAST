# S-series STEP 2 - named perturbation sets (design note)

Status: DRAFT (STEP 2). No model/LLM call made. Nothing committed. Awaiting S-STEP 5 approval.
Author note: this file only *designs* the perturbations. No data file is modified here; the
perturbations are applied to COPIES at run time (originals untouched, `mcp_server/` untouched).

## 0. Purpose and guardrails
- Purpose of the S series: test the core claim that no-tool LLM advice rests on training-era
  (static, climatological) knowledge, whereas the MCP tool path lets the model respond to the
  **current** conditions it is handed. Mechanism test, not a forecasting claim.
- Shifted inputs are called **"simulated scenarios"**. They are **not** real-time data, not
  forecasts, and not predictions. Each is a single-variable sensitivity with a magnitude taken
  from published literature/historical record, applied to a copy of the cached weather and/or a
  scenario date.
- Every magnitude below carries source, URL, accessed date, and licence. Magnitudes are
  *plausible perturbations of the same order as cited projections/records*, not endorsements.
- Nothing in `mcp_server/` (code, URLs, thresholds, weights, prompts) changes. Perturbation is
  applied at the eval/harness layer to the data files the tools read (see `S_SCOPE.md`).

## 2.1 Perturbation sets

Legend: mechanism refers to what is edited. `W`=temperature add-offset applied to every daily
`temperature_2m_mean/max/min` in the scenario window and in the climate-normals series; `R`=multiplicative
factor on `precipitation_sum`; `O`=time shift of the daily-rainfall series within the season; `H`=windowed
warming; `NE`=natural-experiment year substitution. All climate perturbations are applied to a working
copy of `eval/cache/weather/<district>.json`; originals are never edited.

| # | set | mechanism | magnitude | grounding source | accessed |
|---|---|---|---|---|---|
| 1 | **S·W1** warm_near | W | **+1.0 °C** (all days) | Dhara et al. 2025 (PLOS Climate): mid-century SSP2-4.5 +1.2–1.3 °C rel. 1995–2014; +1 is the low band | 2026-10-16 |
| 2 | **S·W2** warm_mid | W | **+2.0 °C** | CMIP6/SSP2-4.5 far-future all-India ≈ +2 °C; Sanjay et al. RCP4.5 far-future +2.44±0.41 °C | 2026-10-16 |
| 3 | **S·W3** warm_far (beyond-range) | W | **+3.0 °C** | upper tail of regional (NW/central India) SSP2-4.5/CORDEX warming; beyond the mid-century all-India best estimate | 2026-10-16 |
| 4 | **S·R1** dry_strong | R | **×0.80 (−20 %)** | IMD/Rainfall Statistics: 2009 all-India −23 % (77 % of LPA), 1918 −25 %; "deficient" band = −20…−59 % | 2026-10-16 |
| 5 | **S·R2** dry_extreme (beyond-range) | R | **×0.60 (−40 %)** | beyond the modern all-India record (worst ≈ −25 %); used only as a beyond-range stress arm | 2026-10-16 |
| 6 | **S·R3** wet_strong | R | **×1.30 (+30 %)** | upper end of CMIP6 JJAS increase (all-India mean +6–8 %; wet-extreme/regional tails larger); floods-flavoured arm | 2026-10-16 |
| 7 | **S·O1** onset_late2 | O | **+14 days** | IMD revised normals: MP onset delayed 3–7 d (state level) to 10–14 d (west-central operational, 1961–2019); SD of onset ≈ 8–10 d | 2026-10-16 |
| 8 | **S·O2** onset_late4 (beyond-range) | O | **+28 days** | beyond the revised-normal delay; extreme-year tail | 2026-10-16 |
| 9 | **S·H1** sow_heat | H | **+2.0 °C on the sowing-window weeks only** | Rohini et al. 2019/2016 (CMIP5/observations): central-India heatwave frequency +0.5 events/decade, duration +4–7 d/decade | 2026-10-16 |
| 10 | **S·C1** hot_dry | W+R | **+2.0 °C and ×0.70 (−30 %)** | compound hot-dry extremes increasing over India (Dhara et al. 2025); combines #2 and #4 family | 2026-10-16 |
| 11 | **S·N0** identity (control) | none | copy = original | harness side-effect check: outputs must be byte-identical to base | 2026-10-16 |
| 12 | **S·N1** cool_wet (control) | W+R | **−1.0 °C and ×1.20 (+20 %)** | direction-reversal control: expect shifts opposite to warm/dry arms | 2026-10-16 |
| 13 | **S·NE15** natural experiment | NE | replay real **2015** (all-India −14 %; archive covers 2013-12-01…) | IMD Monsoon-2015 end-of-season report; archived Open-Meteo history already in the cache | 2026-10-16 |

Notes on #13: the archive window is 2013-12-01…2026-01-15, so 2014/2015 are the only readily available
all-India-deficient monsoon years. The natural-experiment arm uses real dates (no synthetic magnitudes) and
is reported separately from the synthetic arms.

## Source list (URL + licence + accessed date)

| ref | value used | URL | licence | accessed |
|---|---|---|---|---|
| Dhara et al. 2025, PLOS Climate | +1.2–1.3 °C mid-century SSP2-4.5; JJAS +6–8 %; compound hot-dry | https://doi.org/10.1371/journal.pclm.0000724 | CC BY 4.0 | 2026-10-16 |
| IMD press release, new onset/withdrawal dates (MoES) | MP onset delayed 3–7 d vs old normals; Bhopal 15-Jun→22-Jun; Khandwa 14→20 | https://mausam.imd.gov.in/backend/assets/press_release_pdf/IMD_Press_release_new_onset_and_withdrawal_dates(Final).pdf | GoI/MoES public release (cite only) | 2026-10-16 |
| IMD new-normal onset study | operational delay 3–7 d east-central → 10–14 d west-central (1961–2019) | https://internal.imd.gov.in/press_release/20200515_pr_804.pdf | Government of India | 2026-10-16 |
| IMD FAQ on Monsoon | categories: deficient −20…−59 %, large-deficient −60…−99 % (of LPA); meteorological drought < 75 % of LTA | https://mausam.imd.gov.in/imd_latest/monsoonfaq.pdf | Government of India | 2026-10-16 |
| IMD Monsoon-2009 / Monsoon-2015 end-of-season reports | 2009 = 77 % of LPA (−23 %); 2015 = 86 % (−14 %); record low 1918 = 75 % | https://www.tropmet.res.in/~kolli/MOL/Monsoon/year2009/Monsoon-2009.pdf ; .../year2015/Monsoon-2015-NEW.pdf | Government of India | 2026-10-16 |
| Rohini et al. 2016, Sci. Rep. 6:26153 | observed central/NW India heatwave increases | https://www.nature.com/articles/srep26153 | CC BY 4.0 | 2026-10-16 |
| Rohini et al. 2019, Clim. Dyn. (CMIP5 projections) | central-India heatwave freq +0.5 events/decade, duration +4–7 d/decade | https://doi.org/10.1007/s00382-019-04754-9 | Springer; numeric citation only | 2026-10-16 |

## Out of scope (unchanged from S_SCOPE.md)
- No new tool parameters, no new MCP tools, no change to Open-Meteo URL, scorer weights, prompts, or thresholds.
- `mcp_server/` is not edited; originals (`eval/cache/weather/*`, `crop_log*.csv`, GT tables) are never overwritten.
- Soil and crop-KB perturbations are NOT part of the climate-scenario core (they do not represent "changed conditions" a farmer would ask about); recorded only as optional extras.

## Open items before running
1. Route the perturbed cache without editing `eval/tools/eval_risk_tool._load_weather_cache` (hard-coded `Path("eval/cache/weather")`) — via an isolated cache root / cfg override at the eval layer (see S_SCOPE.md).
2. Confirm season for each scenario arm second-by-second with the frozen `MONTH_TO_SEASON` map so `S·O1/O2` actually land in Kharif onset and `S·H1` in the sowing window.
3. Decide, in STEP 4, whether the beyond-range arms (W3, R2, O2) report in the primary table or a labelled sensitivity table.

All magnitudes are single-point sensitivities, not forecasts, and will be reported as such.
