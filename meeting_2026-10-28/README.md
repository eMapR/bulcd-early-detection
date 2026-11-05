# BULC-D follow-up meeting, 2026-10-28

Six figures that answer the questions from the 2026-09-30 meeting (detection timing, expectation
periods, new vs. older change, practical use), plus regional processing as an extra result.

- `figures/` — PNGs, 2666 × 1500 px (16:9, 200 dpi), one per slide.
- `scripts/` — how they were made (all read-only: no Earth Engine asset, algorithm or product was changed).
  `fetch_pilot.py` → `fetch_pixels.py` → `spot_check.py 2026 2025 2024` → `expectation_compare.py A B C` → `make_figures.py`.
- `data/` — the downloaded arrays and the numbers behind each figure (`figure_numbers.json`, `spot_check_*.json`).

**Map display.** Slides 2 and 6 use a flat light-gray base (`#e4e3df`) for land not otherwise colored,
with masked water in white. Slide 4 keeps a lightened grayscale Sentinel-2 image (Jul–Sep 2026 median) for
geographic context. The background is display only. **No forest mask was applied** (`mask_non_forest: false`;
only water is masked), so every area and percentage covers all land-cover types.

**Completed vs. proposed.** Slides 1–4 show completed results only. On Slide 5, everything under
"Next steps" is proposed work.

**Validation status.** The full regional validation was run on islay. Its results and notes could not be
retrieved: the code (`feature/regional-batch-processing` @ `32b11bf`) was never pushed, and the islay SSH key
wasn't loaded. The figures therefore cite only a **spot check** run for this meeting (see Slide 4). Don't present
it as the full validation.

---

## Slide outline

| # | Title | Figure | Question it answers (2026-09-30) |
|---|---|---|---|
| 1 | The detection-year problem | `slide1_detection_year_problem.png` | Why is older change mapped as a 2026 decrease? |
| 2 | 2026 decreases by first detection year | `slide2_original_vs_detection_year.png` | How do we separate new 2026 change from older change? |
| 3 | Understanding detection timing | `slide3_detection_timing_pine_mountain.png` | What does a detection date mean? Seasonal false detections |
| 4 | Regional processing | `slide4_regional_pilot.png` | Can this run beyond single pixels and small areas? |
| 5 | Processing cost; results and next steps | `slide5_processing_performance.png` | What's validated, what's left, path to Region 6 |
| 6 | How does the expectation period affect detection? | `slide6_expectation_period.png` | Al's question: does a different expectation window make detections easier to interpret? |

---

## Slide 1: The detection-year problem

**Caption.** A regional-pilot pixel whose NBR fell from about 0.87 to 0.18 sometime between the 2024 and 2025
observation seasons (Oct 2024–May 2025, outside the Jun 1–Sep 30 window), not necessarily during 2025. Each season is an independent BULC-D run against the same 2018–2023 expectation. The 2024 run ends
unchanged; the 2025 run crosses the threshold on Jun 21 and ends as decrease; the 2026 run crosses again on
Jun 25 and also ends as decrease. The 2026 condition map alone would report it as 2026 change.

**Talking points**
- BULC-D asks "does this season differ from the expectation?", not "did something change this season?".
  With a fixed 2018–2023 expectation, a change that is already there still differs from normal in 2026.
- "Confirmed in 2025" is when BULC-D first saw it, not when it happened: the drop occurred between the 2024
  and 2025 seasons, when no observations are used.
- This is expected behavior, not an algorithm error. The fix is in how we report results: track the first
  season each pixel was confirmed as decrease.
- The live rerun of this pixel reproduces the exported tile values exactly (final P(decrease)
  0.0435 / 0.9145 / 0.9145).

*Note:* the NBR pattern looks like a harvest, but it hasn't been checked against imagery or reference data, so
the slide says "change". Pixel −123.53168, 44.76580.

## Slide 2: 2026 decreases by first detection year (main figure)

**Caption.** Left, "2026 condition: decrease": every pixel classified as decrease at the end of the 2026
season (35.3 km² in the 400 km² pilot). Right, "2026 decreases by first detection year": the same pixels,
colored by the first season BULC-D confirmed them as decrease (blue 2024 or earlier, amber 2025, red 2026).
Gray is other land (unchanged or increase in 2026); white is masked water. No forest mask.

