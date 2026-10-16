# Circularity audit (STEP 3)

Question: is the real-world reference independent of the system under test, or does the
evaluation risk rewarding what the system already "knows"? This audit traces the
provenance of every input to the real-world evaluation and quantifies overlap.

Everything below was checked against the repository as it is; no model/LLM call was made.

---

## 1. Provenance of each artifact

| artifact | used for | provenance | independent of the model? |
|---|---|---|---|
| S1 UPAG district APY | reference (area/production) | DES/MoA&FW via agriwelfare.gov.in, distributed by India Data Portal | yes |
| S2 DES crop-wise APY | Pea fill, cross-check | DES via data.desagri.gov.in, India Data Portal | yes |
| S3 DES 2023-24 | cross-check | DES, global-agriculture mirror | yes |
| `mp_districts.geojson` | scenario districts | GADM v4.1 (51 districts) | yes |
| `season_tool.MONTH_TO_SEASON` | scenario season strata | repo code (month map) | yes |
| `crop_log.csv` | crop vocabulary + model scoring | hand-authored (21 crops, requirement ranges) | shared with the model |
| model outputs | system under test | `eval/runs/*/results.json` (pre-existing) | n/a |
| `crop_season_table_v1.1.csv` | internal season-validity check (not used here) | agronomic documents (SLBC-MP, evikas, CRIDA, ...) | no (but does not feed the area reference) |

The crop score tool (`mcp_server/crop_score_tool.py`) ranks crops from `crop_log.csv`
requirement ranges. It does not read any DES area/production series. The scenarios are
sampled from district polygons and assigned seasons by month. So neither the model's
inputs nor the scenario geometry share provenance with the reference area data.

## 2. Findings

F1. Reference vs model: independent. The reference is held out by construction; the
model was never given DES district area data in any condition (C0, C0b, C1a, C1b, C2a,
C2b, C3). No new calls are made in this evaluation.

F2. Reference vs scenarios: independent. Scenarios come from geometry + calendar only.

F3. Vocabulary restriction (the one real overlap). The evaluation universe is the
21-crop registry in `crop_log.csv`. The DES source has more crops for MP (29 in S1,
61 in S2). Restricting the reference to the 21 registry crops is a selection made
using prior knowledge of which crops matter in MP, and it can inflate apparent
agreement. Measured size of the effect:
- 72% of the 153 district x season cells have all of their real top-5 inside the
  21-crop vocabulary; 28% have at least one out-of-vocab crop in the real top-5
  (mean 0.31 out-of-vocab crops per cell).
- The recurring out-of-vocab crops are "Other Pulses" (a residual Rabi category),
  "Small Millets" (Kharif), Linseed, Nigerseed, Mesta, Safflower, Jute, Castorseed.
Mitigation: the report will publish (a) the out-of-vocab share of the real top-5 and
(b) metrics computed against the vocabulary-restricted reference, and it will state
that agreement is conditional on the registry's crop set. Kodo-Kutki and Watermelon
are absent from the reference entirely (see QA.md §6), which works against, not for,
the system, so it does not inflate agreement.

F4. Registry vs GT season table. Both are "MP crops", but the season table's rows come
from agronomic documents, not from the DES area series, and it is not an input to the
area reference. There is no shared numeric provenance between the two.

F5. LLM training contamination (inherent, not resolvable in-repo). The models may have
seen MP cropping patterns during training. This cannot be measured from inside the
repo and applies to any LLM benchmark. It is disclosed as a limitation; it is not a
pipeline circularity.

F6. District set. GADM has 51 districts (the newer official districts are missing). The
reference folds post-2018 districts (Niwari, Maihar, Mauganj, Pandhurna) back into
their parents to match the 51 geometry districts, so reference and scenarios use the
same district set.

## 3. Verdict

- The evaluation pipeline itself is not circular: the reference is external and
  independent, the model never saw it, and no dependency runs from model outputs back
  into the reference.
- Two residual risks are recorded rather than eliminated:
  (a) vocabulary restriction (quantified above, mitigated by disclosure), and
  (b) LLM training contamination (inherent, disclosed).
- No shared-file or shared-source shortcut was found between the reference and the
  system under test.

Because this is the pre-registered stop point for the circularity check, the
evaluation pauses here for confirmation before pre-registration (STEP 4) and scoring
(STEP 5). The two open decisions are: whether to proceed given F3/F5 as documented,
and whether to also report an unrestricted (all-crop) reference as a secondary metric.
