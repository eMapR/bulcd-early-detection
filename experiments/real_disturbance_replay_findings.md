# Real-disturbance replay comparison — harvest vs. fire

2026-09-18. Scripts: `replay_harvest_2025.py`, `replay_fire_2026.py`.
Outputs: `output/harvest_2025_replay.csv`, `output/fire_2026_replay.csv`.

## Terminology used below

- **Acquisition/observation latency** — time from the known disturbance
  timing/window to the first valid post-change satellite observation in
  our evidence stream.
- **Evidence/algorithm latency** — additional valid observations and
  calendar time BULC-D's Bayesian posterior needs to cross the 0.5
  decrease-probability threshold, once post-change evidence starts
  arriving.
- **Operational delivery latency** — delay between satellite acquisition
  and imagery becoming available to a real monitoring pipeline. **Not
  measured here** — both replays query today's archive by acquisition
  date; they say nothing about when each scene was actually processed/
  ingested and queryable in near-real-time on its own date.

## Setup change from the approved config

Before either replay could run, `organize_inputs()`'s harmonic
expectation-model fit hit Earth Engine's "User memory limit exceeded"
for the originally-approved 2-sensor (L8+S2), multi-year (7-8 year, 217
binned Events) expectation baseline — confirmed by isolating just the
fit's R² at a point (fails; independent of `tileScale`, so a
graph-complexity limit inside BULC-D_rebuild's fitting code, not spatial/
raster memory). **With user approval**, both expectation periods were
narrowed to **L8 only** (same year range) to fit within EE's limits.
Target periods (L8+L9+S2) and all shared BULC-D parameters are unchanged
from what was approved. This is an experiment-side scale reduction, not
a BULC-D_rebuild change or an algorithm-parameter tune.

## Headline finding: the raw evidence is immediate; the Bayesian decision is not

**In neither test does `argmax_class` ever flip to "decrease," and
`decrease_probability` never crosses 0.5, anywhere in the observed
window** (through ~2 months after harvest completion / ~2 months after
the fire, as much data as currently exists). This held with the
approved config unchanged - no parameter was adjusted to try to fix or
improve on it.

Yet the raw z-score evidence is unambiguous and essentially immediate in
both cases:

| | Harvest (-121.637, 45.120) | Fire (-118.263, 48.106) |
|---|---|---|
| First valid post-window-start observation | 2025-07-27 (z=-7.97) | 2026-07-19 (z=+0.20, still normal-looking) |
| First valid observation showing clear evidence (z ≈ -10, the pipeline's documented clamp floor) | 2025-07-27 | 2026-07-23 |
| **Acquisition/observation latency** (known event timing → first valid post-change observation) | **2 days** (07-25 start → 07-27) | **2 days** to first post-window observation (07-17 → 07-19), but that one is still evidence-free; **1 day** from the confirmed post-fire date to the first observation actually showing the burn (07-22 → 07-23) |
| Valid post-change observations accumulated in the window, no threshold crossing | 15 | 11 |
| Final `decrease_probability` (last valid observation) | 0.126 (2025-09-29) | 0.283 (2026-09-09) |
| Final `argmax_class` | unchanged | unchanged |

**Sensor/data latency vs. algorithm/evidence-accumulation latency: the
data is not the bottleneck.** Both sites had a valid, cloud-free
observation showing extreme spectral change within 1-2 days of the
known disturbance timing. The 2+ months of *algorithm* latency
(evidence/algorithm latency, as defined above) dwarfs the *acquisition*
latency by roughly two orders of magnitude in both cases.

## Why: the pre-change portion of the same target period builds a
competing prior

This is the opposite of what the B&B Complex Fire plumbing test showed
(crossed 0.5 after only 4 valid observations) - and the difference is
structurally explainable, not a contradiction or a bug:

- The B&B test's target period started in 2004, **after** the 2003
  fire - every target-period z-score was already extreme from the very
  first Event, so the Bayesian fold only ever saw disturbance evidence.
- Both replays here were deliberately configured (per your request) so
  the target period spans well **before** the disturbance too, to see
  the pre-to-post transition. That means the fold spends its first 10-13
  Events (harvest) or 4-6 Events (fire) consuming ordinary "nothing
  changed" evidence, each one (via `dampening_factor=0.5`) nudging the
  running posterior further toward `unchanged` - reaching **~0.95
  unchanged** by the last pre-change observation in the harvest case,
  and **~0.70** in the fire case (fewer valid pre-change observations,
  less time to compound). Once the real disturbance evidence arrives,
  it has to climb out of whatever hole the pre-change portion dug - a
  smaller hole (fire) yields visibly faster movement (0.283 vs. 0.126)
  even with fewer post-change observations and less elapsed time.

This is the same compounding mechanism `docs/findings.md` already
documented for the old multi-decade continuous-stream design ("long
stable baselines can mask real disturbance," 12-year lag on
`year_of_change()`) - but it turns out **not to require decades**. A
single growing season's worth of pre-change "confirm normal" evidence,
folded into the same target period as the disturbance itself, is enough
to produce the same qualitative effect at a much shorter timescale. This
directly contradicts the tentative hope (raised after the B&B plumbing
test) that the restored short-target-period design had sidestepped this
failure mode - it hasn't; it's just less visible when the target period
happens to start after the disturbance, as B&B's did.

`recency_factor` exists specifically to counteract this (`docs/findings.md`,
built for exactly this problem) but was deliberately left at its default
(off) here per your instruction to isolate the effect of accumulating
observations, not new parameter choices. Not tested in this experiment.

## Answers to the requested per-observation markers

Both CSVs carry `phase` (pre_change/disturbance_window/post_change),
`first_valid_post_change_evidence`, `first_argmax_decrease`, and
`first_decrease_crossing` columns. For both sites, `first_argmax_decrease`
and `first_decrease_crossing` are `False` on every row - there is no
crossing to report, which is itself the finding.

**Whether BULC-D detects the change while occurring or only afterward:**
neither, within the observed window - it doesn't cross the decision
threshold at all yet, despite unambiguous raw evidence appearing during
the harvest itself (2 days post-start) and immediately post-fire.

**Effects of masked/cloudy observations:** masked Events are exact
carry-forwards (confirmed again here, same as the B&B test) - they add
calendar-time gaps but don't distort probabilities. The fire site was
notably cloudier (15/31 valid vs. harvest's 25/31), which reduced how
many independent update steps it accumulated in the same elapsed time,
but - counterintuitively - didn't stop it from reaching a *higher*
final probability than the harvest, because its shorter pre-change
portion left it a smaller "unchanged" prior to overcome.

## Implication for later milestones (not designed here)

If a real monitoring system re-derives a fresh target period (with its
own pre-change buffer) for every check, this compounding effect could
recur every time. Carrying forward a persistent, evolving posterior
across checks instead of re-including weeks of "normal" evidence at the
start of every window is a real architectural question for later - not
addressed or designed in this milestone.
