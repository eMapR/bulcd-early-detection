# Figures v4: seven slides, one per research question

Built by `scripts/make_figures_v4.py`; the numbers are in `data/figures_v4_numbers.json`. Earlier versions are
preserved unchanged: `figures/` (v1), `figures_v2/`, and `figures_v3/` (the prototypes). `PLAN.md` is the agreed
plan.

**Basis for every result**
- **BULC-D runs.** A, B and C each use full-year expectation and full-year monitoring (2026 runs to
  Oct 27). These are the full-year runs in `data/fullyear/`.
- **What counts as flagged.** A pixel is flagged when its 2026 outcome is a decrease (the confirmed rule).
- **What "detection date" means.** The start of the decrease episode that is still standing on Oct 27.
  The date is the end of a 4-day window.

**Map classes.** Each class is independent satellite evidence, not a verified disturbance or a verified
date.

| Class | Evidence |
|---|---|
| Historical forest loss | Hansen loss year 2018–2024 |
| 2025 forest loss | Hansen loss year 2025 |
| 2026 spectral decline | Sentinel-2 burn ratio fell by ≥ 0.2 from late 2025 to late 2026 (Sep 15–Oct 27 composites), with no Hansen loss in 2018–2025 |
| No independent record | All other land |

## Slides

| Q | File | Answer chip | Title (the answer) |
|---|---|---|---|
| 1 | `Q1_regional_processing.png` | Partly | One 10 × 10 km tile takes 2–4 minutes; a longer "normal" costs more |
| 2 | `Q2_new_vs_older.png` | Partly | Past forest loss is 64% of A's 2026 map but 36% of B's; neither removes it all |
| 3 | `Q3_expectation_period_effect.png` | Strong effect | Past loss stays flagged until "normal" includes enough years after it |
| 4 | `Q4_older_disturbances.png` | Mostly yes | B still flags 3% of historical forest loss (A: 36%), but 84% of 2025 loss |
| 5 | `Q5_missing_2026.png` | No evidence of that | Every version flags 90–93% of 2026 spectral declines; mostly the same places |
| 6 | `Q6_how_early.png` | Partly | Half of 2026 spectral declines are flagged by end of May; none before March |
| 7 | `Q7_timing.png` | Can't tell yet | Same month as Sentinel-2 in 43–44% of cases; within one month in 81% |

Each slide has a "Can't tell yet" box naming what the evidence doesn't answer.

## Notes per slide

**Q1.** The benchmark was run on 2026-10-28 with `scripts/bench_fullyear_tile.py`. It exported tile
r0056c0034 for each of A, B and C to a new folder, `regional_bench/fullyear-2026/`. Nothing in `regional/`
or the earlier `regional_bench/bench-*` was touched.

| Version | Compute (EECU-seconds) | Wall time |
|---|---|---|
| A | 510 | 4.4 min |
| B | 172 | 1.6 min |
| C | 618 | 4.4 min |

- **Different outputs.** The exported image is the full-year analysis image (outcome, decrease, increase,
  first detection, episodes and observation counts). The regional products have a slightly different set
  of outputs.
- **10,000 km² estimate.** This is 100 times the one-tile cost: about 14 h for A, 5 h for B and 17 h for C.
  It assumes cost scales with area.
- **Not on the slide.** The Jun–Sep benchmark (`figures/slide5`) is kept separate, as requested. It
  measured the same tile with the regional exporter at 132 EECU-seconds; the two runs differ in both the
  outputs exported and the season covered.

**Q2.**
- **Map window.** The maps show one 6 × 6 km window, picked automatically as the densest mix of the three
  evidence classes. Appendix A2 shows the whole pilot.
- **Background.** Sentinel-2 Jul–Sep 2026, converted to grayscale and lightened, with flagged areas filled.
  I chose this over natural color with outlines (appendix A3) because the filled colors match the legend,
  and bright, uncolored clearcuts are visible as "bare but not flagged".
- **2023 inset.** Uses the new read-only fetch in `scripts/fetch_rgb_2023.py` (`data/rgb_2023_2024.npz`).
- **Answer.** The answer is "Partly". A recent "normal" reduces how much historical forest loss is
  flagged. That is not the same as showing that BULC-D reliably separates new disturbances from old ones.

**Q3.** A circle's area is proportional to the share of that year's Hansen loss that is flagged. Under A,
loss from inside its own final years is still flagged too (2022: 42%, 2023: 89%). The full table is in
appendix A1.

**Q4.**
- **Shares.** Historical forest loss (2018–2024) still flagged: A 36%, B 3%, C 18%. 2025 forest loss still
  flagged: A 97%, B 84%, C 95%.
- **Possible repeat disturbance.** About 1.0 km² per version has a Hansen loss record and also a 2026
  spectral decline. It is counted as past loss.

**Q5.**
- **Shares.** A, B and C flag 90%, 93% and 91% of 2026 spectral declines. 90% are flagged by all three
  versions, 4% by only one or two, and 7% by none.
- **Not tested.** Only strong declines are tested. The no-record area (A 4.9, B 3.4, C 3.7 km²) is not
  scored.

**Q6.**
- **What it measures.** The cumulative share of 2026 spectral declines with a standing detection, by month.
  The dashed line shows the first month the Sentinel-2 monthly median falls below the same month of 2025,
  as a reference.
- **Comparison.** Only A, B and C under full-year monitoring are compared. There is no summer comparison.
- **Detections by May 31:** A 49%, B 50%, C 49%. None are flagged before March. Sentinel-2 shows about 10%
  of declines in January. These may be harvests between Oct 27 and Dec 31, 2025, which BULC-D's 2026 run
  could not flag in January.

**Q7.**
- **Month.** BULC-D's month compared with the Sentinel-2 month. "Same month" is 43–44%; within one month
  is 81–82%. BULC-D tends to be later (+1 month: 31–32%; +2 or more: 15–16%).
- **Year.** Only A has 2024 and 2025 runs. Of Hansen 2024 loss, 93% is first flagged in 2024; of Hansen
  2025 loss, 90% is first flagged in 2025.
- **Wording.** The slide says "agreement with an estimate, not accuracy".

## Appendix
- **A1.** Share flagged by Hansen loss year, 2018–2025, plus the 2026 spectral decline and no-record rows.
- **A2.** Whole-pilot maps in the four evidence colors.
- **A3.** The alternative map treatment (natural color with outlines).
- **Earlier supporting figures, still valid.** The snow and seasonal checks are in
  `figures/supplement_fullyear_snow.png`. Example pixel histories are in
  `figures_v2/05_Q3_why_expectation_matters.png`.

## New data and processing for v4
- **Benchmark.** Three Earth Engine export tasks, written to `regional_bench/fullyear-2026/`.
- **Imagery.** Sentinel-2 natural-color composites for summer 2023 and 2024 (read-only).
- **No changes elsewhere.** The algorithm, the regional products and the earlier results were not
  modified.
