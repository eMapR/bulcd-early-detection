# Revised figures (v2): can BULC-D isolate 2026 disturbances?

Built from scratch around the research questions. The original six slides and supplements in `../figures/`
are unchanged for comparison. Script: `../scripts/make_figures_v2.py`; numbers: `../data/figures_v2_numbers.json`.

**Consistent basis.** Every BULC-D result uses **full-year** expectation and monitoring (DOY 1–362) for
A 2018–2023, B 2024–2025 and C 2018–2025; 2026 is **year to date** (Jan 1–Oct 27). Detection year comes from
full-year A runs for 2024, 2025 and 2026. No summer-vs-full-year comparison appears.

**Two kinds of date, never mixed.** *Detection date/year* is BULC-D's. *Disturbance date/year* comes from
independent satellite products BULC-D never uses: Hansen Global Forest Change (loss year, through 2025) and
Sentinel-2 NBR change 2025→2026 (S2 was disabled in these runs). Neither is field-verified.

## Story and slide outline

| # | Section | Figure | One takeaway |
|---|---|---|---|
| 1 | The problem | `01_problem_old_disturbance_looks_new.png` | A 2024 harvest still looks like a 2026 disturbance when "normal" is 2018–2023 |
| 2 | How we tested | `02_how_we_tested.png` | Same area and 2026 data, three expectation periods; terms defined |
| 3 | Q1 Large regions | `03_Q1_processing.png` | 400 km² ran in minutes, identical when recomputed |
| 4 | Q2 New vs older | `04_Q2_new_vs_older.png` | Detection year separates them: only 28% of the 2026 decrease is new |
| 5 | Q3 Why the period matters | `05_Q3_why_expectation_matters.png` | A disturbance stops being flagged once "normal" has absorbed it |
| 6 | Q3 Maps | `06_Q3_maps_by_expectation.png` | Older disturbances: 64% of A's 2026 map, 36% of B's |
| 7 | Q4 Earlier disturbances | `07_Q4_older_disturbances.png` | B drops 2022–2024 disturbances, not last year's (2025) |
| 8 | Q5 Missing 2026 | `08_Q5_missing_2026.png` | No sign of missing strong 2026 disturbances: 90 / 93 / 91% detected |
| 9 | Q6 Timing | `09_Q6_timing.png` | Right year about 9 in 10; same month about half, 75% within a month |
| 10 | Q7 Tradeoffs | `10_Q7_tradeoffs.png` | Each period answers a different question; none shown "most accurate" |
| 11 | Open questions | `11_open_questions.png` | No reference-data accuracy yet; proposed next steps |

## Notes per slide

**1. The problem.** One pilot pixel; Hansen records loss in 2024. "Normal" (purple) is learned from
2018–2023; 2024–2025 is a gap neither period uses. In 2026 the observations sit far below normal, so BULC-D
says "decrease", and it would keep doing so in later years. *Say:* this is expected behavior, not a bug; the
question is how to report or avoid it.

**2. How we tested.** Defines expectation period, decrease (≥ 65% confident below normal at the latest
observation), detection date vs disturbance date, and gap. Introduce Hansen and Sentinel-2 as independent
checks here, and say once that they are satellite estimates, not field data. 2026 is year to date;
November–December could change it.

**3. Q1.** Tiles of 10 × 10 km run independently. 12 tile-season exports + 4 detection-year stacks all
succeeded (1–4 min per tile-season). The exported 2026 product recomputed identically on all 443,427 land
pixels; a 1,600-pixel seam spot check matched. *Caveats on the slide:* not yet run beyond 400 km²; islay
validation results not retrieved; exported products are Jun–Sep (the full-year runs were computed on request,
not exported).

**4. Q2.** 34.3 km² flagged as decrease in 2026 under A: 49% first detected 2024 or earlier, 23% in 2025,
28% in 2026. Check against Hansen: 93% of Hansen-2024 land was first detected in 2024; 90% of Hansen-2025 land
in 2025; 94% of new-2026 detections have no earlier Hansen loss. "2024 or earlier" includes older change.

**5. Q3 (mechanism).** Three real pixels, A vs B:
- 2024 harvest: B's normal already includes the cut stand → no change. A → decrease.
- 2025 harvest: B's normal is mostly pre-harvest (2024 + early 2025) → still decrease.
- New 2026: both normals are intact forest → both flag it.
*Key point for disturbances inside the expectation or gap:* a disturbance in the gap is always "new" to
the expectation; one inside it stops being flagged only if enough post-disturbance years are included.

**6. Q3 (maps).** Same three maps, colored by independent disturbance timing. Share of 2026 decrease area:

| | Older 2018–2024 | 2025 | Likely 2026 | No record | Total km² |
|---|---:|---:|---:|---:|---:|
| A | 48% | 16% | 22% | 14% | 34.3 |
| B | 8% | 28% | 44% | 20% | 17.3 |
| C | 34% | 22% | 30% | 15% | 25.0 |

Fewer km² is not the same as more accurate; the "no record" share is unexplained either way.

**7. Q4.** Share of Hansen-disturbed land still flagged in 2026:

| Disturbed | A | B | C |
|---|---:|---:|---:|
| 2018–2021 | 5% | 3% | 3% |
| 2022–2023 | 61% | 1% | 15% |
| 2024 | 96% (gap) | 10% | 85% |
| 2025 | 97% (gap) | 84% (last year of B) | 95% |

Gap disturbances are almost always re-flagged. B removes 2022–2024 disturbances but not 2025 ones, because
its normal has seen little post-2025-harvest data. C barely helps for 2024–2025. Old ones have regrown.

**8. Q5.** Test set: 8.2 km² with a strong S2 drop 2025→2026 and no Hansen loss 2018–2025. Detected: A 90%,
B 93%, C 91%. Flagged area with no independent record: 4.9 / 3.4 / 3.7 km² (false alarms or subtle change,
unknown). *Limit:* only strong, harvest-like 2026 change is tested; subtle or small disturbances are not.

**9. Q6.** Year: 93% / 90% of Hansen 2024 / 2025 disturbances first detected in the same year.
Month (likely 2026 disturbances, expectation A, vs first S2 month with a lasting drop): 47% same month,
28% one month late, 15% 2+ months late, 6% one month early, 4% 2+ months early. The early ones mostly cross in
March–April before a summer change, consistent with seasonal false alarms linked to snowy springs in the
expectation years. B and C are nearly identical. S2 months are bounded by clear-image availability.

**10. Q7.** The tradeoff table pulls numbers from slides 4–9 plus: observations behind normal (100 / 37 / 136
per pixel), regrowing 2018–2023 disturbances shown as "increase" (6% / 20% / 5%), spring false alarms that
later clear (about 6 km² each; they don't reach the map). Summary: A is the most stable but needs detection
year; B best isolates 2026 with no loss of sensitivity in this test but has fewer observations, still flags
last year's, and shows regrowth as increase; C behaves much like A.

**11. Open questions.** Accuracy against reference data; subtle 2026 disturbances; a snowy target year;
other regions and a full ecoregion; whether B's "increase" on regrowth matters to users. Proposed (not
started): a reference sample, 2025 as a target year (Hansen covers it), snow masking, a second region, and a
decision on the reporting rule.

## Not claimed
- No accuracy figures: Hansen and S2 are independent *estimates*, and no field or high-resolution reference
  sample exists yet.
- No recommendation of one expectation period.
- Results are one 400 km² harvest-dominated area, one target year (2026, year to date, nearly snow-free).