The panel titles avoid "original" and "new", which could be read as the original BULC-D algorithm vs. our
rebuild. Both maps come from the same rebuild run; the right one only adds detection year.

| First confirmed | km² | % of 2026 decrease |
|---|---:|---:|
| 2024 or earlier | 17.1 | 48.5% |
| 2025 | 8.4 | 23.8% |
| 2026 | 9.8 | **27.7%** |

**Talking points**
- **Only 28% of the 2026 decrease area was first confirmed in 2026.** Nearly half had already been
  confirmed in 2024, the first season analyzed.
- Detection year is when BULC-D *first confirmed* the decrease, not when the disturbance happened. "2024 or
  earlier" includes any change that predates 2024, as long as it still differs from 2018–2023.
- "Confirmed" means the season *ended* as decrease (the end-of-season rule adopted 2026-09-30), so brief
  within-season crossings don't count.

*Product check (done before making the figure):* all 4 tiles are present in the 2024, 2025, 2026 and stack
collections; every band covers all 443,427 land pixels. `detection_year` equals "the earliest season that ended
as decrease" with zero exceptions, and the stack's `condition` equals the 2026 product's. Also in the product
but not on the slide: 4.6 km² first confirmed in 2024 is no longer decrease in 2026.

## Slide 3: Understanding detection timing

**Caption.** Robert's Pine Mountain pixel (central Oregon, burned fall 2024). This is a separate experiment
with different settings from the regional pilot. The single-year 2023 expectation predicts high spring NBR,
but in 2024 the pixel was snow-free from April. BULC-D's first detection, Apr 17, is the snowmelt (amber,
hatched: false detection); the fire shows up as a second episode starting Sep 24 that lasts to season end
(red: the real disturbance).

**Talking points**
- First detection ≠ disturbance date. Here the first detection is a seasonal false detection, about five
  months before the real disturbance.
- The season still counts as a confirmed decrease (it ends at P = 0.91), and "last detection" picks out the
  fire. That's why the apps now report last detection and detection episodes as well as first detection.
- The same effect applies at the year level: a change between seasons (like Slide 1) gets its first
  detection the next season.

*Settings:* expectation 2023 only, monitoring 2024, Feb 1–Nov 15, L8+L9+S2, fit order 1, interactive-app
defaults. Source: `experiments/output/pine_mountain_fit_order/` (`docs/findings.md`, 2026-10-13).

## Slide 4: Regional processing

**Caption.** Oregon Coast Range pilot: a 20 × 20 km box (400 km²) of four 10 × 10 km tiles around the
original testsite, at 30 m in EPSG:5070. The map shows 2026 decrease (35.3 km², 8.8% of land) over a
lightened Sentinel-2 image for context. The products were exported as Earth Engine assets and are read
back without rerunning BULC-D. The slide shows the spot check and the islay validation in separate boxes:
the spot check is complete; the islay results were not retrieved.

**Talking points**
- We've moved from single pixels and live map requests to batch exports: 16 exports (12 tile-seasons and 4
  detection-year stacks), all succeeded, 1–4 min per tile per season (0.8–4.2 min; 135–235 EECU-seconds).
- Each season product has 9 bands (condition, three probabilities, first and last detection, episode count,
  monitoring and expectation observation counts), plus the detection-year stack.
- **Spot check, not the full validation:** a live BULC-D rerun over the 40 × 40 pixel window where all four
  tiles meet matched the tiles on all 1,600 pixels for 2024, 2025 and 2026, with probabilities within
  0.00005 (uint16 storage precision). There were no seam artifacts in that window.
  - The only differences were `first_detection_doy` on increase pixels (28 / 12 / 9). That band records decrease
    timing only, so this is a definition difference, not an error.

## Slide 5: Results and next steps

**Caption (figure).** Earth Engine batch-export cost for one 10 km tile. EECU-seconds (Earth Engine Compute
Unit-seconds) are Earth Engine's measure of a task's computational cost, independent of queue time;
wall-clock minutes are shown alongside. Left: cost rises with expectation
length and with Sentinel-2 in the expectation (152 EECU-s for the pilot's 6-year L8 expectation; about
640–650 for 6-year S2 expectations). Right: per-area cost by export block size with the pilot config
(113–196 EECU-s per 100 km²). Benchmark runs, 2026-10-26.

