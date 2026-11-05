# Speaker notes: BULC-D follow-up results

The slides carry only the takeaway. These notes hold what was cut, so you can answer questions. Meeting
timestamps and who raised what are in `MEETING_MAPPING.md`.

**Terms.**
- **Expectation period:** the reference years BULC-D fits as normal conditions.
  - A = 2018–2023
  - B = 2024–2025
  - C = 2018–2025
- **First detection year:** the first monitoring year (2024, 2025 or 2026) that BULC-D confirmed as a decrease,
  meaning the season ended as decrease.
- **Disturbance year:** when the disturbance actually happened. We don't know it for these pixels; the Hansen loss
  year is an independent estimate, not a verified date.

**Data behind slides 2–3.** Oregon Coast Range pilot, 400 km², 30 m.
- BULC-D on Landsat 8/9, full-year monitoring; 2026 runs through Oct 27.
- Water masked, no forest mask.
- Forest loss from Hansen GFC v1.13. "2026 decline" means Sentinel-2 NBR fell by at least 0.2 from late 2025 to
  late 2026, with no Hansen loss in 2018–2025.

---

## 1. Introduction

The three questions came out of the September 30 discussion (recording 40:45–1:12:00). Most results are from the
pilot; the algorithm checks also use earlier test pixels, Apostle Islands, North Cascades and Pine Mountain.

## 2. Disturbance timing: "Tracking first detections helps identify recent changes"

**The problem.** BULC-D asks whether a season differs from the expectation period, not whether something changed
this season. With a 2018–2023 expectation, a 2025 harvest still looks abnormal in 2026, so the single-year 2026
map mixes new and older change.

**The three panels** (same 6 × 6 km window; colors show what other data say about each mapped pixel):

| Approach | Mapped as 2026 change | 2026 S2 decline | 2025 loss | Older loss | Not seen | Strong 2026 declines retained |
|---|---:|---:|---:|---:|---:|---:|
| Single-year run (A) | 34.3 km² | 22% | 16% | 48% | 14% | 90% |
| First-detection tracking (A, runs 2024/25/26) | 9.6 km² | 75% | 0.8% | 6% | 19% | 88% |
| Recent expectation (B) | 17.3 km² | 44% | 28% | 8% | 20% | 93% |

**How first-detection tracking works.**
- 2024, 2025 and 2026 are each run separately against the same expectation.
- Each run starts from the same prior. A single continuous run "locks in" on unchanged and misses later change.
- A pixel's first detection year is the earliest season that ended as decrease. Only pixels whose first detection
  year is 2026 are kept as new.
- It costs one run per monitoring year.

**If asked about accuracy.**
- The first detection year matched the Hansen loss year for 93% of 2024 loss and 90% of 2025 loss.
- Hansen and Sentinel-2 are independent indicators, not verified disturbance years.
- "2024 or earlier" can't date anything older than the first run.

**Detection year ≠ disturbance year.** The supporting slide (`figures/slide1_detection_year_problem.png`) shows
a pixel whose NBR fell between the 2024 and 2025 seasons. It was first confirmed in 2025 and flagged again in 2026.

**Not yet tested.** Comparing 2026 against each previous year individually (2025, 2024, 2023), flagging a pixel
if it differs from 2 of 3.

## 3. Expectation period: "Reference years strongly affect detection"

**Reading the figure.** Each dot shows the share of that year's Hansen forest loss still detected as a decrease in
2026. Shaded years are the expectation period; the last column is the 2026 Sentinel-2 declines.

**Points to make.**
- **Late losses stay detected.** Loss in the last year of an expectation period is still detected: 2023 under A
  (89%), 2025 under B (84%). It takes several later reference years before a disturbance counts as normal; one
  later year isn't enough (2022 under A: 42%).
