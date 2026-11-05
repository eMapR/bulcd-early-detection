# Sept 30 meeting → what we did → what it shows

Source: `~/Downloads/GMT20260930-174719_Recording.transcript.vtt` (Zoom auto-transcript), 40:45–1:12:00.
The transcript labels several speakers "Peter". Robert is identified by context (John at 45:55: "What ones are you
pointing at, Robert?"; "Robert needs to go to class", 1:10:42). John Boetsch, Natasha Antonova and Al are labeled
correctly. Quotes below are paraphrased from the auto-transcript, which has many errors.

Status vocabulary: **Worked** · **Partly worked** · **Not tested**. None of these mean "accurate". Nothing has been
checked against reference data (field plots, an interpreted sample).

---

## 1. Can BULC-D tell new disturbances from older ones?

| When | Who | What was said |
|---|---|---|
| 40:45–42:08 | Presenter | The 2026 run still flags change that happened in 2025. |
| 42:09–42:40 | John | With normal = years through 2023, anything after 2023 counts as change in 2026, not just 2026. |
| 42:43–42:53 | Presenter | Proposal: **run BULC-D several times to find the first year a change is detected** (approach 1). |
| 53:12–54:12 | Robert | If there's a gap, you can't tell whether 2026 is "weird" because of 2026 or the years in between. |
| 57:04–58:42 | Robert | Done in sequence, 2025 would already have been run. Should 2026 be compared only with the prior year? Problem: a mid-2025 disturbance makes early 2026 look different from early 2025. |
| 1:02:19–1:04:20 | Robert | Proposal: **compare 2026 with each earlier year separately** (2025, 2024, 2023, …) and use the set of scores (approach 2b). |
| 1:05:22–1:08:02 | Al | Likes that: three reference years; flag if different from 3 of 3 or 2 of 3, not 1 of 3. Easier to explain than one long normal period. |
| 1:08:17–1:09:02 | John | The example pixel: 2026 started where 2025 left off. It would be nice to tell new 2026 change apart from 2025 change. |
| 1:09:09–1:09:44 | Natasha | The gap is the issue; comparing 2025 with 2026 probably wouldn't flag it. |

**What we did**

| Approach | Status | Experiment | Result |
|---|---|---|---|
| 1. Multi-year first detection: run each season separately against the same normal period, keep the first season that **ends** as decrease | **Partly worked** | 09-29 independent annual runs (a single continuous run failed: lock-in); 09-30 end-of-season rule; regional pilot detection-year stack; today's breakdown against Hansen/S2 (`data/figures_v7_numbers.json`) | Of the 34.3 km² 2026 decrease (normal 2018–2023), only 9.6 km² is first detected in 2026. That 9.6 km² is 75% 2026 Sentinel-2 decline, 0.08 km² 2025 forest loss, 0.5 km² older loss. It keeps 88% of strong 2026 S2 declines. First-detection year agrees with the Hansen loss year 93% (2024) / 90% (2025). Limits: a detection year, not a disturbance date (Slide S1); "2024 or earlier" can't date older change; 3 runs instead of 1. |
| 2a. Change the normal period (recent B 2024–2025; extended C 2018–2025) | **Partly worked** | A/B/C runs on the pilot (Jun–Sep and full year) | B removes nearly all pre-2025 loss (3% still flagged), but **84% of 2025 loss is still reported as 2026 change**. Its 2026 map is 17.3 km², only 44% of which is 2026 S2 decline. |
| 2a'. Rolling normal (2018–2024 → 2025, 2018–2025 → 2026) | **Partly worked** (little effect) | 09-29/30, testsite + two parks | First-detection maps barely changed. |
| 2b. Compare with each earlier year separately; 2-of-3 vote (Robert, Al) | **Not tested** | — | Proposed for next round. |

**Conclusion supported:** multi-year first detection does the best job of separating 2026 change from 2025 and
older change in this pilot; a recent normal period removes older change but not last year's. Neither has been
checked against reference data.

## 2. How should the expectation ("normal") period be chosen?

| When | Who | What was said |
|---|---|---|
| 49:56–50:30 | Natasha | Why does the normal period end in 2023 if the target is 2026? |
| 55:18–55:33 | John | Why would we want a gap at all? |
| 58:47–59:50 | Natasha | If a disturbance happens inside the normal years, does it change the curve and the result? "So it needs to last more than one year?" |
| 59:57–1:00:43 | Robert / presenter | Picking normal is hard (droughts); a single year like 2018 would catch lots of older harvest. |
| 1:01:49–1:02:19 | Robert | Reference years can be very variable in some systems. |
| 1:02:19–1:08:02 | Robert, Al | Individual previous years instead of one combined period (see 1, approach 2b). |
| 1:11:07–1:12:06 | Al | Some extra output describing the reference years (e.g. "a very dry year") would help explain results. |

**What we did**

| Sub-question | Status | Evidence | What it shows |
|---|---|---|---|
| Gap between normal and monitoring year | **Tested** (A vs C) | A 2018–2023 vs C 2018–2025 | Closing the gap halves older-loss detections (36% → 18% of 2018–2024 loss still flagged), but the most recent loss stays flagged (2025: 95%). |
| Recent years only | **Tested** (B) | B 2024–2025 | Fewer detections (34 → 17 km²); keeps 93% of 2026 declines. But 37 vs 100 clear observations per pixel, and recovering 2024 harvests can show as "increase" (5.5 km², Jun–Sep). Not shown to be more accurate. |
| Disturbance inside the normal period | **Tested** | Share of each Hansen loss year still flagged in 2026 | A loss only stops being flagged when most normal years come after it. Loss in the last normal year is still flagged 84–89% (A 2023, B 2025). One prior year after it is not enough (A 2022: 42%). Natasha's "needs to last more than one year" is right. |
| Individual previous years | **Not tested** | — | Only single-year normals in other experiments (Pine Mountain 2023 → 2024: snowmelt false detection). |
| Reference-year context output (Al) | **Not tested** | — | — |
| Sensors in the normal period (our follow-up, not raised) | **Tested** | North Cascades 09-30 | Landsat-only normal with Sentinel-2 monitoring inflated confirmed detections; consistent sensors cut that class 60–76%. |

## 3. Is BULC-D responding correctly?

| When | Who | What was said |
|---|---|---|
| 43:12–44:57 | Presenter | Probability can jump over the threshold and drop back. Option A keeps it; option B drops it. Can short-lived real change happen (defoliation that recovers)? |
| 45:14–49:40 | Robert, John | 2025 observations well below the fit (about a 20% NBR drop by mid-season) barely moved P(decrease). "I want to make sure there's not something weird with the underlying code." Maybe a parameter gives new observations too little weight. |
| 49:44–53:06 | Robert, presenter | Rebuild or Jeff's libraries? Presenter: about 99% pixel agreement; the transition matrix matters most. |
| 1:00:43–1:01:38 | Robert | The sensitivity must be a knob we can tweak; maybe show Jeff first. |
| 1:05:48–1:06:11 | Al | Doesn't want to test something that may not be right until the sensitivity question is settled. |
| 59:57, 1:03:27, 1:11:07 | Robert, Al | Droughts, dry or wet years: is it change or year-to-year conditions? |
| — | (not raised explicitly) | Validation against independent observations is our follow-up, not a meeting request. The nearest were "make sure the code is right" (46:38) and "show Jeff" (1:01:17). |

**What we did**

| Concern | Status | Evidence | What it shows |
|---|---|---|---|
| Is the code right? | **Worked** (engineering check) | 10-04 / 10-08 GUI equivalence; decision 0011; bulcd.js parity | Exact match with the original BULC-D GUI at decrease, unchanged and increase pixels; the GEE version matches Python to 1e-15. Two input differences were found and fixed in BULC-D_rebuild (S2 scene filter, time axis). |
| Weak response to large NBR drops | **Partly worked** | 09-29 lock-in finding; 10-11 switch to the GUI's defaults | On Sept 30 the posterior leveler was off (1.0). A run of normal observations then pushes P(unchanged) to about 1.000 and decrease evidence barely moves it. The original GUI uses 0.9, which keeps probabilities between about 0.04 and 0.91, so about 3 decrease observations start a detection. The apps have used it since Oct 11. **The exact pixel shown on Sept 30 was not re-run.** Sensitivity was not tuned. |
| Brief jumps that don't last | **Worked** (as a reporting rule) | 09-30 rule A vs B; 10-13 episodes | Counting a season only if it ends as decrease removed 94% of the Apostle Islands detected area, most of it brief crossings. Last detection and the episode count are now reported too. Risk: real short-lived change isn't counted (not tested). |
| Seasonal variation vs real change | **Partly worked** | Pine Mountain (10-13); full-year snow check; NOCA sensors | Snowmelt timing creates false spring detections (Pine Mountain: first detection Apr 17, fire Sep 24). In the pilot, spring false episodes go from 0.7% to 4.2% of land when the normal years were snowy; most don't end as decrease. Drought or wet years: not tested. |
| Independent check | **Partly worked** | Hansen GFC, LCMS, Sentinel-2 comparisons | 90% of strong 2026 S2 declines detected; detection year matches the Hansen loss year about 9 times in 10. These are other models and spectral evidence, **not validation**. No reference sample yet. |

---

## Slide order (figures_v7)

See `README.md` for the deck order. The slides follow the three questions above (disturbance timing,
expectation period, algorithm behavior). They don't repeat the timestamps or the status labels; this document
holds those.