**Completed**
- *Algorithm:* Python rebuild ≡ original BULC-D GUI at reference pixels (decrease, unchanged, increase);
  bulcd.js matches Python to floating-point precision (decision 0011).
- *Batch processing:* four-tile pilot exported for 2024–2026 plus the detection-year stack. Full validation
  done on islay (results to be brought over); spot check here (Slide 4).
- *Detection year:* separates the 2026 decrease into 2024-or-earlier / 2025 / 2026 (Slide 2). Last detection
  and detection episodes are now in both apps.
- *Performance:* a pilot tile-season takes minutes; S2 expectations that fail interactively all completed as
  batch exports.

**Remaining issues**
- *Expectation period and sensors are not final.* A longer or S2 expectation costs up to about 4× more
  per tile. Mixing an L8-only expectation with S2 monitoring inflated the 2024 class at North Cascades
  (2026-09-30).
- *Seasonal false detections:* spring snowmelt (Pine Mountain) and early-season transients in the parks.
  The confirmed rule removes many of them, but not all.
- *Detection year ≠ disturbance year;* "2024 or earlier" can't date older change.
- No scientific (reference-data) validation yet. So far everything is engineering equivalence.

**Next steps (proposed)**
1. Bring the islay validation results and the `feature/regional-batch-processing` branch into the shared repo.
2. Decide the expectation period and sensors, using the probe and benchmark results.
3. Run the Pine Mountain box as a seasonal false-detection test in the regional workflow.
4. Expand to the R6 ecoregions (FS Multi-Model boundaries): job tracking, resumability, a regional viewer.
5. Reference-data assessment (scientific validation), then a local backend (OSU Slurm) compared against GEE
   over Oregon.

## Slide 6: How does the expectation period affect detection? (experiment for Al's question)

**This is an experiment, not a recommendation.** It shows what changes when the expectation window changes.
It does not show that one window is better.

**Setup.** Same 400 km² pilot, same 2026 monitoring season (Jun 1–Sep 30). Only the expectation years
change; everything else is the pilot's stored config (L8 expectation, L8+L9 monitoring, sensitivity 1,
thresholds 0.65 / 0.75, 30 m, EPSG:5070).
- **A, 2018–2023 (pilot):** recomputed live, then checked against the exported product. It matched on all
  443,427 land pixels, with probabilities within 0.00005 and identical expectation observation counts.
- **B, 2024–2025 (recent only):** computed live.
- **C, 2018–2025 (extended):** computed live.

Nothing was exported or written to Earth Engine.

**Caption.** 2026 classifications under three expectation windows (red decrease, blue increase, gray
unchanged land, white masked water), and where A and B disagree (orange decrease under A only, green
decrease under B only, faded violet increase differs, gray same class). Each map title gives its decrease
area and median clear expectation observations per pixel. Three key-finding tiles summarize A vs B, and a
"Read with care" box carries the qualifications. No forest mask: all land-cover types.

**Key findings on the slide (A vs B)**
- **−54% decrease area:** 35.3 → 16.3 km².
- **90%** of decreases first confirmed in 2026 under A are still decrease under B.
- **10%** of 2024-or-earlier detections are still decrease under B.
- Headline: the recent window mainly removes older, persistent detections.

**"Read with care" box on the slide**
- No forest mask: all land-cover types included.
- Fewer detections ≠ better accuracy; no reference data were compared.
- B has fewer observations (19 vs 47 per pixel) and may treat 2024–2025 disturbances as normal (5.5 km² of
  2024 detections become 2026 increase).
- The comparison shows how long detections persist, not which window is more accurate.

The full tables (including C and increase area) are below; they are in the notes, not on the slide.

| Expectation | Clear obs. per pixel (median) | Decrease km² | Increase km² | Same class as A |
|---|---:|---:|---:|---:|
| A 2018–2023 | 47 | 35.3 | 51.7 | — |
| B 2024–2025 | 19 | 16.3 | 29.5 | 82.1% |
| C 2018–2025 | 66 | 23.9 | 30.3 | 91.7% |

| A's 2026 decrease, first confirmed in | km² | Still decrease under B | Under C |
|---|---:|---:|---:|
| 2024 or earlier | 17.1 | 10% | 43% |
| 2025 | 8.4 | 62% | 89% |
| 2026 | 9.8 | 90% | 92% |

