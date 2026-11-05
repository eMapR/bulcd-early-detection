# Figures v7: slides rebuilt around the Sept 30 meeting

Built by `scripts/make_figures_v7.py`. The question → timestamp → experiment → conclusion mapping is in
`MEETING_MAPPING.md`; read it first.

- Organized by the three questions actually raised at 40:45–1:12:00 of the Sept 30 recording, not by our
  earlier Q1–Q7.
- No new BULC-D runs. Every number comes from existing outputs: the full-year A/B/C pilot runs, Hansen, Sentinel-2,
  and `docs/findings.md`. The one new tabulation is the multi-year first-detection breakdown by evidence class,
  in `data/figures_v7_numbers.json`.
- All earlier figures (`figures/`, `figures_v2/`–`figures_v6/`) are unchanged.

## Deck order

| # | File | Content |
|---|---|---|
| 1 | `00_introduction.png` | BULC-D: Follow-up Results; three questions |
| 2 | `01_disturbance_timing.png` | Tracking first detections helps identify recent changes |
| 2s | `../figures/slide1_detection_year_problem.png` | Supporting: first detection year ≠ disturbance year (one pixel, 2024–2026) |
| 3 | `02_expectation_period.png` | Reference years strongly affect detection |
| 4 | `03_algorithm_behavior.png` | Implementation verified; detection accuracy still needs testing |
| 4s | `../figures/slide3_detection_timing_pine_mountain.png` | Supporting: snowmelt produces a first detection months before the fire |
| 5 | `04_findings_next_steps.png` | Conclusions and next steps |

## Terminology used on the slides
- **Expectation period**: the reference years BULC-D fits as normal conditions (A 2018–2023, B 2024–2025, C 2018–2025).
- **First detection year**: the first monitoring year (2024, 2025 or 2026) that BULC-D confirmed as a decrease
  (the season ended as decrease).
- **Disturbance year**: when the disturbance actually happened. It isn't known for these pixels; the Hansen loss
  year is an independent estimate, not a verified date.

The slides keep only the takeaway (about 30–40 words each). Explanations, numbers and limitations for answering
questions are in `SPEAKER_NOTES.md`. Meeting timestamps, speakers and the tested/untested status of each idea are
in `MEETING_MAPPING.md`.

## Basis
Slides 2–3 use the full-year runs (2026 through Oct 27). The supporting slide 2s and the backup `slide2` figure use the
Jun–Sep pilot. Both show about 28% of the 2026 decrease first detected in 2026.
