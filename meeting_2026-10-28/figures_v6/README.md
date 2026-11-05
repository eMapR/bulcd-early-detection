# Figures v6: the meeting slides in plain language

Built by `scripts/make_figures_v6.py`.
- It imports every number and map from `make_figures_v5.py` without recomputing them, so the results are
  identical to v5. Only the wording and layout changed.
- `data/figures_v6_numbers.json` is a copy of the v5 numbers.
- Earlier folders are unchanged.

## Slide structure
Each slide has five parts:
1. the research question;
2. a plain-English finding as the title;
3. one figure;
4. one or two sentences of explanation;
5. a short limitation and a one-line source.

Methods and definitions are in appendix A4. Timing details are in appendix A5.

## Terms

| Technical term | Plain wording on the slides |
|---|---|
| Expectation period | The years used to define normal conditions. Introduced on Q1. |
| A / B / C | Normal conditions based on 2018–2023 / 2024–2025 / 2018–2025 |
| 2026 decrease | Vegetation decrease detected in 2026 |
| Historical forest loss flagged | Older forest loss still detected |
| 2026 spectral decline | 2026 vegetation decline in Sentinel-2 imagery. Always "decline", never "disturbance". |
| First threshold crossing | First time BULC-D detected a change |
| No independent record | Not seen in other data |

## Files
- **Main slides:**
  - `Q1_regional_processing.png`
  - `Q2_new_vs_older.png`
  - `Q3_expectation_period_effect.png`
  - `Q4_older_detections.png`
  - `Q5_new_disturbances.png`
  - `Q6_how_quickly.png`
  - `Q7_timing_accuracy.png`
- **Appendix:**
  - A1: per-year table
  - A2: whole-pilot maps
  - A3: alternative map style
  - A4: methods
  - A5: timing details (winter detections, changes visible in late 2025, detections before a change was visible)

## Limitations kept on the main slides
- Q1: only one 100 km² tile was timed.
- Q2: forest-loss years and Sentinel-2 declines are not verified disturbance dates.
- Q4: possible repeat disturbance.
- Q5: strong declines only; about 5% were already visible in late 2025; the area not seen in other data is
  unknown.
- Q6: timing is compared with the month a decline first became visible, not the actual disturbance date;
  there was no comparison with summer-only monitoring; Sep–Oct changes may be too recent.
- Q7: these are first detection dates, which may not persist; the late-2025 changes are left out.
- Every slide: 2026 data through Oct 27.