Where A's decrease goes under B:
- 16.3 km² becomes unchanged.
- 3.2 km² becomes **increase**.
- Only 0.6 km² is decrease under B but not under A.

Also: 5.5 km² first confirmed as decrease in 2024 is classified as *increase* in 2026 under B. That's
probably regrowth judged against a disturbed expectation; not checked against imagery.

**Why the expectation window matters (for the explanation on the slide)**
- **The expectation defines "normal".** BULC-D scores each 2026 observation by how far it falls from the
  fitted seasonal curve, scaled by that fit's residual spread. Changing the years changes both the curve and
  the spread, and so every probability.
- **Historical conditions.** A long window averages over whatever happened in it: old harvests, regrowth,
  drought years. A change that happened *before* the window becomes part of normal. A change *inside* the
  window lowers the fitted curve and widens the spread.
- **Recent disturbances.** A recent-only window (B) absorbs 2024–2025 disturbances into normal. It mostly
  stops re-detecting them, which is the interpretability gain Al suggested. But a stand that is recovering
  after a 2024 harvest can then look like an *increase*, and a disturbance that continues or worsens may no
  longer stand out.
- **Number of observations.** B rests on 19 clear Landsat 8 observations per pixel (median), vs 47 for A
  and 66 for C. A two-season fit is more sensitive to one unusual year (weather, phenology, a partial
  disturbance) and to noise.

**Talking points**
- Bottom line: expectation-period choice changes how long detections *persist*. It does not tell us which
  window is more *accurate*; that needs reference data.
- Changing only the expectation window moves 8–18% of pixels to a different class (C and B), and changes
  2026 decrease area from 35.3 km² (A) to 23.9 (C) or 16.3 (B).
- The recent window does what Al suggested for interpretation: decrease area falls 54%, 90% of decreases
  first confirmed in 2024 or earlier drop out, and 90% of those first confirmed in 2026 stay. So B's map is closer to "new since
  2025".
- **Fewer detections is not automatically better.** B changes the question being asked: "different from
  2024–2025" instead of "different from 2018–2023". It rests on about 40% of A's observations, and turns
  some recovering 2024 disturbances into increases.
- The extended window (C) is in between. It keeps 43% of the 2024-or-earlier decreases, because 2024–2025
  partly fold into normal.
- The detection-year product (Slide 2) gives a similar "new vs. earlier" split while keeping the long,
  stable 2018–2023 expectation. That's one argument for answering this in the reporting rather than in the
  expectation, but it's for discussion, not a conclusion.

*Not checked:* none of the three configurations has been compared with reference data. The difference
categories are BULC-D class changes, not verified disturbance or recovery.

---

## Supplement (not a slide): does B isolate 2026 disturbances without losing new ones?

Figures: `figures/supplement_target_year_map.png`, `figures/supplement_target_year_chips.png`.
Script: `scripts/fetch_reference.py` → `scripts/target_year_analysis.py`. Numbers: `data/target_year_numbers.json`.
Read-only: existing A/B outputs plus small display fetches (Sentinel-2 composites, Hansen, LCMS); no BULC-D runs.

**Two kinds of year.** *Detection year* is BULC-D's: the first season it confirmed a decrease. *Independent
evidence* here is Sentinel-2 NBR change, 2025 → 2026 (same-season composites; S2 was disabled in the
pilot runs, which used L8/L9 only), plus Hansen GFC v1.13 (loss through 2025) and LCMS 2025-11 (through
2025). These are spectral evidence and other models, **not verified disturbance years**. Neither product
covers 2026, and nothing has been checked in the field or against a reference sample.

| Group | km² | S2 NBR drop ≥ 0.10 | Notes |
|---|---:|---:|---|
| Retained: A 2026-first, still decrease under B | 8.8 | 90% | Coherent patches; only 8% had Hansen loss 2018–2025 |
| Lost: A 2026-first, not decrease under B | 1.0 | 20% | 81% within 60 m of other decrease; median P(dec) under A 0.79 (retained 0.91); late first detection (median DOY 256, 23% on DOY 276); 34% had Hansen loss 2018–2025 |
| Added: decrease under B only | 0.6 | 42% | 64% within 60 m of other decrease; never decrease under A in any season |
| Stable land (control) | 295 | 2% | |
| A persistent, "2024 or earlier" (B removes 90%) | 17.1 | 8% | Hansen loss 2022–2024: 84%; LCMS loss 2023–2024: 77% |
| A persistent, "2025" (B removes 38%) | 8.4 | 48% | Hansen 2025 loss: 58%; LCMS 2025 loss: 80% |

