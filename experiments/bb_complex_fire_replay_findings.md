# B&B Complex Fire replay — findings

2026-09-18. Script: `replay_bb_complex_fire.py`. Output:
`output/bb_complex_fire_replay.csv`. Plumbing/probability-trajectory
test, not a definitive detection-latency result (see caveat below).

## Setup

Reused `../BULC-D_rebuild/scripts/debug_bb_complex_fire.py`'s config
unmodified: 2003 B&B Complex Fire point (ignited 2003-08-15), Landsat 5,
NBR band, expectation 2000–2003, target configured as 2004–2005.

## What happened

- `last_year` in BULC-D's `SensorEvidenceConfig` is an **exclusive**
  upper bound (`bulcd/inputs.py::_date_bounds`/`_evidence_date_and_doy_bounds`),
  so target `last_year=2005` actually resolved to 2004's growing season
  only (day-of-year 152–273, 4-day bins → 31 Events, 2004-06-04 through
  2004-10-02). Not a bug — matches existing BULC-D_rebuild convention,
  just worth remembering when configuring a target window.
- Of 31 Events, 9 landed a real Landsat 5 scene (`valid=True`); the
  other 22 were no-data bins (cloud cover / no scene) carried forward
  from the prior posterior unchanged — confirms `bulc.run_bulc()`'s
  `unmask(prior)` no-op behavior for gaps holds in practice, not just
  by inspection of the code.
- `decrease_probability` rises **monotonically** across all 9 valid
  observations, from 0.38 (first, 2004-06-04) to 0.70 (last, 2004-10-02)
  — no reversal, no disappearing early signal in this run.
- Crosses the 0.5 threshold at the **4th valid observation**
  (2004-08-07, Event #17 of 31). `bulcd.interpret.first_change_year()`
  (public API) independently agrees: `2004`.
- `argmax_class` is already `"decrease"` from the very **first** Event
  (0.38 vs 0.34 unchanged vs 0.27 increase) — i.e. argmax flips to
  "decrease" immediately, 3 valid observations before the 50%-confidence
  threshold crossing. Argmax and probability-threshold are genuinely
  different signals with different timing.
- Masked (no-data) Events never change the probabilities — they're
  exact carry-forwards of the previous valid step's posterior, visible
  directly in the CSV (e.g. rows 2–4 all repeat row 1's values exactly).

## Caveat — why this isn't a detection-latency answer yet

The target period (2004) starts ~10 months after the fire's Aug 2003
ignition. Every target-period z-score is already extreme (−9.4 to −10,
near the pipeline's effective floor) from the very first observation —
we never see the actual pre-to-post-fire transition, only the
already-post-fire tail continuing to accumulate confidence. To answer
"how soon after a real disturbance does evidence appear" (open question
1) needs a target period that starts *before* a known disturbance and
spans across it — a natural next experiment, not done here.

## Relation to the open questions

1. Not answered by this run (see caveat).
2. Answered qualitatively for the post-fire tail: monotonic increase,
   no plateau/reversal, ~0.38 → ~0.70 over 9 valid observations.
3. 4 valid observations were enough to cross 0.5 in this run — but
   since the signal was already strong at observation 1, this likely
   undercounts what's needed from a genuinely ambiguous starting point.
4. No — probabilities only ever increased in this run; no early
   detections appeared and later vanished.
5. Gaps (22 of 31 Events masked) don't distort the signal, only pause
   it — the trajectory is a step function that only moves on valid
   observations, confirming clouds/gaps delay but don't corrupt timing.
