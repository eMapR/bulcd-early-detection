# Proposal: comparing BULC-D detections with its own Landsat NBR observations

Status: **proposal only. Nothing in this document has been run.**

## Two questions, kept separate

| Comparison | Question | What it is |
|---|---|---|
| **Landsat NBR** (main slides) | Does BULC-D respond appropriately to changes in the observations it processes? | A diagnostic. Same observations, same 30 m grid, same sensors. |
| **Sentinel-2** (appendix) | Do BULC-D detections correspond to declines seen by another satellite? | Supporting evidence from a different sensor. |

Neither comparison is validation. The Landsat comparison is partly circular by design: it checks the algorithm's
behavior given its inputs, not whether those inputs reflect real disturbance.

## What we have, and what's missing

**Already on disk** (`data/fullyear/{A,B,C}26.npz`, `A24`, `A25`), per pixel:
- the final condition and probabilities;
- the first decrease crossing date, episode count and last episode start;
- expectation and monitoring observation counts.

These are BULC-D *outputs*. There are **no Landsat NBR values** for the pilot on disk. `reference.npz` and
`monthly_s2*.npz` are Sentinel-2 composites, and `pixels.json` holds one pixel's time series.

**What we can get without changing BULC-D.** `bulcd.inputs.organize_inputs(config)` is public API, and
`expectation_compare_fullyear.py` already calls it. For the exact configs used in the full-year runs, it returns:
- `target_collection`: the binned Landsat 8/9 NBR BULC-D sees, one image per 4-day bin in 2026;
- `expectation_fitted_collection`: the fitted expectation NBR for each of those bins;
- `expectation_residual_stddev`: the SD that scales each z-score (floored at 0.05);
- `lof_zscore`: the per-bin z-scores BULC-D bins and folds.

So the comparison can use exactly BULC-D's inputs, with no re-implementation. Getting them is a new **read-only**
Earth Engine fetch (`computePixels` in the same 111 × 111 blocks). It doesn't rerun BULC-D, change the algorithm,
or write assets. Per-bin stacks would be large (about 75 bins × 443k pixels), so the per-pixel summaries below
would be computed server-side and only those fetched, about 15 bands per config.

## Proposed method

Run on config **A** (expectation 2018–2023, 2026 full-year monitoring), which is the basis of slide 2. Repeat on
B and C only if A shows something worth comparing.

### 1. Define "substantial Landsat NBR decline" two ways

Each definition answers a different part of the question.

**D1, departure from the expectation** (what BULC-D is supposed to react to):
- **Residual:** r = observed NBR − fitted expectation NBR, per valid 2026 bin.
- **Strong departure:** at least 3 valid bins with r ≤ −0.20.
- **Sustained:** the median r of the last 3 valid bins ≤ −0.20 (still low as of Oct 27).

This tests the Bayesian update, binning and threshold. It says nothing about whether the expectation fit is
appropriate.

**D2, new decline in 2026** (no expectation involved; the Landsat version of the Sentinel-2 class):
- the median NBR of valid 2026 bins after the decline, against the median of valid late-2025 Landsat bins at the
  same pixel;
- a drop of ≥ 0.20, where both have at least 2 valid observations.

The late-2025 values need one extra read-only fetch: the same `organize_inputs` call with a 2025 target period, or
a plain Landsat composite.

**Robustness.** Report both at thresholds of 0.10 / 0.20 / 0.30 and run lengths of 2 / 3 / 4 bins, so the
conclusions don't rest on one cutoff.

### 2. Compare with BULC-D

**Does it respond?**
- Of D1 pixels, the share that end 2026 as decrease, and the share with any decrease episode.
- The lag from the 3rd qualifying bin to the first threshold crossing.

**Does it react to changes that aren't in the data?** Of BULC-D 2026 decreases, the share with no D1 departure.
Low values are expected; high values would point to binning or sensor-mixing artifacts.

**New vs older change.** Of D2 pixels, the share whose first detection year is 2026; of first-detected-2026
pixels, the share that are D2. This is the Landsat counterpart to slide 2's Sentinel-2 numbers.

### 3. Investigate misses (D1 or D2, but no detection)

Stratify the misses by likely mechanism, using fields we either have or would fetch:

| Possible cause | Check |
|---|---|
| Large residual SD shrinks the z-score | Expectation residual SD; z = r / max(SD, 0.05) |
| Too few observations after the decline | Valid bins after the first qualifying bin; decline timing (Sep–Oct declines may be too recent) |
| Decline recovered | Last-3-bin median r |
| Disturbance inside the expectation period | Hansen loss year 2018–2023 at the pixel |
| Snow in the expectation (spring) | `snow.npz` snow fraction; elevation |
| Lock-in | Long run of normal bins before the decline. Should be rare with leveler 0.9, but worth checking. |

Then plot 6–10 rule-selected example pixels (the largest miss patch per cause) with the existing
`pixel.pixel_history` on the product grid: observations, fitted curve and P(decrease). These are the plots Robert
asked about.

### 4. Outputs

- **Main slide.** One map of the 6 × 6 km window: D1/D2 Landsat declines detected vs missed, plus one bar with the
  shares. Slide 2's "88% of strong Sentinel-2 declines" would be replaced by the Landsat figure, and the
  Sentinel-2 version would move to the appendix.
- **Appendix.**
  - the existing Sentinel-2 comparisons;
  - the threshold-sensitivity table;
  - the miss breakdown;
  - the example pixel plots.
- **Data.** A new script, `scripts/landsat_nbr_compare.py`, and a new file, `data/landsat_nbr_{A}.npz`. Existing
  files stay untouched.

## Cost and limits

- **Cost:** one server-side pass per config over the 36 blocks, roughly the cost of the earlier full-year runs
  (minutes, not hours), plus about 20 MB of downloads. No exports and no assets.
- **Circularity:** D1 shares the fitted expectation with BULC-D, so agreement mainly confirms the update logic. D2
  is more informative but still uses the same Landsat observations.
- **Cloud gaps:** Landsat has about 2 clear observations a month here, so D2 can't be computed everywhere. Pixels
  without enough valid observations are reported separately, not counted as misses.
- **Sentinel-2 and Landsat won't agree everywhere.** Differences in resolution and acquisition dates are expected;
  that's the reason for keeping them as separate questions.

## Decision needed

Approve the read-only fetch (config A first), and confirm the two thresholds (0.20 NBR, 3 bins) as the main
definitions.