**Reading**
- *What B removes is mostly real earlier loss.* Hansen and LCMS independently record loss in 2022–2025 on
  most of A's persistent detections. That is the intended effect.
- *What B loses from 2026 is small and mostly weak (1.0 km², 10%).* These are scattered pixels at the edges
  of other detections, marginal under A (P ≈ 0.79), often first crossing late in the season. Only 20% show an
  independent S2 drop, versus 90% for retained detections and 2% for stable land. A third fall in units
  Hansen mapped as 2018–2025 loss, so some are probably older change rather than new 2026 disturbance. About
  0.2 km² has S2 support and could be real 2026 change that B misses; most of it is edge pixels.
- *What B adds is small, partly plausible (0.6 km², 42% S2-supported).* Most of it sits on the edges of 2026
  harvests A also caught, so B mostly extends existing patch boundaries rather than finding new events.
- *Chips (one example per group, not a sample):* the "lost, no S2 drop" example is a landing/road inside an
  older clearing, unchanged between late 2025 and late 2026. The "lost, S2 drop" example is the margin of a
  clearing already present in 2025. The "added" example is the edge of a clear 2026 harvest. The retained
  example is a clear 2026 harvest.

**Tentative answer to the scientific question.** In this pilot, the recent expectation removed most
persistent earlier detections, and independent data say those were real earlier loss. It kept about 90% of
target-year first detections. What it lost and gained were mostly small, weak edge pixels. That supports
"better isolation of target-year change without a large loss of sensitivity" for coherent harvest-scale
disturbance. It's **not established** for subtle, small or late-season disturbances, because the evidence is
spectral, not verified, and comes from one 400 km² area, one year and one land-use regime. It also leaves out
B's other costs (fewer observations; 2024 harvests becoming "increase").

**Open item.** 23% of lost pixels have first_detection_doy = 276 (Oct 3), but the configured season ends
on DOY 273. Worth checking in BULC-D_rebuild how the timing band is recorded; not investigated here.

**To make this a real accuracy assessment (proposed, needs sign-off):**
1. A stratified random sample, e.g. 50–100 pixels each from retained, lost and added and from a 2026
   non-detection stratum. Interpret it against the full S2/Landsat time series and high-resolution imagery
   (NAIP is only through 2022 here, so Planet or Google Earth for 2026), and record an interpreted
   disturbance date for each pixel. That gives errors of omission and commission for A and B in 2026.
2. Optionally, repeat A vs B for 2025 as the target year, where Hansen and LCMS 2025 can serve as an
   independent (model-based) reference across the whole box.
3. Optionally, run the same comparison in a second, non-harvest-dominated area.

---

## Supplement (not a slide): full-year monitoring, 2026 YEAR-TO-DATE

Figures: `figures/supplement_fullyear_comparison.png`, `figures/supplement_fullyear_snow.png`.
Scripts: `scripts/expectation_compare_fullyear.py` (5 live runs, cache in `data/fullyear/`), `scripts/fetch_snow.py`,
`scripts/fullyear_analysis.py`. Numbers: `data/fullyear_numbers.json`. The Jun–Sep results, figures and
Slide 6 are unchanged; no assets written.

**DOY 276 explained.** bulcd bins observations into 4-day windows starting at first_doy (152) and timestamps
each bin with its END date (legacy parity, `bulcd/inputs.py` `_bin_evidence_by_day_step`). The last bin
starts on DOY 272 (Sep 29), covers Sep 29–Oct 2 and is stamped DOY 276 (Oct 3). So "276" = "crossed in the
final bin". The data used ends Oct 2, and every first-detection date is a bin end, up to 4 days after the
observation.

