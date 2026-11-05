# Figures v4: seven slides, one per question (plan, for review before building)

Earlier versions are preserved: `figures/` (v1), `figures_v2/`, and `figures_v3/` (the Figure 4 and 5
prototypes). Nothing in this folder is rendered yet.

## Rules for every slide

- **One question, one visual, one takeaway.** The title is the answer. Each slide also gives a one-line
  answer (**Yes**, **Partly**, **No evidence of that**, or **Can't tell yet**) and one footnote line.
- **A, B and C appear side by side in the same order and colors on every slide.** All runs monitor the
  full year 2026 to date (Jan 1–Oct 27).
- **The same four map colors appear on every map:**
  - **Historical forest loss**: Hansen loss year 2018–2024.
  - **2025 forest loss**: Hansen loss year 2025.
  - **2026 spectral decline**: Sentinel-2 burn ratio fell by at least 0.2 from late 2025 to late 2026,
    with no Hansen loss in 2018–2025.
  - **No independent record**.
- **None of these is called a verified disturbance or a verified date.** "Supports" is the strongest
  verb used.
- **No algorithm explanation slides.** The mechanism appears only where it answers a question (Q3).

## The seven slides

| Q | Question | Answer (current evidence) | Visual | Basis |
|---|---|---|---|---|
| 1 | Can BULC-D process large regions efficiently? | **Partly.** Yes for the summer (Jun–Sep) setup; full-year cost not yet measured. | Three stat tiles: area processed, time, and a byte-identical rerun. A small map of the pilot's tiles. | Existing export records (Jun–Sep). |
| 2 | Can BULC-D distinguish new from older disturbances? | **Yes, if "normal" is recent.** With B, most of the 2026 map is 2026 decline or 2025 loss. With A, half of it is historical loss. | **Improved Figure 4**: the same stands under A, B and C, drawn on Sentinel-2 natural-color imagery. A stacked bar of flagged area sits under each map. | v3 Figure 4. |
| 3 | How does the expectation period affect detection? | **Past loss stops being flagged once "normal" contains mostly the years after it.** | A timeline. One row each for A, B and C across 2018–2026. The normal years are shaded, and above each year a dot shows the share of that year's forest loss still flagged in 2026. | New per-year breakdown of v3 Figure 5 (existing results, no new processing). |
| 4 | Does a shorter, more recent period reduce detections of older disturbances? | **Yes for loss before 2025**: 43% (A) to 12% (B) of historical loss still flagged. **Not for 2025 loss**: 84% under B. | The past-loss half of v3 Figure 5: two rows (historical forest loss, 2025 forest loss) by A/B/C. | v3 Figure 5. |
| 5 | Does changing the period make us miss genuine 2026 disturbances? | **No evidence of that for strong declines**: 90 / 93 / 91% flagged. **Can't tell for subtle change.** | The 2026 half of v3 Figure 5, plus a small map of the 2026 decline each version misses. | v3 Figure 5. |
| 6 | Does full-year monitoring detect disturbances earlier? | **Earlier, yes; whether genuinely earlier, partly.** Under A, the first flag on 2026 declines comes a median of 43 days sooner than with Jun–Sep monitoring, and 55% are flagged before June. | A calendar. Each 2026 decline is a dot at its first-flag date, for full-year and for Jun–Sep monitoring, with the month Sentinel-2 first shows the decline marked. | Existing full-year and Jun–Sep runs (config A only; see decision 2). |
| 7 | How accurately can BULC-D identify when disturbances occurred? | **Year: agrees with Hansen about 9 times in 10. Month: matches Sentinel-2 about half the time and is within one month most of the time. Verified accuracy: can't tell yet.** | Two simple bars: year agreement with Hansen, and month agreement with Sentinel-2 (earlier / same / later). | v2 numbers, redrawn. |

**Improved Figure 4 (Q2).** I'll try two imagery treatments on the zoom window and show you both:
- **(a)** natural-color 2026 Sentinel-2 imagery, with flagged areas drawn as colored outlines;
- **(b)** lightened imagery, with semi-transparent fills.

I expect (a) to read better. I would drop the "no independent record" class from the map and keep it
only in the bar, to reduce clutter. The 2026 imagery is already on disk. If you'd like a 2023 image
inset to show the forest before harvest, I'll fetch it with a small read-only request.

## Appendix (supporting, not presented)

- **A1.** Full table: share flagged by Hansen loss year, 2018–2025, for A, B and C.
- **A2.** Whole-area maps for A, B and C in the four evidence colors.
- **A3.** Example pixel histories (cut 2024, cut 2025, 2026 decline) under A and B.
- **A4.** Snow and seasonal false-detection checks.
- **A5.** Details of the Q6 and Q7 timing comparisons.
- **A6.** Definitions and run settings.
- **A7.** Loss followed by a 2026 decline: about 1.0 km² (possible repeat disturbance, or 2025 harvests
  after the late-2025 comparison image).

## Questions the evidence cannot yet answer (shown on the slides, not hidden)

- **True detection accuracy and dates.** No field or reference disturbance dates exist for 2026, and
  Hansen does not yet cover 2026.
- **Sensitivity to subtle 2026 change** (thinning, insects, drought). Only strong declines are tested.
- **What the "no independent record" area is**: 3–5 km² per version, either false alarms or subtle
  real change.
- **Full-year processing cost** at regional scale. Not yet measured.
- **Snowy years.** 2026 was nearly snow-free, so winter and spring early detection is untested
  under snow.
- **Other landscapes.** One 400 km² harvest-dominated pilot.

## Decisions needed

1. **Q1 full-year cost.** The block run times for the full-year runs were not logged. Options: present
   the Jun–Sep cost and mark full-year as "not yet measured", or time one full-year tile (a small run).
2. **Q6 compares full-year with Jun–Sep monitoring.** You asked earlier for no summer-versus-full-year
   comparison, but Q6 needs one. I'd confine it to this slide. Only config A has stored Jun–Sep
   first-detection dates. Options: show A only (no new processing), or rerun B and C Jun–Sep to get
   their dates (new processing).
3. **Q6 and Q7 may overlap**, since both use Sentinel-2 timing. I'd keep Q6 about *earlier than
   summer-only monitoring* and Q7 about *agreement with independent dates*.