- **B removes older loss, not 2025 loss.** B drops pre-2024 loss to 1–4% but still flags 84% of 2025 loss.
- **A vs C is not just the gap.** C (2018–2025) halves the detection of 2018–2024 loss compared with A (36% → 18%).
  That's both closing the gap to 2026 and adding two reference years; we can't separate the two.
- **Costs of B.**
  - It rests on about 37 clear observations per pixel, against 100 for A and 136 for C.
  - Some regrowing 2024 harvests show up as increases.
  - Fewer detections don't by themselves mean better accuracy.
- **2026 declines.** All three expectation periods keep about 90% of strong 2026 declines.

**Related.**
- **Monitoring window.** The June–September runs show the same pattern (earlier deck, slide 6).
- **Sensor consistency.** At North Cascades, a Landsat-only expectation with Sentinel-2 monitoring inflated
  detections; using consistent sensors cut that class by 60–76%.
- **Not tested:** individual reference years, and a summary of reference-year conditions (e.g. wet, dry or snowy).

## 4. Algorithm behavior: "Implementation verified; detection accuracy still needs testing"

**Implementation.**
- The Python rebuild exactly reproduces the original BULC-D GUI at three test pixels (decrease, unchanged,
  increase). That covers observed and fitted NBR, residuals, bins and probabilities.
- The Earth Engine version matches Python to about 1e-15.
- Two input differences were found and aligned with the original: the Sentinel-2 scene filter and the time axis.
- This verifies the implementation, not the accuracy of the detections.

**Sensitivity.**
- On September 30 the posterior leveler was off (1.0). After a run of normal observations, P(unchanged) reaches
  about 1.000 and later decrease evidence barely moves it ("lock-in"). That fits the weak response to the 2025 NBR
  drop shown at the meeting.
- The original GUI uses 0.9, which keeps probabilities between about 0.04 and 0.91, so about three low
  observations start a detection. Both apps have used it since October 11.
- **Still open:** the exact pixel from the meeting hasn't been rerun, and the sensitivity itself hasn't been tuned.

**Seasonal effects.**
- **Pine Mountain** (supporting slide `figures/slide3_detection_timing_pine_mountain.png`): with a single-year 2023
  expectation, the 2024 snow-free spring looks like a decrease. The first detection is Apr 17; the fire comes on
  Sep 24.
- **Pilot:** spring false episodes go from 0.7% to 4.2% of land where the expectation years were snowy. Most don't
  end as decrease.
- **End-of-season filtering:** a season only counts if it ends as decrease. At Apostle Islands this removed 94% of
  the detected area, mostly brief crossings. Its cost is that real change which recovers within a season isn't
  counted (not tested).
- Episodes and last detection are now reported, so a false spring episode can be told apart from a later real
  one.

**Accuracy.**
- BULC-D detects 90% of strong 2026 Sentinel-2 declines in the pilot.
- Its first detection year matches the Hansen loss year about 9 times in 10.
- Both are comparisons with other data. No independently interpreted reference sample exists yet.

## 5. Conclusions and next steps

**On the roughly 10% not detected.** BULC-D already captures about 90% of the strong 2026 Sentinel-2 decline area
(90% single-year run, 88% with first-detection tracking, 93% with the recent expectation period). Closing the
remaining gap toward 99% is a research goal, not a result we've shown. The likely places to look:
- late-season declines with few observations before Oct 27;
- edge pixels of larger patches;
- pixels with a noisy (high-SD) expectation.

**Next steps, in more detail.**
1. **Year-by-year comparison:** run 2026 against 2025, 2024 and 2023 separately on the same pilot, and compare it
   with first-detection tracking.
2. **Meeting pixel:** rerun the September 30 pixel with the current configuration.
3. **Reference sample:** a stratified sample (about 50–100 pixels per class: retained, lost, added, and a
   no-detection stratum). Interpret it against the Landsat/Sentinel-2 time series and high-resolution imagery,
   recording an interpreted disturbance date for each pixel. That gives omission, commission and timing errors.