**Methodological concerns (read before the results)**
1. *The expectation window had to change too.* The Jun–Sep expectations would score Jan–May/Oct–Dec
   observations against a harmonic fitted to summer only, which means extrapolation. So expectation AND
   monitoring are both DOY 1–362 here; full-year A/B/C are not the same expectations as Slide 6.
   (last_doy 362 keeps the last bin inside the year; 365 would spill Jan 2026 into B's expectation.)
2. *Detection year was recomputed on a full-year basis* (A for 2024, 2025, 2026 YTD). 0.6 km² moves from
   Jun–Sep "2026" to full-year "2025" (changes between Oct 2025 and May 2026), and 0.6 km² moves the other way.
3. *2026 is year-to-date* (through Oct 27). "Ends as decrease" = as of the latest observation; Nov–Dec
   could change it. The 2024/2025 runs are complete years.
4. *Snow is not masked.* bulcd's L8/L9 mask drops QA bits 0–4 only; the snow flag (bit 5) passes (legacy
   behavior). Snow entering the expectation is the main seasonal risk (below).
5. *Winter data are sparse and noisier* (cloud, low sun, topographic shadow). Full-year A has 100 expectation
   observations per pixel against 47, not 3×; 2026 YTD has 24 monitoring bins against 18.
6. *Evidence is still not verification.* The S2 NBR check compares summers and late seasons, 2025 vs 2026.
   It can't confirm *when* in 2026 a change happened.
7. No exported product exists for the full-year runs to validate against; they use the same code path that
   reproduced the Jun–Sep pilot exactly.

**Results (A = 2018–2023, B = 2024–2025, C = 2018–2025; Jun–Sep → full-year YTD)**

| | Jun–Sep | Full year (YTD) |
|---|---:|---:|
| B removes A's "2024 or earlier" decrease | 90% | 95% |
| B removes A's "2025" decrease | 38% | 23% |
| B retains A's 2026-first decrease | 90% | 93% |
| Lost by B, km² (S2-supported) | 1.0 (20%) | 0.7 (19%) |
| Added by B, km² (S2-supported) | 0.6 (42%) | 1.3 (51%) |
| Decrease km², A / B / C | 35.3 / 16.3 / 23.9 | 34.3 / 17.3 / 25.0 |
| Increase km², A / B / C | 51.7 / 29.5 / 30.3 | 23.7 / 13.9 / 13.7 |
| Same class as A, B / C | 82% / 92% | 88% / 95% |
| Expectation obs per pixel, A / B / C | 47 / 19 / 66 | 100 / 37 / 136 |

- The target-year conclusion holds and is slightly stronger: B removes more of the oldest persistent
  decrease and keeps more of the 2026-first decrease. It adds more, and about half of the added area has S2
  support.
- B removes less of A's "2025" decrease with the full year (23% vs 38%). Full-year "2025" now includes
  Oct–Dec 2025 changes, which B's 2024–2025 expectation has seen only briefly.
- Increase area roughly halves with a full-year expectation. Summer-only fits probably over-call increase;
  not investigated further.

**Seasonal / snow check**
- 2026 had an almost snow-free spring: 0.03% of clear spring observations were snow-flagged, against 13.7%
  (2019), 10.2% (2023) and 6.0% (2024). So **this year can't test snow in the target year.**
- Snow in the *expectation* produces spring false episodes. Under A, the share of land with a spring episode
  that doesn't end as decrease rises from 0.7% (no expectation snow) to 4.2% (> 15% snowy expectation
  observations), and from 0.8% below 300 m to 3.8% above 700 m. That's 6.1 km² in 2026, only 3% with S2
  support. Same mechanism as Pine Mountain: snowy expectation springs raise expected NBR, so a snow-free
  spring looks like a decrease. Supporting it: full-year A for 2025 (snow-poor spring) has 10.7 km² of these;
  for 2024 (snowy spring), 1.8 km².
- B's pattern is flatter, matching its less snowy years, but its total is similar (6.2 km², 11% S2-supported).
  The shorter window doesn't remove spring false episodes overall.
- With the confirmed rule these episodes mostly don't end as decrease, so the 2026 *map* barely changes.
  They would contaminate first-detection dates and episode counts, and an "any crossing" rule would map them.
- Full-year monitoring catches real winter–spring change earlier: 5.2 km² of A's 2026-first decrease first
  crossed in Jan–May, 85% S2-supported (winter and spring harvesting). Whether each crossing date is the
  disturbance or an earlier seasonal crossing is not resolved.

**Possible follow-ups (not run):** mask the Landsat snow flag (bit 5) or the S2 snow class in both periods
and rerun A/B for 2026 (same 5-run cost, about 5 min); a snowier test year or a higher-elevation area to test
snow in the target year; for timing, a sample of Jan–May first crossings checked against dated imagery.
