# S-series perturbation sets, v2 (amendment to STEP 2)

Supersedes the v1 table in `S_PERTURBATIONS.md` (kept as the historical record). Reason:
`eval/results/S_SIGNAL_CHECK.md` showed the v1 **uniform precipitation multipliers** cannot
move the oracle (the risk tool's SPI is refit from the same series, so it is exactly
scale-invariant: measured `max |Delta drought_z| = 0.00` at x1.30), and the **temperature arms**
had no oracle term at all. v2 keeps the sourced magnitudes but changes the SHAPE/PHASE/INTENSITY
of the series (and adds a heatwave oracle term, see `S_ORACLE_V2.md`).

All arms act on a working COPY of the per-district weather cache. `mcp_server/` is untouched;
`as_of_date` unchanged; called "simulated scenarios".

## Temperature (unchanged magnitudes)
| set | change | mechanism | rationale / source |
|-----|--------|-----------|--------------------|
| S-W1 | +1.0 C | temp offset | near-term central-India warming |
| S-W2 | +2.0 C | temp offset | mid-century SSP2-4.5 (+1.2-1.3 C rel. 1995-2014; Dhara et al. 2025, PLOS Climate, doi 10.1371/journal.pclm.0000724) |
| S-W3 | +3.0 C | temp offset (beyond-range) | upper warming scenario |
| S-H1 | +2.0 C in [as_of, as_of+21d] | sowing-window heat | growing-season heatwave; Rohini et al. 2019 (+0.5 heatwave events/decade central India) |

## Precipitation shape (REPLACES the scale-invariant multipliers)
| set | change | mechanism | rationale / source |
|-----|--------|-----------|--------------------|
| S-D1 | 30-day rain x0.10 | dry spell (agricultural drought) | IMD Monsoon-2009 = 77% LPA (-23%); 2015 = 86% (-14%); PLOS Climate 2025 drying |
| S-D2 | 45-day rain x0.05 | severe prolonged dry spell (beyond near-term) | as D1, prolonged |
| S-WET1 | forecast wk = 3x60 mm + 4x5 mm | heavy-rain week | JJAS intensification (+6-8%; Dhara 2025); extreme-rain events |
| S-WET2 | 3x90 mm + 4x10 mm | extreme-rain week (beyond) | intensification tail |

## Rainfall phase (unchanged)
| set | change | mechanism |
|-----|--------|-----------|
| S-O1 | rain series +14 d (onset delay) | IMD: MP onset delayed 3-7 d (up to 10-14 d west-central) |
| S-O2 | rain series +28 d (beyond) | 4-week onset delay |

## Compound (unchanged intent)
| set | change | mechanism |
|-----|--------|-----------|
| S-C1 | +2.0 C and 30-day rain x0.10 | hot-dry compound |

## Controls / natural experiment
| set | change | purpose |
|-----|--------|---------|
| S-N0 | identity | harness validity: evidence must equal `archive_v2/evidence` and `D = {}` |
| S-N1 | -1.5 C | direction reversal: cooling removes heat stress -> expect `D = {}` |
| S-NE15 | substitute 2015 weather (in-cache observed) | natural experiment (real deficit-monsoon year) |

## Measured oracle signal (offline, n=40 base scenarios; `eval/results/s_oracle_signal.json`)
STRICT `sig`/`|D|tot` (scenarios with `|D|>0` / total newly-infeasible instances):

| arm | STRICT sig/|D| | LENIENT sig/|D| | blocking term |
|-----|-----------------|------------------|---------------|
| W1 | 2 / 8 | 2 / 12 | heatwave (Wheat,Barley,Gram,Mustard) |
| W2 | 2 / 8 | 2 / 12 | heatwave |
| W3 | 2 / 8 | 2 / 12 | heatwave |
| H1 | 2 / 8 | 2 / 12 | heatwave |
| D1 | 0 / 0 | 10 / 20 | drought (lenient only: Rice,Sugarcane) |
| D2 | 0 / 0 | 11 / 22 | drought (lenient only) |
| WET1 | 21 / 21 | 21 / 84 | flood (Urad strict; +Moong,Sesame,Groundnut,Watermelon lenient) |
| WET2 | 21 / 21 | 21 / 84 | flood |
| O1 | 1 / 1 | 3 / 8 | flood+drought |
| O2 | 2 / 2 | 4 / 14 | flood+drought |
| C1 | 2 / 8 | 12 / 32 | heatwave + drought |
| N0 | 0 / 0 | 0 / 0 | control (correct) |
| N1 | 0 / 0 | 0 / 0 | control (cooling -> no new infeasibility) |
| NE15 | 2 / 2 | 14 / 31 | flood + drought |

Note: in STRICT mode the drought block is empty (all drought rows are `unverified`), so the
precipitation **dry** arms have STRICT `D = {}`. Per `S_ORACLE_V2.md`, the pre-specified
companion analysis for the dry arms uses LENIENT (declared before any run).
