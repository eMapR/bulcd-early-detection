# Figures v3: proposed visual approach (for review before any figures are made)

`figures/` (v1) and `figures_v2/` are preserved unchanged. Nothing in this folder is rendered yet.

## What changes from v2

v2 rearranged the same technical charts: maps colored by BULC-D's own detection year, composition
bars, a timing histogram, and several numbers per slide. v3 changes the visual language itself.

1. **One map language for the whole deck.** Every flagged pixel is colored by *independent evidence of
   when the disturbance happened*, never by BULC-D's detection date. There are four colors, the same on
   every slide:
   - **Older disturbance**: forest loss recorded in 2018–2024 (Hansen). Muted blue.
   - **2025 disturbance**: forest loss recorded in 2025 (Hansen). Amber.
   - **New in 2026**: a strong drop in Sentinel-2 imagery between 2025 and 2026, with no earlier loss
     record. Red.
   - **No independent record**: flagged, but neither source shows anything. Dark gray, hatched. This
     could be false alarms or subtle real change; we can't tell which.

   A reader learns this legend once and can then read every map.
2. **Verdicts instead of statistics.** The examples and the A/B/C comparison show answers ("flagged" or
   "not flagged") rather than probability curves or detection-year bars.
3. **Real places.** Image chips and zoomed map windows of actual stands carry the argument. Whole-area
   maps serve only as context.
4. **At most three numbers per slide.** Detailed tables move to an appendix.
5. **Fewer figures (8 plus an appendix)**, each tied to one research question.

## Proposed sequence

| # | Figure | Question | The one thing a reader should see |
|---|---|---|---|
| 1 | Is this a 2026 disturbance? | Core | A stand cut in 2024 is still bare in 2026. A says "new change"; B says "no". |
| 2 | What "normal" means | Q3 setup | A timeline showing which years each version learns from, and where the 2024, 2025 and 2026 disturbances fall relative to that. |
| 3 | Why the answer changes | Q3 | Three real stands, each judged by A and by B: one cut in 2024, one cut in 2025, one disturbed in 2026. |
| 4 | Same place, three answers | Q2–Q4 | A, B and C maps of one zoomed window side by side, in the evidence colors. A is mostly blue, B is mostly red. |
| 5 | Which disturbances get flagged in 2026? | Q4–Q5 | One grid: disturbance age (rows) by A/B/C (columns), filled-circle share flagged. |
| 6 | When does BULC-D notice? | Q6 | One horizontal bar showing BULC-D's first flag compared with the month the drop first appears in Sentinel-2. |
| 7 | Can it run on large regions? | Q1 | Three stat tiles: area, run time, identical result on rerun. |
| 8 | What we learned | Q7 and close | Three columns: learned, still uncertain, what it means for early detection. Plus a short tradeoff row for each of A, B and C. |
| A1–A3 | Appendix | | The full tables, the whole-area maps, and the snow and seasonal checks for anyone who asks. |

### Sketches of the key figures

**Figure 1: the question.** Three real Sentinel-2 image chips of the same stand, from 2023, 2024 and 2026,
in natural color. A caption bar underneath reads: "Cut in 2024. Should a 2026 change map flag it?" Two
verdict badges follow: **A (normal = 2018–2023): FLAGGED as new** and **B (normal = 2024–2025): not
flagged**.

**Figure 2: "normal" timeline (a schematic, not data).**
```
            2018 2019 2020 2021 2022 2023 2024 2025 | 2026
  A          ███████████████████████████            |  watch
  B                                    ██████████   |  watch
  C          ████████████████████████████████████   |  watch
  stands:                              ✂ cut   ✂ cut | ⚠ new
```
The caption reads: "A disturbance looks 'normal' only if the learning years include the time after it."

**Figure 3: three stands, two versions.** The grid has three rows (stands) and two columns (A and B).
Each cell shows a simple greenness line over 2018–2026, with the expected range shaded and a large
verdict:

| Stand | A (2018–2023) | B (2024–2025) |
|---|---|---|
| Cut 2024 | flagged | not flagged |
| Cut 2025 | flagged | still flagged: "normal" has only half-learned it |
| New 2026 | flagged | flagged |

There is no probability axis and no jargon. The 2025 row is the honest twist: even B can't absorb a
disturbance from the last year it learns from.

**Figure 4: the centerpiece.** Three equal map panels (A, B and C) of one zoomed window about 6×6 km,
showing a handful of stands of different ages, colored in the four evidence colors on flat gray land.
Under each panel there is one thin stacked bar of flagged area in the same colors. A small whole-area
locator marks the window. The finding is visible without reading a number: blue fills A's panel and
fades out under B.

**Figure 5: which disturbances get flagged.**
```
                    A     B     C
  2018–2021 loss    ○     ○     ○
  2022–2023 loss    ◕     ○     ◔
  2024 loss         ●     ○     ◕
  2025 loss         ●     ◕     ●
  New in 2026       ●     ●     ●     ← the ones we want
```
(The circles are filled in proportion to the share flagged.) The title reads: "Moving 'normal' forward
stops flagging disturbances from before it, but not ones from its final year." There is one footnote
on "no record" area. It says fewer flags are not the same as more accurate.

## Honesty rules carried over

- "When it happened" always comes from Hansen or Sentinel-2. These are labeled *satellite records*,
  not verified dates.
- "New in 2026" covers strong drops only. Subtle 2026 change is not tested.
- 2026 is year to date (Jan 1–Oct 27) and was nearly snow-free. The results come from one 400 km²
  harvest-dominated area.
- Figure 7's numbers come from the exported Jun–Sep products. The slide says so.
- There is no accuracy claim and no recommended expectation period.

## Needs your OK before building

1. **The evidence-color backbone.** Is it acceptable to class flagged pixels by Hansen and Sentinel-2
   as the primary visual?
2. **One small read-only fetch.** Natural-color Sentinel-2 chips for 2023 (and 2024) of the three
   example stands. This is a few small tiles. Nothing is computed by BULC-D and nothing is written to
   Earth Engine.
3. **Prototype first?** I suggest building Figures 4 and 5 first, so you can judge the direction before
   I make the rest.
