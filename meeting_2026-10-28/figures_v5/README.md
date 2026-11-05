# Figures v5: the seven meeting slides (final review set)

Built by `scripts/make_figures_v5.py`; the numbers are in `data/figures_v5_numbers.json`. Earlier folders
(`figures/`, `figures_v2/`, `figures_v3/`, `figures_v4/`) are unchanged.

v5 is v4 with Q6 and Q7 rebuilt around detection timing, plus small wording changes to Q1, Q2, Q4 and Q5.
Q3 is unchanged. The basis and class definitions are the same as in `figures_v4/README.md`.

| Q | File | Answer | Title |
|---|---|---|---|
| 1 | `Q1_regional_processing.png` | Partly | One 100 km² tile takes 2–4 minutes; whole-region performance is untested |
| 2 | `Q2_new_vs_older.png` | Partly | BULC-D doesn't label age; a recent "normal" just stops flagging older loss |
| 3 | `Q3_expectation_period_effect.png` | Strong effect | Past loss stays flagged until "normal" includes enough years after it |
| 4 | `Q4_older_disturbances.png` | Mostly yes | Historical loss flagged falls from 36% (A) to 3% (B); 2025 loss: still 84% |
| 5 | `Q5_missing_2026.png` | No evidence of that | All versions flag 90–93% of strong 2026 spectral declines, largely the same |
| 6 | `Q6_how_early.png` | Partly | 87–93% of spring–summer changes flagged within a month; winter ones wait |
| 7 | `Q7_timing.png` | Can't tell yet | ~80% of first flags are within a month of the observed change; 3–4% precede it |

## Timing method (Q6, Q7)

Each 2026 spectral-decline pixel is described by three dates, which are kept separate:

1. **First BULC-D detection.** The first 4-day window in 2026 with P(decrease) > 0.65 (`first_dec`), counted
   whatever the season's final outcome.
2. **First independently observed change.** The first month whose Sentinel-2 monthly burn ratio is at least
   0.25 below the same month a year earlier, and is still at least 0.2 below in the next month. The
   months run from Nov 2025 to Oct 2026.
3. **Actual disturbance date.** Unknown. It lies between the last month Sentinel-2 looks unchanged (within
   0.1 of the year before) and the first changed month. Because these are monthly medians, the window is
   uncertain by about a month.

**Data.**
- `data/monthly_s2.npz` (Jan–Oct 2025 and 2026).
- New: `data/monthly_s2_late.npz` (Nov–Dec 2024 and 2025, plus 2026 clear-observation counts) from
  `scripts/fetch_monthly_s2_late.py`. This is a read-only Earth Engine fetch.
- The clear Landsat dates for Jan–Apr 2026 (Q6 inset) come from an Earth Engine metadata query and are
  listed in the script.

## Results

**When each strong 2026 decline was first visible in Sentinel-2:**

| First visible | Share |
|---|---|
| Nov–Dec 2025 | 4.6% |
| Jan 2026 | 6.2% |
| Feb–Oct 2026 | 85.5% |
| No monthly change found | 3.7% |

The Nov–Dec 2025 group is not 2026 disturbance. BULC-D's 2026 run flags it in March–April (A: 90%), the
same as early-2026 change.

**Q7: first BULC-D detection relative to the observed change** (declines first seen in 2026; values are
A / B / C):

| Category | A / B / C |
|---|---|
| Before any change is seen (possible false early detection) | 3.1 / 3.9 / 2.7% |
| By the month change is first seen | 48 / 50 / 49% |
| 1 month later | 31 / 31 / 31% |
| 2+ months later | 11 / 11 / 11% |
| Not flagged in 2026 | 7 / 5 / 7% |

Flags that come before any change is seen are a median of 2 months early (B: 4).

**Q6: by season of first observed change.**
- **Spring and summer (Mar–Aug).** 87–93% are flagged by the month the change first appears or the
  month after.
- **Jan–Feb.** 93–94% are flagged 2 or more months later, from Mar 16 onward. That is the case even
  though clear Landsat views exist on Jan 19 and Feb 4–5. The reason is not yet explained.
- **Sep–Oct.** 13–16% are not yet flagged by Oct 27.

**Year check (config A only).** Of Hansen 2024 loss, 93% is first flagged in 2024. Of Hansen 2025 loss,
90% is first flagged in 2025.

## Other changes from v4

- **Q1.** The title, subtitle and "Can't tell yet" box now say that one 100 km² tile doesn't establish
  performance across a whole region. The 10,000 km² figures are labeled "100 × this tile (not measured)".
- **Q2.**
  - The flagged-area bars are dropped, so the slide focuses on the maps.
  - Three numbered real stands are added, with what A, B and C do at each:
    - cut in 2024: A and C flag it, B does not;
    - cut in 2025: all three flag it;
    - 2026 spectral decline: all three flag it.
  - The text states that BULC-D doesn't classify disturbance age.
- **Q4.** The title carries both findings: historical loss falls from 36% to 3%, while B still flags 84%
  of 2025 loss. B's 2025 bar is boxed and annotated.
- **Q5.** The title and subtitle say these are strong, independently supported declines, not all genuine
  2026 disturbances. The box adds that about 5% were already visible in Nov–Dec 2025.

## Not claimed

- No timing accuracy. Sentinel-2 and Hansen are estimates, not verified dates.
- No accuracy figure for the no-record area.
- No recommendation of an expectation period.
- Only one 400 km² area, with a nearly snow-free 2026.
