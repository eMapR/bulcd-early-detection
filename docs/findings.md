# Findings

Running, dated record of durable technical/experimental findings for
this project — the "why" behind decisions, kept separate from
`PROJECT_STATE.md` (current status/handoff) and BULC-D_rebuild's own
`docs/findings.md` (that engine's own validation history, not
duplicated here — read it directly when relevant).

## 2026-09-18 — pip re-resolves direct git-URL dependencies on every install

Had `bulcd` been in this project's default `dependencies`, a plain
`pip install -e .` would silently try to re-clone it from GitHub and
overwrite a local editable `bulcd` checkout (confirmed via dry-run and a
real reinstall). Solved by putting it in the `engine` extra instead —
see `README.md` "Relationship to BULC-D_rebuild" for the install
workflow this produces.

## 2026-09-18 — `probability_stack` already contains the progressive-observation trajectory

No custom replay harness is needed to see how BULC-D's confidence
evolves as target-period observations accumulate. `bulc.run_bulc()`'s
`BulcResult.probability_stack` holds one posterior-probability image per
target-period Event, in chronological order — a single
`engine.run_bulcd(config)` call, read via `probability_stack` instead of
only `final_probabilities`, already gives the full progressive-observation
trajectory. Materially simplifies the eventual monitoring architecture:
"watch confidence build up as new observations arrive" is reading
`probability_stack` from one run, not orchestrating repeated BULC-D runs
per cutoff date. See `experiments/replay_bb_complex_fire.py` (plumbing
test against the 2003 B&B Complex Fire point) and
`experiments/bb_complex_fire_replay_findings.md`.

Also discovered: `SensorEvidenceConfig.last_year` is an **exclusive**
upper bound (`bulcd/inputs.py`) — `last_year=2005` with `first_year=2004`
only includes 2004. Relevant to any target/expectation window config.

## 2026-09-18 — Earth Engine "User memory limit exceeded" on multi-year, multi-sensor expectation baselines

`organize_inputs()`'s harmonic expectation-model fit (`_fit_expectation_model`)
alone triggers EE's "User memory limit exceeded" for a 2-sensor (L8+S2),
7-8 year (217 binned Events) expectation baseline — isolated by testing
just `expectation_r2.reduceRegion()` in isolation (fails; independent of
`tileScale`, so a graph-complexity limit inside BULC-D_rebuild's fitting
code, not spatial/raster memory). Worked around on our side by narrowing
to L8-only expectation (same years) — not a BULC-D_rebuild change.
Relevant to any future replay using a multi-year, multi-sensor
expectation period; the validated B&B test's baseline (4 years, single
sensor, ~124 bins) is well under whatever this limit is.

## 2026-09-18 — Real-disturbance replays: algorithm latency dwarfs data latency; neither site crosses the decision threshold

Two real, independently-dated disturbances (2025 clearcut/harvest,
2026 fire with unknown exact date) replayed with target periods spanning
before/during/after each event. See `experiments/replay_harvest_2025.py`,
`experiments/replay_fire_2026.py`, `experiments/output/`,
`experiments/real_disturbance_replay_findings.md` for full detail.

**Both sites had a valid, cloud-free observation showing extreme z-score
change (the pipeline's documented ±10 clamp) within 1-2 days of the
known disturbance timing** — acquisition/observation latency is a
non-issue at both sites.

**But at `recency_factor=1.0` (classic/off), neither site's
`decrease_probability` ever exceeds 0.5, nor does `argmax_class` ever
flip to "decrease,"** through ~2 months of post-change data (harvest
reaches only 0.126 by its last valid post-change observation; fire only
0.283).

**Mechanism:** both target periods were deliberately configured to
include a pre-change portion (to see the transition). The Bayesian fold
spends its first several Events consuming ordinary "nothing changed"
evidence, building a strong `unchanged` prior (~0.95 for harvest's 10
valid pre-change Events, ~0.70 for fire's 4-6) before the real
disturbance evidence arrives. This is the same "long stable baseline
masks real disturbance" compounding effect BULC-D_rebuild's own
`docs/findings.md` documented for the old multi-decade design — now
shown to occur **within a single growing season**. This contradicts the
tentative hope (after the B&B plumbing test, which crossed after only 4
valid observations) that the short-target-period redesign had
sidestepped this failure mode — it hadn't; B&B's target period just
happened to start *after* its fire, so its fold never saw a pre-change
portion at all.

## 2026-09-18 — `recency_factor` sweep: real effect, but non-monotonic, and doesn't fully fix either site

Tested `recency_factor` (`bulcd/bulc.py`'s `discount()`,
`docs/decisions/0005-recency-weighting-extension.md`) at
1.00/0.95/0.90/0.85/0.80 against the exact same two sites/configs above —
**only `recency_factor` changed**, nothing else tuned. See
`experiments/replay_recency_sweep.py`,
`experiments/output/recency_sweep_comparison.csv`, and the per-run CSVs
(`experiments/output/{site}_recency_{gamma}.csv`).

| site | gamma | crossed 0.5? | valid post-change obs before crossing | crossing date | days since known disturbance¹ | max decrease_probability² | false decrease>0.5 pre-change? |
|---|---|---|---|---|---|---|---|
| harvest | 1.00 | no | — | — | — | 0.126 | no |
| harvest | 0.95 | no | — | — | — | 0.448 | no |
| harvest | 0.90 | **yes** | 13 | 2025-09-21 | +58d | 0.550 | no |
| harvest | 0.85 | **yes** | 12 | 2025-09-17 | +54d | 0.542 | no |
| harvest | 0.80 | **yes** | 14 | 2025-09-25 | +62d | 0.508 | no |
| fire | 1.00 | no | — | — | — | 0.283 | no |
| fire | 0.95 | no | — | — | — | 0.432 | no |
| fire | 0.90 | no | — | — | — | 0.491 | no |
| fire | 0.85 | no | — | — | — | 0.497 | no |
| fire | 0.80 | no | — | — | — | 0.482 | no |

¹ Harvest measured from the observed harvest onset (2025-07-25); fire
measured from the known confirmed-post-fire date (2026-07-22), not an
invented ignition date — the true fire date is somewhere in
2026-07-17–22, so this is a conservative (lower-bound) latency estimate.
² At `gamma=1.0` the naive whole-run maximum is a pre-change artifact
(the very first Event, before any evidence has accumulated either way —
harvest 0.284 on 2025-06-05, fire 0.300 on 2026-06-05); the genuine
post-change maximum at `gamma=1.0` is 0.126 (harvest) / 0.283 (fire), as
shown above. At every `gamma<1.0` the maximum occurs at the last valid
observation in both cases — the trajectory hadn't peaked/plateaued
within the available data.

**Unexpected result #1 — `recency_factor` helps, but does not fully fix
either site.** Harvest crosses 0.5 at three of the four tested values;
fire never crosses at any tested value, up to and including the most
aggressive (0.80).

**Unexpected result #2 — the effect is non-monotonic in `gamma` for the
0.5-probability crossing, at both sites.** For harvest, `0.85` crosses
*soonest* (2025-09-17, 54 days), `0.90` crosses next (58 days), and
`0.80` — the most aggressive forgetting tested — crosses *last* (62
days) and reaches the *lowest* peak probability (0.508) of the three
crossing runs. Fire shows the same shape in its (non-crossing) peak
probability: `0.85` (0.497) > `0.90` (0.491) > `0.80` (0.482). Neither
site got monotonically "better" as forgetting increased.

**Why (mechanistic, not a bug):** `discount()` (`posterior^gamma /
Σ(posterior^gamma)`) is applied to *every* Event, uniformly — it doesn't
distinguish "old wrong evidence" from "recent correct evidence." Once
the disturbance evidence has started winning, the same mechanism that
helped the posterior escape the `unchanged` trap keeps flattening the
newly-accumulating `decrease` confidence on every subsequent step too.
Very aggressive forgetting (`0.80`) escapes the trap faster but then
also caps how much confidence can build once escaped — producing a real
trade-off/sweet-spot around `gamma≈0.85` for these two sites, rather than
"smaller gamma is always better." Contrast with `argmax_class`'s first
flip to "decrease" (an easier bar — just `decrease > unchanged`, not
`decrease > 0.5`), which *is* monotonic in `gamma` at both sites (harvest:
2025-09-17→09-01→08-24 as gamma goes 0.90→0.85→0.80; fire: 2026-09-01→
08-24→08-20) — the two decision criteria respond differently to the same
parameter.

**Why fire never crosses even at `gamma=0.80`:** fire has fewer valid
Events overall (15 vs. harvest's 25) and is cloudier (16/31 masked vs.
harvest's 6/31). `discount()` is a no-op on masked/no-data Events (it's
applied to the posterior before the `.unmask(prior)` revert in
`bulc.py`'s `_step()`, so a masked step's discount is discarded along
with the rest of that step's would-be update) — fewer valid Events means
fewer chances for the geometric decay to compound, regardless of `gamma`.
Fire's smaller pre-change "unchanged" prior (~0.70 vs. harvest's ~0.95)
made intuitive sense as an *easier* climb, but that advantage was offset
by having fewer post-change Events to climb it in.

**No other parameter was changed or tuned based on these results,** per
instruction — this is reported as-is.

## 2026-09-18 — Traced mechanism: why fire never crosses 0.5, and what "extreme z-score" actually buys you

Investigated *why* by reconstructing the fire replay's per-step Bayesian
update from its components — transition-matrix bin lookup →
`dampen()` (pre-update) → `bayes_update()` → `dampen()` (posterior_leveler)
→ `discount()` (recency) — using BULC-D_rebuild's own real functions
called directly per step (not a from-scratch reimplementation). Every
reconstructed step matched the real `probability_stack` value exactly
(max delta < 1e-6) at both `gamma=1.0` and `gamma=0.85`, confirming the
trace is faithful. See `experiments/trace_fire_recency_mechanism.py`.

**Central finding: the z-score's "extremeness" beyond the first bin
boundary buys zero additional Bayesian evidence.** `bin_cuts`'s most
extreme cut is `-2`; every z-score below it — whether `-2.01` or the
pipeline's own documented clamp floor `-10` — falls into the same bin 1
and gets the exact same transition-matrix row, `[decrease=0.16,
unchanged=0.11, increase=0.02]`. Every valid post-fire observation in
this dataset happened to land at the clamp (`z=-10`), so every single
one contributed *identically weak* evidence: a 1.45:1 raw decrease:unchanged
odds ratio — not the overwhelming evidence "z=-10" sounds like. After
`dampening_factor=0.5` (applied to the update factors *before*
`bayes_update()`), that ratio compresses further to `[0.247, 0.222,
0.177]` — roughly **1.11:1**, barely above a coin flip. This is the
distinction between "extreme spectral evidence" (the z-score/NBR
change itself, genuinely dramatic) and "extreme Bayesian evidence" (what
actually reaches `bayes_update()`, quite modest) — the pipeline's
binning + dampening layer discards almost all of the z-score's own
magnitude information once it's past the outermost bin cut.

**Why repeated extreme observations still accumulate (slowly), not at
all, or reverse:** each bin-1 Event nudges the posterior by only that
modest ~1.11:1 ratio, so `decrease_probability` climbs by roughly
0.02–0.045 per valid Event (`gamma=1.0`) — accumulation happens, but it
takes many repeated Events to overcome whatever prior came before, and
fire's target period only ever supplies 11 valid post-window Events
(through the data currently available). At `gamma=0.85`, the traced
per-step *increments* themselves shrink over the run (+0.045, +0.042,
+0.038, ... +0.016) — not because the evidence weakened, but because
`discount()` (`p^gamma/Σp^gamma`) pulls *every* class toward uniform
(1/3) every step, and it pulls harder on whichever class currently
deviates most from uniform. Once `decrease` becomes the largest class
(crosses ~1/3, around 2026-08-12 in this run), `discount()` starts
actively pulling it back down every step, fighting the next
`bayes_update()`'s gain — the same mechanism that helped `decrease`
escape the `unchanged` trap early on works against it once it's ahead.
**`decrease_probability=0.497` on 2026-09-09 is NOT a peak or plateau —
it is simply the last valid Event in the data currently available; the
trajectory was still rising every step up to that point.** (Correction
to this file's recency-sweep entry above, which described it as
"peaks around 0.497" — that comparison was accurate across gamma values
at a fixed calendar cutoff, but shouldn't be read as this run having
leveled off in time.) Whether it would cross 0.5 given more data is
genuinely open — the per-step gain is shrinking, but it's already at
the threshold.

**`posterior_leveler` (default 1.0) is confirmed to be an exact no-op**
in this trace — `post-bayes` and `post-leveler` columns are identical on
every row, matching `dampen()`'s documented `leveler=1.0` identity case.

**Harvest vs. fire — why harvest crosses and fire doesn't:** both sites
use the identical matrix/bin-1 row and the same weak ~1.11:1
post-dampening ratio for their (also z≈-10) evidence. The difference
isn't evidence strength — it's **repetition count**. Fire actually had
a *smaller* pre-change deficit to climb out of (`unchanged` reached only
0.780 right before its first burn evidence, vs. harvest's 0.947 — even
weaker than previously estimated, since the uncertain-window's own
2026-07-19 non-evidence observation added one more "confirm normal"
step before the real fire evidence started). Despite starting from a
harder position, harvest still crosses, because it gets **15 valid
post-change Events** to apply the same modest per-step gain, vs. fire's
**11** — about 36% more repetitions. This refines last entry's
"smaller deficit should mean an easier climb" framing: deficit size
mattered less than how many valid observations were available to work
against it.

**No BULC-D_rebuild code or configuration was changed to produce or
interpret this trace** — `experiments/trace_fire_recency_mechanism.py`
calls BULC-D_rebuild's real functions (including two underscore-prefixed
`engine.py` helpers, used read-only for introspection) with the exact
approved config's constants.

## 2026-09-18 — Provenance investigation: the matrix we've been using is an illustrative example, not production

Investigated the bin_cuts/transition-matrix/dampening_factor choices
our experiments have inherited, entirely by reading BULC-D_rebuild's own
`CLAUDE.md`, `docs/findings.md`, `docs/decisions/`, and `configs/`
(no legacy PDFs needed — this was already thoroughly documented there).
**No BULC-D_rebuild code or config was changed; no new matrix designed.**

**1-2. bin_cuts and the z→bin mapping.** `bin_cuts=[-2,-1.5,-1,-0.5,0,
0.5,1,1.5,2]` (9 cuts, 10 bins) — confirmed by BULC-D_rebuild's own
research to match `guiBULCD.rtf`'s hardcoded `binCuts` (line 5965), the
**real legacy production value**, not invented for this rebuild.
`_bin_zscore()`'s `.gt(cut)` chain (strict `>`) means: bin 1 = `z ≤ -2`,
bin 2 = `-2 < z ≤ -1.5`, ..., bin 9 = `1.5 < z ≤ 2`, bin 10 = `z > 2`.
Bins 5-6 sit within ±1σ ("no change"); 1-4 are increasingly large drops
(1 = most extreme); 7-10 are increasingly large increases (10 = most
extreme).

**3-4. Willis NBR12 matrix provenance — hand-picked, not empirical.**
The matrix every one of our experiments has used so far (`NBR12_TRANSITION_MATRIX`
in our scripts) is Willis (2022)'s **own worked illustrative example**
for the thesis, transcribed verbatim — explicitly **not** the real
production matrix (BULC-D_rebuild's `CLAUDE.md` says so directly: "not
the shipped default, but a concrete, correctly-shaped real one"). Its
rows don't sum to 1 (0.16+0.11+0.02=0.29, etc.) — BULC-D_rebuild's own
docs state plainly these are "hand-picked likelihood weights, not
empirical proportions," explicitly contrasted against classic BULC's
normal data-derived (confusion-matrix) update table. This directly
answers Q4: **hand-tuned/illustrative, not empirically derived or
independently published/validated.**

**Major finding — a REAL production matrix already exists in this
codebase, and it's very different.** `../BULC-D_rebuild/configs/cell_8c_comparison.yaml`
contains a transition matrix **read live from the actual legacy GUI's
own Console output** (`docs/findings.md`'s "Real production BULC-D
parameters" entry, 2026-08-10) — genuinely different numbers, rows that
sum to ~0.98-0.99 (real conditional probabilities, not hand-picked
weights):

| bin | Willis (illustrative, used in all our runs) | Production (real GUI, cell 8C) |
|---|---|---|
| 1 (most extreme decrease) | `[0.16, 0.11, 0.02]` | `[0.83, 0.08, 0.08]` |
| 2 | `[0.14, 0.07, 0.02]` | `[0.66, 0.24, 0.08]` |
| 3 | `[0.07, 0.12, 0.02]` | `[0.53, 0.37, 0.08]` |
| 4 | `[0.03, 0.16, 0.02]` | `[0.14, 0.76, 0.08]` |
| 5-6 (no change) | `[0.015, 0.2, 0.01]` / `[0.015,0.195,0.025]` | `[0.08, 0.83, 0.08]` (both) |
| 10 (most extreme increase) | `[0.02, 0.02, 0.08]` | `[0.08, 0.08, 0.83]` |

**Quantified effect at the most extreme decrease bin (bin 1)** — raw
decrease:unchanged odds, then after `dampening_factor=0.5`:

| matrix | raw ratio | after `d=0.5` |
|---|---|---|
| Willis (used in our experiments) | 1.45:1 | **1.11:1** (barely above a coin flip) |
| Production (real GUI) | **10.38:1** | **2.81:1** |

This is the answer to Q8 and to the investigation's central question.
**Our "weak accumulation, fire never crosses 0.5" finding from the last
two entries is very likely substantially an artifact of using Willis's
illustrative thesis example, not a fundamental property of BULC-D's
design.** The real production matrix gives the most extreme bin roughly
9x stronger raw evidence and 2.5x stronger post-dampening evidence than
what all our replays have been running against. Full per-bin dampened
comparison (both matrices, all 10 bins) is in
`experiments/output/` (computed inline, not saved as a script — see
this entry's own numbers above for the load-bearing bin).

Also notable: Willis's own matrix is **not monotonic by extremity** on
the decrease side — bin 1's raw ratio (1.45) is actually *weaker* than
bin 2's (2.00), an internal irregularity. Production's matrix has no
such quirk (10.38 → 2.75 → 1.43 → ..., cleanly monotonic) — another
signal that Willis's numbers are a rough illustrative example, not a
carefully bin-by-bin-calibrated set.

No BAI transition matrix values were found transcribed anywhere in
BULC-D_rebuild's repo (`CLAUDE.md`/`docs/`/`configs/`) — only that Willis's
thesis has one, described as differently-shaped (BAI inverts NBR12's
sign convention). Not available for direct comparison without reading
the thesis PDF itself, which wasn't necessary for the findings above.

**5. Was collapsing every z ≤ -2 into one bin intentional?** Yes, as far
as the binning structure itself goes — `guiBULCD.rtf`'s real hardcoded
cutoffs, not a rebuild invention (see #1-2 above). Discretizing a
continuous z-score into a small number of bins is inherent to how
BULC-D's transition-matrix mechanism works at all (a fixed, small lookup
table can't have infinite resolution) — this is a structural property of
the *method*, not a bug or a rebuild-side choice. What's NOT confirmed
intentional is that bin 1 (Willis's version) happens to give *weaker*
relative evidence than bin 2 — that looks like an artifact of a rough
illustrative example, not a deliberate "don't fully trust the most
extreme case" design choice (see the non-monotonicity point above, and
contrast with production's clean monotonicity).

**6-7. `dampening_factor` provenance and quantified effect.** Cardille &
Fortin (2016) section 4.6 — `dampened = d·raw + (1-d)/n_classes`, their
own tested value `d=0.5`, documented purpose (per BULC-D_rebuild's
`CLAUDE.md`): "used when classifications agree suspiciously well and you
don't want to overreact to any single Event." `docs/decisions/0004` adds
this rebuild's own validation: `d=1.0` (off) produced ~48 orders of
magnitude overconfidence over many sequential Events at one real test
pixel — `d=0.5` was adopted to fix that, not chosen for its effect on
any single bin. Quantified per-bin effect: `dampen()` is a fixed linear
pull toward uniform (1/3 each class) — at `d=0.5` it roughly halves how
far any single row's probabilities sit from uniform (see the two full
per-bin tables above: e.g. production bin 1's 10.38:1 raw ratio becomes
2.81:1, bin 4's 0.18:1 becomes a less extreme 0.43:1). It compresses
*every* row proportionally, including the strongest/most extreme ones —
consistent with its documented purpose (guard against ANY single Event
dominating), not something targeted at extreme-decrease evidence
specifically.

**9. Documented rationale for limiting a single extreme observation's
influence?** Yes, on two independent, separately-documented levels:
`dampening_factor` (above) is explicitly motivated by robustness to
over-reacting to a single classification/Event, per Cardille & Fortin's
own paper. Separately, BULC-D_rebuild's `CLAUDE.md` describes bin 10 (the
most extreme *increase* bin) as "a catch-all for atmospheric-interference
outliers, weighted low so it doesn't dominate" per Willis's thesis — an
explicit, named rationale (transient atmospheric/sensor artifacts
mimicking regrowth) for suppressing that specific bin's influence. No
equivalent documented rationale was found for symmetrically suppressing
the most extreme *decrease* bin (bin 1) — if anything, production's real
matrix treats bin 1 as its *strongest* signal (0.83, the single largest
value anywhere in the matrix), the opposite of a "distrust extreme
drops" design choice.

**Bottom line — answering the investigation's central question:** the
*binning structure* (10 bins, `±2σ` outer cutoffs, discretization
itself) and the *general dampening mechanism* (robustness to
single-Event overconfidence) are both confirmed intentional, sourced
design characteristics of original BULC-D. But the **specific matrix
values** every one of our experiments has used are an illustrative
thesis example, not production-calibrated ones — and BULC-D_rebuild's
own repo already contains a real production matrix that behaves very
differently at the extreme-decrease bin our fire/harvest cases actually
land in. This reframes the last two entries' findings: "BULC-D doesn't
accumulate confidence from extreme evidence" may be substantially a
property of *which matrix we happened to use*, not of BULC-D itself.
Per instruction, no matrix was changed or newly designed here — this is
provenance/establishment only.

## 2026-09-19 — Production-matrix baseline: both sites cross cleanly, no recency weighting needed

Confirms the previous entry's hypothesis directly. Reran the exact same
harvest/fire replays with **only** `custom_transition_matrix` swapped
from Willis's illustrative example to the real production matrix
(`../BULC-D_rebuild/configs/cell_8c_comparison.yaml`, transcribed
verbatim in `experiments/replay_production_matrix.py`) and
`recency_factor=1.0` (off) — everything else (AOI, expectation/target
periods, sensors, DOY window, `bin_cuts`, `dampening_factor=0.5`,
`posterior_leveler`, 0.5 interpretation threshold) identical to every
prior replay. See `experiments/output/harvest_2025_production_matrix.csv`,
`fire_2026_production_matrix.csv`.

| site | matrix | crosses 0.5? | valid post-change obs to cross | crossing date | days since known disturbance¹ | max decrease_probability | false positive pre-change? |
|---|---|---|---|---|---|---|---|
| harvest | Willis (`gamma=1.0`) | no | — | — | — | 0.126 | no |
| harvest | **Production** (`gamma=1.0`) | **yes** | **9** | 2025-09-01 | **+38d** | **0.999** | no |
| fire | Willis (`gamma=1.0`) | no | — | — | — | 0.283 | no |
| fire | **Production** (`gamma=1.0`) | **yes** | **6** | 2026-08-12 | **+21d** | **0.998** | no |

¹ Same reference dates as the recency-sweep entry: harvest from the
observed onset (2025-07-25); fire from the known confirmed-post-fire
date (2026-07-22) — still not an invented ignition date.

**First valid post-change observation and z-score (identical across
matrices — z-score computation doesn't depend on the transition
matrix):** harvest 2025-07-27 (z=-7.97); fire 2026-07-19 (z=+0.20, still
normal-looking — the first observation actually *showing* burn evidence
is 2026-07-23, z=-10, same as previously found).

**Both sites reach near-certainty (>0.99) by the end of the currently
available data**, and — unlike every Willis-matrix run — `argmax_class`
and the 0.5-probability crossing now happen at the **exact same
observation** in both cases (production's bin-1 evidence is strong
enough to jump straight past 0.5 in one step once it starts to
dominate, rather than the slow multi-Event creep through the 0.33-0.5
range seen with Willis's matrix).

**Quantifying how much of the earlier slow response was matrix choice:
effectively all of it, for these two cases.** Holding `recency_factor=1.0`
fixed and changing only the matrix took harvest from "never crosses,
max 0.126" to "crosses in 9 observations, reaches 0.999," and fire from
"never crosses, max 0.283" to "crosses in 6 observations, reaches
0.998" — with **no recency-weighting extension needed at all**. This
directly answers the question that motivated the whole investigation:
the earlier "BULC-D doesn't accumulate confidence from extreme evidence"
finding was not a fundamental property of the algorithm — it was
predominantly an artifact of testing against Willis's thesis
illustration instead of BULC-D's real production evidence model.

**One minor data-freshness note, not a methodology issue:** this run
(2026-09-19) picked up one additional valid fire observation
(2026-09-13) that wasn't yet archived when the Willis-matrix fire
baseline was run (2026-09-18) — 16 valid Events here vs. 15 previously.
The extra observation arrives well after production's crossing point
(observation #18 of 31) and doesn't affect any number in the comparison
above.

**No `recency_factor` sweep was run against the production matrix in
this entry**, per instruction — that's the natural next step once this
baseline is established.

## 2026-09-20 — Matrix provenance confirmed against real legacy source; first spatial validation

Two-part investigation, nothing tuned or changed based on results.

### Part 1: the "production" matrix traced to the actual legacy GEE source

Previously (2026-09-18 entry) the production matrix's provenance was
established via a *Console dump* captured from a live GUI session
(`../BULC-D_rebuild/docs/findings.md`'s "Real production BULC-D
parameters"). That leaves open exactly the question this session raised:
was that Console dump a one-off value the analyst typed in for cell 8C,
or the app's actual built-in default? Traced further, into
`../BULC-D_rebuild/legacy/6003.3c-BULC-AdvancedParameters.txt` — a real
legacy GEE **source file** (not a captured dump), version `r2903-V2.4`,
whose `getBULCParameterDictionary()` function is literally what supplies
`customTransitionMatrix` to every real run of the app that uses
`overlayApproach === "C"` (custom matrix mode).

**The active (uncommented) matrix in that source file, lines 142-153, is
byte-for-byte identical to what we've been calling "the production
matrix."** This confirms it is not a per-analyst, per-study parameter —
it is the shared, hardcoded default the real legacy app's own source
code supplies to every custom-matrix run of that app version.

**The source file's own comments give real provenance/rationale**
(dated, first-person, confirms several things this project could
previously only infer):
- Earlier matrix versions (commented out, lines 99-130) had much lower
  absolute magnitudes and were found to produce "dampened in the
  extreme" numbers downstream — the June-2024 rewrite explicitly
  rescaled rows to sum to ~1 to fix this, not for any reason related to
  extreme-decrease evidence specifically.
- **Direct confirmation of Q9's rationale** (from the 2026-09-18 entry):
  "The main effect is to make bin 10 more powerful. I feel I can do this
  because the cloud masks are better, so clouds are not errantly
  included as often, so bin 10 can be used as real data." — bin 10 (most
  extreme increase/outlier bin) was historically suppressed
  *specifically* because of cloud-masking quality concerns, and that
  suppression was deliberately relaxed once cloud masking improved. This
  is the real author's own stated reasoning, not inference.
- The matrix superseded by the current one (lines 155-166, "until June 4
  2024") had bin 10 = `[0.11, 0.37, 0.53]` — barely more extreme than a
  mid-range bin, consistent with deliberate historical distrust of that
  bin, now corrected.
- The file also independently corroborates the three real production
  levelers already known from the Console dump: `initializingLeveler=0.7,
  transitionLeveler=0.7, posteriorLeveler=0.9` — cross-validates the
  earlier Console-dump provenance for those values too.

**Known, pre-existing gap, unchanged by this session:** our current
replays use `dampening_factor=0.5` (Cardille & Fortin's own published
value) and `posterior_leveler=1.0` (off), NOT production's real
`transitionLeveler=0.7`/`posteriorLeveler=0.9`. This was already flagged
in `../BULC-D_rebuild`'s own `docs/decisions/0004`'s "Open gap" as an
unreconciled structural mismatch (`bulc.py`'s single-scalar `dampen()`
can't represent three separate levelers without further BULC-D_rebuild
work) — not something introduced or changed here. So even with the
correct matrix, our current setup is not yet a full production match on
the leveler side.

**Was this matrix+config combination validated against the real legacy
GUI?** Yes, quantitatively, per `../BULC-D_rebuild/docs/decisions/0010`'s
"Revalidated 2026-08-11" note: `configs/cell_8c_comparison.yaml` (which
carries this exact matrix) was compared pixel-by-pixel against a real
legacy GUI render for cell 8C after a DOY-filter fix — MAE 0.01-0.035 per
band, ~0.86 per-band correlation, **97.9% argmax classification
agreement**, remaining disagreement read as ordinary per-pixel noise
with no systematic structure. This is real, quantified validation
evidence, not just "the numbers came from a real source."

**Bottom line:** we are not drifting from the reference by using this
matrix — it *is* the reference, more so than initially established, and
it's the one combination in this whole project with an actual quantified
match against the real legacy app's output.

### Part 2: first spatial validation (~5km buffers, both sites)

`experiments/spatial_validation.py` reruns each site's exact approved
production-matrix config (recency_factor=1.0, everything else identical
to the point replays) over a real `ee.Geometry.buffer(5000)` polygon
instead of the point-sized AOI. Produces `final_probabilities`'
`decrease` surface, a `>0.5` binary mask, `bulcd.interpret.first_change_year()`
(public API — year-granularity only, since target periods are
single-year, so it's visually close to the binary mask), and an
independent post-disturbance Sentinel-2 false-color (B12/B8/B4)
reference composite, each with the original test point marked. Published
as an inspectable gallery: https://claude.ai/artifact/3gUfR9HoW1yZa2RwBPFzkq
(private artifact; images also saved under `experiments/output/spatial/`).
**Not a false-positive-rate calculation** — no independently-verified
disturbance-perimeter reference data exists for the full buffer area.

**Harvest (9.85% of the 77.6 km² buffer > 0.5, ~7.6 km²):** decrease
detections form several distinct, well-defined rectilinear blobs
consistent with real individual forestry cutblocks scattered through the
buffer (our target point is one of several, not visually the largest) —
plus widespread scattered speckle and a **clearly road/linear-feature-
correlated pattern** threading through the image, a plausible real
false-positive source (edge-mixing, variable road-surface spectral
signature) worth further investigation, not something ruled out here.

**Fire (44.75% of the same-size buffer > 0.5, ~34.7 km²) — much higher
than harvest, but visually well-explained, not obviously spurious.** The
decrease surface shows one large, spatially coherent mass with a sharp
boundary that initially looked like a data-coverage or scene-edge
artifact — the corrected reference composite resolved this immediately:
**the sharp boundary is a lake shoreline** (the buffer straddles a large
lake/reservoir), and the burned area west of it is clearly visible as a
real, extensive red-brown burn scar in the false-color imagery, matching
the decrease surface's shape closely. A second, smaller, more speckled
detached patch appears on the buffer's east side across the lake — not
yet explained, flagged for follow-up, not investigated further here.
The high percentage is very plausibly mostly real fire extent, not
mostly false positives — but this is a visual read, not a measurement,
per the caveat above.

**One implementation bug found and fixed while building this:** the
reference composite initially divided Sentinel-2 SR DN values (0-10000
scale) by 3000 (a true-color habit), saturating the NIR band solid
green and making the reference imagery useless. Fixed to visualize raw
DN with `min=0, max=4000` directly. Did not affect any BULC-D output
(`decrease_probability`/mask/first-detection are independent of the
reference composite) — only the visual-context layer.

**No BULC-D_rebuild code was modified and no parameter was tuned based
on any of the above** — both parts are validation/provenance only.

## 2026-09-28 — Apostle Islands 2026 prototype run: most mapped change predates the season and rings the shorelines

First run over a whole study area with no known disturbance
(`notebooks/early_detection_demo.ipynb`). Config: the validated
fire-replay baseline (production matrix, `recency_factor=1.0`, L8-only
2018–2025 baseline, L8/L9/S2 Jun 1–Sep 30 2026, threshold 0.5).
Nothing was tuned.

- **Scale/runtime:** the full park (WDPA boundary, 277 km²; bulcd run over
  its 2,178 km² bounding box, output clipped to the boundary) completed as
  ONE `Export.image.toAsset` task in 19 min, so no tiling was needed. Live
  `getThumbURL` over a 9 km² custom AOI took ~4 min per map, because every
  map recomputes BULC-D.
- **Result:** of 164 km² analyzed forest, 2.3 km² decrease and 0.3 km²
  increase. About 5 km² of land is excluded by the Hansen non-forest mask.
- **Timing:** ~76% of changed area first crossed 0.5 within the first two
  weeks of the season (median first-detection bin: DOY 156, Jun 5). With
  this matrix, one early-season crossing that persists all season means
  the pixel was already anomalous against the 2018–2025 same-season model
  when observations began. Read the map as "differs from its normal", not
  as in-season disturbance, unless timing says otherwise.
  **Status: OPEN interpretation issue, to investigate after the
  2026-09-30 demo.** The current output largely identifies places that
  differ from the 2018–2025 expectation, not necessarily changes that
  began during the 2026 monitoring season. Detection behavior is
  deliberately left unchanged until then.
- **Spatial pattern:** detections concentrate along island shorelines and
  around the Stockton Island tombolo (open wetland edges, forested dune
  ridge). Sentinel-2 imagery shows the Stockton area looking similar in
  late 2025 and late 2026, consistent with the timing result.
  - **Unresolved:** shoreline mixing at the JRC water-mask edge vs real
    lake-level/shoreline change vs the multi-year baseline.
  - **Not validated:** no reference data or known event was used.
- **Confidence is uninformative at this threshold:** changed pixels have
  median final probability 0.9997, and unchanged pixels ~1.0. So the
  notebook's confidence map shows change pixels only.

## 2026-09-28 — The forest mask is a rebuild default, not a BULC-D requirement

Traced on request, before any change:

- **Legacy BULC-D has no forest mask.** `guiBULCD.rtf` (production GUI)
  has zero forest/treecover/hansen/land-cover references (74 water-mask
  references). Core caller: water only (`legacy/BULCD-Caller-Current.txt:96-97`).
  The only legacy `forestMask` is `mckenzeBULCD.rtf`, a downstream
  "FOREST LOSS ENSEMBLE" workflow (`users/msime/forestChangeEnsemble`),
  not core BULC-D.
- **The rebuild's algorithm assumes nothing about forest:** `bulcd/inputs.py`
  and `bulcd/bulc.py` have no forest/land-cover logic; each pixel is
  compared with its own history. `mask_non_forest=True`
  (`bulcd/config/schema.py:121`, Hansen `treecover2000 >= 10%`) was added
  2026-07-30 after above-treeline false change in cell 2F
  (BULC-D_rebuild `docs/decisions/0006`). It's applied only to
  `final_probabilities` at the end of `run_bulcd` (`bulcd/engine.py:243-245`).
- **The legacy-matched config has it off:** `configs/cell_8c_comparison.yaml:78`,
  `mask_non_forest: false`. Our `build_config` never set it, so every
  replay, the spatial validation and the notebook inherited `True`.
- **Removing it (Stockton area, 43 km², live):** forest pixels identical
  (0 km² differ). Excluded land had 0% Hansen tree cover (beach, sand
  spit, open bog). 27% of it flagged decrease, vs 0.7% of forest (mostly
  the open bog). Park-wide the mask excludes ~5.1 km² (~3% of land).
  Real change vs noise there is unknown.
- **Hansen staleness:** `treecover2000` is year-2000 cover. Land cleared
  since still counts as forest, and forest grown in since is excluded.
- The notebook's earlier caveat "BULC-D's model is tuned for forest" was
  wrong (copied from rebuild comments) and has been corrected.

## 2026-09-28 — First parameter comparison: shoreline decrease disappears without Sentinel-2

`notebooks/early_detection_demo.ipynb` section 10, drawn area
`stockton_south_shore` (3 km², south shore of Stockton Island incl. part
of the open bog). Decrease km² (forest-masked unless noted):

| Variant | Decrease | Increase |
|---|---:|---:|
| Current settings | 0.049 | 0.001 |
| Threshold 0.9 | 0.031 | 0.000 |
| All land (no forest mask) | 0.087 | 0.002 |
| Landsat-only monitoring (no S2) | **0.001** | 0.000 |
| Baseline 2022–2025 | 0.062 | 0.005 |

- **Landsat-only monitoring removes ~98% of decrease.** The baseline is
  Landsat 8 only (EE memory workaround), while monitoring adds Sentinel-2.
  Leading hypothesis: S2 vs L8 differences (spectral response,
  harmonization, 10–20 m pixels at sharp land/water edges) read as
  departures from an L8-only "normal". That would also explain detections
  appearing immediately in early June (see the 76% entry above). Caveat:
  L8+L9-only has fewer observations, so some real change may drop too.
- **Recent baseline doesn't remove it,** so Lake Superior high water in
  2019–2020 inside the baseline isn't supported as the cause here.
- ~63% of decrease survives threshold 0.9: mostly strong evidence, not marginal.
- **One small area only** — a lead, not a conclusion. Needs inland forest
  and other shorelines, and a check against the early-June timing.


## 2026-09-28 — Sensor consistency: S2 detections track the L8-only baseline, not the change

Direct test of the Stockton lead above. `experiments/sensor_consistency.py`:
notebook default controls and `build_config()` throughout; ONLY the
expectation → monitoring sensor sets change. 5 saved ~3 km² AOIs
(`notebooks/aois/`): two suspicious shorelines (`stockton_south_shore`,
`shoreline_top_decrease` = the park's highest-decrease shoreline cell in
the precomputed result), two stable interiors (`stockton_interior`, right
next to the south-shore box; `interior_forest_quiet`), and the known
Jul 18–21 2026 fire (`fire_2026_wa`, same monitoring year). Raw rows:
`experiments/output/sensor_consistency.csv`; tables:
`experiments/summarize_sensor_consistency.py`. 1 pixel = 0.0009 km².

Decrease km² (forest-masked):

| AOI | L8→L8 | L8→L8+L9 | **L8→L8+L9+S2** (current) | L8→S2 | S2→S2 | L8+S2→L8+L9+S2 |
|---|---:|---:|---:|---:|---:|---:|
| stockton_south_shore | 0.0045 | 0.0009 | **0.0486** | 0.0801 | 0.0 | 0.0 |
| shoreline_top_decrease | 0.0045 | 0.0045 | **0.0720** | 0.1152 | 0.0036 | 0.0018 |
| stockton_interior | 0 | 0 | **0.0018** | 0.0063 | 0 | 0 |
| interior_forest_quiet | 0 | 0 | **0** | 0.0054 | 0 | 0 |
| fire_2026_wa | 1.238 | 1.249 | **1.274** | 1.271 | 1.278 | 1.279 |

- **Detections appear only when S2 is in monitoring but not in the
  baseline** (L8→L8+L9+S2, L8→S2), in all four non-fire AOIs. Adding S2 to
  the baseline (S2→S2, L8+S2→L8+L9+S2) removes 95–100% of it.
- **Not an observation-count effect:** S2→S2 uses the same S2 monitoring
  observations as L8→S2 and finds ~nothing; L8→S2 finds the most.
- **Real change is kept by every configuration:** the fire is 1.24–1.28 km²
  in all six; the consistent S2 configs lose nothing.
- **Early June:** in the shoreline cell, 99% of mismatched-config decrease
  first crossed in the season's first 14 days (median DOY 156 = Jun 5 —
  the same median as the park-wide 76% finding). In the fire AOI, 27–33% of
  decrease pixels in the L8-baseline + S2 configs first crossed **before the
  fire started** (DOY < 199), vs 1–2% Landsat-only and 7–8% with S2 in the
  baseline. That fits a cross-sensor offset registering as change as soon as
  the first S2 scenes arrive. (stockton_south_shore is an exception: its
  mixed-config detections are mostly later, median DOY 168.)
- **The S2 baselines ran fine at this size** (15–150 s per run). The
  earlier L8+S2 baseline memory failure happened in the Milestone 1
  harvest/fire replays (2026-09-18 entry), not in an Apostle Islands run.
  An S2-inclusive baseline has never been tried over the whole park, so
  whether it fits there is untested.
- **Status: strong support for the lead, not yet a park-wide conclusion.**
  5 small AOIs, one season, one fire; the mismatched areas are only 2–130
  pixels per AOI. Nothing in the notebook or the precomputed result was
  changed. Next: a park-wide or larger-sample check (e.g. all shoreline
  cells), and whether an S2-inclusive baseline is feasible at park scale.

## 2026-09-29 — North Cascades 2026 with the unchanged default config: widespread decrease, mostly mid/late season

Default config exactly as Apostle Islands (nothing tuned). WDPA "North
Cascades" National Park, 2,022 km². Whole-park export: 40.2 min, one task.

| Outcome | km² | share of analyzed |
|---|---:|---:|
| Decrease | 375.76 | 31.6% |
| Unchanged | 783.57 | 65.9% |
| Increase | 29.97 | 2.5% |
| Not analyzed (non-forest) | 832.86 | — |

- Threshold 0.9 (same probabilities): decrease 326.45, increase 23.65 km².
- Only ~1% of changed area was first detected in the first two weeks
  (Apostle Islands: 76%), so the early-season sensor-mismatch pattern is not
  the dominant signal here.
- Five random forested 2 km boxes: 9–20% decrease each at 30 m.
- **Do not use coarse-scale screening:** a 240 m `computePixels` run flagged ~79%
  decrease; aggregated pixels have lower residual variability, inflating
  z-scores. Not representative of 30 m behavior; discarded.
- Comparison box (23.4 km², 48.83 N 121.19 W): clear single S2 dates show
  green forest on 2026-07-15 and coherent red-magenta loss on 2026-09-06
  (2025-09-10 matches 07-15). Box-mean NBR on clear dates ~0.49 before, ~0.20–
  0.24 after. Heavy haze (blue reflectance 2,000–3,400 vs normal 250–800) from
  ~Jul 20, 2026, which spoils seasonal composites. Cause unconfirmed.
- Parameter effects there (decrease km²): default 13.29; threshold 0.9 10.00;
  sensitivity 0.5 7.95; sensitivity 2.0 16.48; dampening 0.7 13.30; posterior
  leveler 0.9 **16.28** (increases, unlike Devils Island's decrease: it lets
  pixels that were normal until mid-July switch faster).
- **Not investigated** (user direction): why so much decrease is mapped
  park-wide. Candidates to test later: real 2026 change, haze/smoke in
  monitoring imagery, harmonic-baseline fit in steep mountain forest.

## 2026-09-29 — testsite (FeatureCollection) 2026 with the unchanged default config

Study area: `projects/bulcd-python-rebuild/assets/testsite` (1 feature, 26.3 km²,
single polygon, 123.59–123.52 W, 44.81–44.85 N; 24.2 km² forest under the
Hansen mask, no water). Default config as the other notebooks, nothing tuned;
bulcd runs on the asset directly (`aoi_asset`). Export: 1.4 min.

| Outcome | km² | share of analyzed |
|---|---:|---:|
| Decrease | 4.75 | 19.6% |
| Unchanged | 18.75 | 77.5% |
| Increase | 0.68 | 2.8% |
| Not analyzed (non-forest) | 2.21 | — |

- ~64% of changed area first detected in the first two weeks of June.
- Parameter effects, whole site (decrease / increase km²): default 4.78 / 0.69;
  threshold 0.9 4.45 / 0.60; sensitivity 0.5 3.02 / 0.04; sensitivity 2.0
  7.63 / 1.92; dampening 0.7 4.73 / 0.67; posterior leveler 0.9 4.79 / 0.65.
  The comparison runs use their own snapped 30 m grid, so "default" differs
  from the precomputed total by ~0.6% (4.78 vs 4.75): grid alignment, not a
  different result.
- Reference imagery: Sentinel-2 true color on 2024-09-16, 2025-09-16 and
  2026-09-16 (each fully clear over the site per Cloud Score+, low haze; one
  fixed stretch).
- BULC-D's decrease patches are distinct and sharp-edged, and **correspond to**
  patches that are green in 2024 and bare/brown in the 2025 or 2026 imagery;
  the larger increase patches correspond to areas bare in 2024 and greener by
  2026. The imagery shows visible differences that align with the detections;
  it does not confirm a particular disturbance type or cause. The high
  early-June share is consistent with patches that were already bare before
  the 2026 season started. Not field-checked.

## 2026-09-29 — A continuous multi-year run locks in and misses later change; use independent annual runs for timing

**Question:** when did BULC-D first detect each departure (testsite, 2024–2026)?

**First attempt:** one continuous run with monitoring 2024–2026 and baseline 2018–2023
(`config.set_monitoring_years`; engine supports it, no math changes).
- It put 84% of detected decrease in 2024.
- It never detected 32% of the pixels that the 2026 single-season run maps as decrease.

**Cause: posterior lock-in.** With the posterior leveler off (our default), a pixel that
looks normal for one season reaches P(unchanged) ≈ 1.000000. Later evidence cannot
overturn that.
- **Example:** an east-patch pixel (123.51845 W, 44.82731 N) with NBR 0.83 / 0.83 / 0.05 in
  2024 / 2025 / 2026 was at P(unchanged) = 1.000000 from early August 2024 through the
  whole 2026 season. The obvious 2026 loss was never detected.
- Consistent with Section 4's posterior-leveler behavior and with the legacy
  app's use of 0.9. Not a BULC-D bug; a property of long runs without posterior leveling.

**Adopted instead** (no parameter changes): three independent single-season runs
(2024, 2025, 2026), each with the same fixed 2018–2023 baseline and each starting from even
odds (`detection_timing_image` per season, `combine_season_timing`). First detected season =
the earliest season that crossed 0.5; that season's crossing date is kept.

**testsite results** (24.19 km² analyzed):

| First detected | km² | % of detected |
|---|---:|---:|
| 2024 | 3.73 | 52% |
| 2025 | 1.41 | 20% |
| 2026 | 2.01 | 28% |
| Never | 17.03 | — |

**Check against the temporal NBR composite** (categories from annual NBR; Jul 1 – Sep 15,
Cloud Score+):

| NBR pattern | First detected |
|---|---|
| Fell 2025→26 ("yellow") | 94% in 2026 |
| Fell 2024→25 ("red") | 94% in 2025 |
| Low all three years ("dark") | 77% in 2024, 21% never (possibly already low in the baseline; not checked) |

Representative pixel (rule: nearest the center of the largest 2026 + yellow patch):
123.52488 W, 44.82438 N. Never crossed in 2024 or 2025; first crossed 2026-06-13.

The continuous-run assets (`testsite_timing_2024_2026_v1`) remain in Earth Engine but aren't used.

## 2026-09-29 — One-at-a-time parameter responses (default config, other settings fixed)

Decrease km² as each parameter moves alone (notebook section 4):

| Parameter | Devils Island | NOCA comparison box | testsite |
|---|---|---|---|
| Sensitivity 0.5 → 2.0 | 0.14 → 0.75 | 7.9 → 16.5 | 3.0 → 7.6 |
| Threshold 0.5 → 0.95 | 0.47 → 0.41 | 13.3 → 9.2 | 4.8 → ~4.3 |
| Dampening 0.3 → 1.0 | flat | flat | flat |
| Posterior leveler 1.0 → 0.7 | 0.47 → 0.34 (down) | 13.3 → ~16 (up) | ~4.8 → ~4.3 |

- **In these three examples,** sensitivity produced the largest area response, and dampening had
  little effect over the tested range. These are example behaviors, not general rules.
- **The posterior leveler's direction depends on timing:** it reduces decrease where the
  change was present from the start (Devils Island) and increases it where the change began
  mid-season (NOCA), because it prevents lock-in on "unchanged".
- **First crossing vs sustained crossing:** the Devils Island example pixel only just passed 0.5
  on June 5, fell back below it, then crossed decisively in mid-July. "First detected" follows
  the legacy first-change rule (a single crossing counts).

## 2026-09-29 — First-detected-season product at park scale: widespread detections, poor NBR agreement (unresolved)

Same method as testsite: independent 2024 / 2025 / 2026 runs, fixed 2018–2023 expectation, even-odds
start, no parameter changes.

| | Analyzed | Detected (any season) | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| Apostle Islands | 164.4 km² | 64.1 km² (39%) | 6.3 | 3.4 | 54.3 |
| North Cascades | 1,189 km² | 865.5 km² (73%) | 707.6 | 87.5 | 70.5 |
| testsite (for reference) | 24.2 km² | 7.2 km² (30%) | 3.7 | 1.4 | 2.0 |

- **Both parks:** far more is flagged than by the 2026 condition products against 2018–2025
  (Apostle 2.3 km², NOCA 376 km² decrease).
- **Apostle Islands:** the 2026 season departs strongly from 2018–2023 but only slightly from
  2018–2025; nearly all of Devils Island is "first detected in 2026". The NBR composite shows few
  clear NBR drops in the park (<1 km² per category), so it can't check timing there.
- **North Cascades:**
  - 60% of analyzed forest is already "detected" in 2024.
  - Where NBR fell between 2025 and 2026 (7.4 km²), only 26% is first detected in 2026 (47% in
    2024).
  - In the comparison box, the 2026 detections do cluster on the visible mid-July 2026 loss.
- Reads as a systematic effect: expectation years, the Landsat-only baseline vs Sentinel-2
  monitoring, or regional seasonal conditions. **Not investigated** (user direction).
- Testsite, with distinct harvest patches, agrees well (94%/94%); the parks don't.

## 2026-09-29/30 — Experiment: rolling vs fixed expectation for the first-detected season

**Rolling:** 2018–2023 → 2024 (shared with fixed), 2018–2024 → 2025, 2018–2025 → 2026. Independent
annual runs from even odds; nothing else changed. New assets `{prefix}_timing2025_base2018_2024_v1`
and `{prefix}_timing2026_base2018_2025_v1` (27 min for all six). The fixed-baseline assets and code
are kept. Not adopted; the notebooks are unchanged.

First detected (km²), fixed → rolling:

| Site | 2024 | 2025 | 2026 | Never |
|---|---|---|---|---|
| testsite | 3.73 → 3.73 | 1.41 → 1.40 | 2.01 → 2.03 | 17.03 → 17.03 |
| Apostle Islands | 6.33 → 6.33 | 3.43 → 3.50 | 54.29 → 62.20 | 100.32 → 92.34 |
| North Cascades | 707.6 → 707.6 | 87.5 → 77.7 | 70.5 → 66.5 | 323.8 → 337.6 |

- **The expectation strategy barely changes the result;** the maps look essentially the same.
  - testsite keeps its NBR agreement: 94% of 2025→26 NBR loss first detected in 2026, 94% of
    2024→25 loss in 2025.
  - North Cascades stays poor (25% of 2025→26 loss first detected in 2026).
  - The 2024 run is the same in both strategies, so North Cascades' 2024 dominance can't change.
- **2026 consistency check:** the rolling 2026 run and the 2026 condition product use identical
  configs. Their end-of-season states match pixel for pixel at testsite and Apostle Islands.
  - North Cascades differs in 126 pixels (0.11 km²). The late-September 2026 Sentinel-2 scenes there
    (acquired Sep 16–28) carry an Earth Engine version of 2026-09-30 04:20 UTC, between the two
    exports, so the input imagery changed between runs.
  - Every condition-decrease pixel is detected in some season: 0 km² "never".
- **What actually drives the park results: the first-crossing rule, not the expectation period.**
  The timing product counts any crossing of 0.5 during a season; the condition product uses the
  end-of-season state. Area that crossed during the 2026 run but was not decrease at season end:

  | Site | Crossed in 2026, not decrease at season end |
  |---|---:|
  | Apostle Islands | 67.7 km² |
  | North Cascades | 217.6 km² |
  | testsite | 0.76 km² |

  These transient crossings (like the Devils Island pixel's brief June 5 crossing) dominate the
  park timing maps. testsite's harvest patches stay above threshold, so it is barely affected.
- **Conceptual caveat of rolling expectations (documented, not solved):** once a pixel changes in
  2024, including 2024 in the 2025 expectation begins to fold its changed state into "normal". For
  a first-detected product that keeps the earliest detection year, that may be acceptable (the
  pixel was already counted in 2024), but it weakens later-season evidence for persistent changes.

## 2026-09-30 — Experiment: timing rule A (raw first crossing) vs B (end-of-season-confirmed)

Fixed 2018–2023 expectation; same annual runs; no BULC-D changes. Only the timing rule changes:
- **A (current):** a season counts if P(decrease) ever crossed 0.5 in it.
- **B:** a season counts only if it ENDS as decrease; the date kept is still that season's first
  crossing.

B is derived from the existing assets (`combine_season_timing(..., confirmed=True)`, experimental
opt-in; default is still A). Not adopted; notebooks unchanged.

First detected (km²), A → B:

| Site | 2024 | 2025 | 2026 | Detected | Never |
|---|---|---|---|---|---|
| testsite | 3.73 → 3.14 | 1.41 → 1.42 | 2.01 → 1.74 | 7.15 → 6.30 | 17.03 → 17.89 |
| Apostle Islands | 6.33 → 2.00 | 3.43 → 1.05 | 54.29 → 0.66 | 64.05 → 3.71 | 100.32 → 160.66 |
| North Cascades | 707.6 → 387.8 | 87.5 → 112.0 | 70.5 → 56.5 | 865.5 → 556.4 | 323.8 → 632.9 |

- **Verification:** in every annual run at all three sites, B-eligible pixels equal that season's
  end-of-season decrease. Every end-decrease pixel has a crossing (0.0000 km² without one). Transient
  area (crossed, not end-decrease) per season:

  | Site | 2024 | 2025 | 2026 |
  |---|---:|---:|---:|
  | testsite | 0.59 | 0.34 | 0.63 |
  | Apostle Islands | 4.33 | 3.81 | 59.33 |
  | North Cascades | 319.8 | 202.4 | 200.9 |

- **NBR timing agreement:**
  - testsite improves slightly: 2025→26 loss 94% → 96% first detected in 2026; 2024→25 loss 94% →
    97% in 2025.
  - North Cascades improves: 2025→26 loss first detected in 2026 goes 26% → 40%, "2024" goes 47% → 28%.
  - Apostle Islands has too little clear NBR loss to check.
- **Spatial:**
  - Devils Island goes from nearly all "2026" to 0.39 km² of 2026 plus small 2024/2025 patches in the
    north-central interior (focus: A 0.96 km² detected → B 0.53).
  - In the NOCA comparison box, 2026 becomes the largest class (6.4 km²) around the visible mid-July
    2026 loss, but "2024" still covers 6.2 km².
- **Example trajectories** (rule-based picks):
  - A NOCA transient crosses every year in late June to mid-July, then returns to ~0 by September.
    Early-season NBR sits well below the expected curve, then rejoins it: a recurring early-season
    shape mismatch, not a disturbance (not investigated).
  - An Apostle transient: one low June 5, 2026 observation puts P at ~0.50, and it decays within weeks.
  - Confirmed examples are sustained departures (NOCA: NBR drops late Aug 2026, P reaches 0.78).
- **Conclusion:** "ever crossed 0.5" is the main reason the park timing maps looked wrong. At
  Apostle Islands it accounts for ~94% of the detected area. At North Cascades B still leaves
  substantial 2024 detections, so something else contributes there (early-season model fit and/or
  sensors).

**Bug fixed during this experiment:** `pixel.pixel_history` sampled with `getRegion` on Earth Engine's
default grid for computed images, which can be offset from the 30 m UTM grid of the exported
products. In patchy terrain it read a neighboring pixel (NOCA example: live P(decrease) 0.19 on the
default grid vs 0.78 on the product grid, ~10 m apart). It now samples on the product's UTM grid. The
four example pixels then match their asset crossing dates and end states exactly. Pixel charts
already embedded in the committed notebooks were made before this fix.

## 2026-09-30 — North Cascades sensor experiment: the mixed L8-only expectation / L8+L9+S2 monitoring setup inflates the "2024" class

`experiments/noca_sensor_timing.py`. Everything identical except the sensor sets:
- fixed 2018–2023 expectation;
- independent 2024/2025/2026 seasons from even odds;
- same window, masks, sensitivity, threshold, matrix, dampening, leveler and grid.

The current setup was re-run too, so all 15 exports read the same input versions.

First detected, rule B (end-of-season confirmed), km²:

| Expectation → monitoring | 2024 | 2025 | 2026 | Never | End-of-season decrease 2024 / 2025 / 2026 |
|---|---:|---:|---:|---:|---|
| **L8 → L8+L9+S2 (current)** | **387.8** | 112.0 | 56.6 | 632.9 | 387.8 / 458.7 / 454.2 |
| L8 → L8 | 157.0 | 142.7 | 78.1 | 811.6 | 157.0 / 228.1 / 245.9 |
| L8 → L8+L9 | 122.3 | 87.4 | 87.8 | 891.8 | 122.3 / 166.2 / 238.7 |
| S2 → S2 | 92.3 | 97.4 | 65.4 | 934.2 | 92.3 / 182.6 / 231.2 |
| L8+S2 → L8+L9+S2 | 91.3 | 87.2 | 60.5 | 950.3 | 91.3 / 170.5 / 213.0 |

- **Every consistent setup cuts the 2024 class by 60–76%.** The setups with Sentinel-2 in both periods are lowest (~91 km²).
- **Fate of the current 388 km² "2024" class** under consistent setups: only 86–109 km² stays 2024,
  12–66 km² moves to 2025/2026, and 189–253 km² is never detected.
- **What remains in 2024 is spatially coherent.** A few large, sharp-edged patches in the north unit
  persist in every setup: candidates for real change present by 2024 (not verified against
  imagery). The diffuse scattered 2024 detections are what the mixed setup adds.
- **Comparison box (rule B, 2024):** 6.24 km² (current) → 0.41–0.43 km² with S2 in both periods, and
  1.1–2.2 km² Landsat-only. 2026 detections cluster on the visible 2026 loss in the S2-consistent
  setups.
- **Observation counts** over the comparison box, per season:

  | Sensor | Jun–Sep scenes | June scenes |
  |---|---:|---:|
  | Landsat 8 | ~7 | 1–2 |
  | Landsat 9 | ~7 | ~2 |
  | Sentinel-2 | 48–60 | 12–15 |

  In the current setup most monitoring observations are S2, judged against an L8-only expectation.
  Landsat-only runs are sparse: one example pixel had a single clear 2024 observation.
- **Rule A (any crossing) still shows transients in Landsat-only runs** (L8 → L8: 217 km² "2024" under
  rule A vs 157 under rule B), so transient early-season crossings are not purely an S2 effect. The
  large inflation of the confirmed (rule B) 2024 class is associated with mixing S2 monitoring with an
  L8-only expectation.
- **Practical limitations:**
  - Configs with S2 in the expectation ran fine as batch exports, but `pixel_history` for them hits
    "User memory limit exceeded" interactively (the same harmonic-fit limit that originally forced
    the L8-only baseline).
  - Park-wide timing maps with display enlargement also exceeded memory in this session.
- **Not adopted, nothing tuned.** Choosing a sensor configuration is a separate decision.

**Conclusion (2026-09-30).** Using a Landsat 8-only expectation with L8+L9+Sentinel-2 monitoring
substantially inflates the confirmed 2024 detection class at North Cascades. Consistent sensor
configurations reduce that class by roughly 60–76%. Because Sentinel-2 supplies far more monitoring
observations than either Landsat sensor, the current mixed configuration effectively compares a
Sentinel-2-dominated monitoring series against a Landsat 8-only expectation. This indicates a
**sensor-consistency problem**, but it does **not** yet establish the best production sensor
configuration; the default configuration is unchanged.

Also:
- **Transient early-season crossings still occur in Landsat-only runs,** so sensor mismatch does not
  explain all early-season behavior.
- **Some sharp-edged North Cascades 2024 patches persist in every sensor configuration** and need
  independent imagery/reference inspection before interpretation.
- **S2-inclusive expectation configurations hit the known Earth Engine memory limitation:**
  - interactively, for pixel histories and live computation;
  - at park scale they completed only as batch exports.


## 2026-10-04 — Legacy GUI vs. Python rebuild, one-pixel equivalence (testsite, −123.56922 44.84283)

Reference: a controlled legacy GUI (V53e) run. L8+L9+S2 (Cross-Sensors), NBR, expectation 2024 / target 2025,
DOY 1–365, scene cloud 70, day step 3, constant+unimodal, numerator 1, minimum denominator 0.05. Script:
`experiments/legacy_gui_equivalence.py`; outputs in `experiments/output/legacy_gui_equivalence/<grid>/`.
The bulcd config was set to the GUI's hardcoded BULC parameters (levelers 0.7/0.7/0.9, start = "unchanged").
Investigation only; nothing tuned.

- **Python reproduces the GUI's qualitative result.** 2024 sits near the fit. In 2025, NBR drops from about 0.7–0.8 to
  about 0 starting with the 2025-03-26 S2 bin and stays there. 59 of the 122 three-day target bins have data. Every
  data bin from 2025-04-04 on is bin 1. P(decrease) is first above 0.5 at the 2025-04-04 bin and plateaus at
  0.914/0.043/0.043. That plateau is the posterior-leveler fixed point, so it is the maximum reachable.
- **Stage by stage, the formulas match the fetched legacy source.** The stages checked: 3-day bins (122/122, ends at
  the bin end, median across sensors), harmonic regressors, OLS fit, residual = observed − fitted, SD (n−1) of
  expectation residuals, z = clamp((obs − fit) / max(SD, 0.05), ±10), and the BULC fold with leveled transitions and
  posterior.
  - A numpy re-derivation using the legacy time variable (fracDOY = 0-based DOY / 365) matches bulcd's probabilities
    to 5 decimals. bulcd instead uses fractional years since 1970. That shifts the fitted curve by ≤ 0.001 NBR and
    changes no bins here.
- **First real input divergence: the S2 scene filter.** Legacy's live S2 path (Cloud Score+,
  `515-gatherCollections27b` lines 873–877) applies **no** scene-level cloud filter; `CloudCoverThresholdS2` is
  only used in commented-out code. bulcd's `_s2_evidence` drops scenes with `CLOUDY_PIXEL_PERCENTAGE > 70`.
  - At this pixel, 5–6 scenes with a clear pixel were dropped. One filled an otherwise-empty 2024 expectation bin
    (Feb 6, affecting the fit); another filled an empty 2025 target bin (Jun 24, already saturated).
  - The divergence is small here but systematic. It goes in BULC-D_rebuild, so it is not fixed in this repo.
- **The sampled pixel depends on the grid.** EPSG:4326 at 30 m and UTM 10N at 30 m hit different pixels: fit
  0.739 vs 0.796, SD 0.0695 vs 0.0456 (the latter floored to 0.05). Detection timing was the same. Exact numerical
  comparison needs the legacy chart's sampling scale/CRS.
- **What the legacy charts plot cannot be confirmed from the source we have.** `getChartResults` lives in
  `r-2903-Dev:BULC/BULCD/BULCD-Helpers/HelperFunctions-BULCD`, which is not fetched. Likely inputs (inferred from
  its arguments, `bulcD_input` and `fullBULCReturn`):
  - `expectCollectionFit` [nbr, fitted] → chart 1;
  - `targetCollectionFit` → chart 2;
  - `fullBULCReturn.allProbabilityLayers` → chart 3;
  - `allEventLayers` (bins, self-masked) → chart 4;
  - `expectationResiduals` / `targetResiduals` → charts 5/6.
  - Also unfetched: the bin edge rule `afn_getOneZBin` (`CommonCode:502.8-Binning/502.8-Binning-5`) and the
    transition dampening `afn_dampenTruthAndAddDummyRow11` (`CommonCode:510.ArrayOperations/510a`).
- **Not compared yet:** the GUI's own numbers. The GUI screenshots only show shapes. Exact equivalence needs the
  legacy per-pixel values exported (see PROJECT_STATE "Next steps").

## 2026-10-04 (later) — OG GUI chart CSVs vs. Python: equivalence confirmed; three explained differences

Ground truth: five chart CSVs exported from the legacy GUI for the reference case above (now in
`experiments/reference_data/legacy_gui_charts/pixel1/`; 122 steps each, 3 decimals). Script: `experiments/legacy_gui_csv_compare.py`; outputs in `experiments/output/legacy_gui_csv_compare/`.
"Exact" means |diff| ≤ 0.0005. Investigation only; bulcd is unchanged, and the S2 test is a config-only variant.

- **Sampling: the GUI reads each scene at its own native pixel containing the point.**
  - Python point sampling at 1 m (EPSG:4326 or UTM) reproduces the GUI's NBR: 48/49 exact, with the S2 filter as-is.
  - 30 m grids sample different pixels: 0/49 exact on UTM 30 m, 3/49 on EPSG:4326 30 m. The previous entry's
    30 m tables were therefore other pixels.
  - Native-pixel sampling also determines the fit and SD (0.0378, so the denominator is the 0.05 floor).
- **Results, with the S2 scene filter removed (`s2_nofilter`):**

  | Stage | Agreement |
  |---|---|
  | Time steps | 122/122 identical dates in both periods |
  | Expectation NBR | 50/50 exact |
  | Expectation fitted | 119/122 exact (max 0.0006) |
  | Target NBR | 60/60 exact |
  | Target fitted | 59/122 exact (max 0.0013) |
  | Target residual | 26/60 exact (max 0.0013) |
  | Bins | 60/60 |
  | Probabilities (lag 1) | 363/363 values exact (max 0.0005) |
  | Final probabilities | 0.914/0.043/0.043 in both |

- **Divergence 1, imagery (first, and the only one that changes inputs): S2 scene filter.** With bulcd as-is
  (`CLOUDY_PIXEL_PERCENTAGE ≤ 70`):
  - The GUI has one more expectation observation (2024-02-06) and one more target observation (2025-06-24).
    Target NBR differs at 2 steps (max 0.0505): one is the missing step, the other a bin whose median loses a scene.
  - These feed into the fit, so only 31/122 expectation fitted values are exact (max 0.0033).
  - Bins agreed 59/59 and probabilities 363/363 anyway.
  - Turning off the S2 scene filter removes every one of these differences. Confirms the source reading: the legacy
    Cloud Score+ path has no S2 scene filter.
- **Divergence 2, harmonic time variable (fit stage): small.**
  - Refitting the same observations with legacy's `fracDOY` = (0-based DOY of bin end)/365 reproduces GUI fitted
    values 244/244 exactly and target residuals 60/60.
  - bulcd's years-since-1970 axis is off by up to 0.0013 NBR (0.026 z). That is too small to change bins here:
    the nearest z is 0.074 from a cut.
- **Divergence 3, chart construction, not algorithm: the GUI probability chart is shifted one step.**
  - GUI row k is the posterior after step k−1. Row 1 (2025-01-04) is the starting prior 0.1/0.8/0.1, and the
    posterior after the final step is not plotted.
  - So the GUI's first P(drop) > 0.5 is labeled 2025-04-07, while the update that causes it is the 2025-04-04 step.
- **Chart meanings, confirmed numerically:**
  - **"Year vs Fit":** 3-day median NBR (`nbr`, blank = no clear data) and harmonic `fitted` at every step.
  - **Target residuals:** `targetDifference` = nbr − fitted, only where observed (60/60 consistent).
  - **Bins:** z-score bin 1–10 at steps with data, blank otherwise.
  - **Probabilities:** prior-then-posteriors, with the one-step offset above.
  - The expectation residual chart was not exported.
- **Still unverified:**
  - The GUI's SD/denominator and z are not in the exports; they are inferred through 60/60 bin agreement.
  - The bin edge rule at exactly a cut and the exact transition-dampening code are untested; no value here lies near
    a cut.
  - This is one pixel, one case.

## 2026-10-04 (later) — Pixel 2 (stable/green, −123.55299 44.83292): GUI CSVs vs. Python

Same settings as pixel 1. GUI exports are the `*_g.csv` files (now in `experiments/reference_data/legacy_gui_charts/pixel2/`),
which now include expectation residuals. Script: `experiments/legacy_gui_csv_compare.py`; outputs in
`experiments/output/legacy_gui_csv_compare/{pixel1,pixel2,pixel2_gui_location}/`. Pixel 1 was rerun and its
numbers are unchanged. Investigation only; bulcd is unchanged.

- **First divergence at the stated coordinate is the sampled location, not the algorithm.**
  - Expectation NBR: only 12/52 exact (S2 filter off). Python also has an extra observation (2024-06-29).
  - Landsat-only steps match exactly; S2 steps mostly do not, so a different S2 pixel is being read.
  - Offset scan (1 m point sampling): GUI values are reproduced 52/52, with identical presence, only inside one
    10 m S2 pixel. It lies 0.7–10.5 m east and 1.2–11.5 m north of the stated coordinate; the nearest matching
    point is +0.9e-5° lon / +1.1e-5° lat.
  - That is more than 5-decimal rounding (≤ 0.5e-5°). So the point the GUI chart sampled is not exactly the
    reported coordinate. The mechanism is unknown (marker placement, chart snapping, or coordinate copying).
- **At the GUI's sampled location (`pixel2_gui_location`, −123.552919 44.832977), S2 filter off:**

  | Stage | Agreement |
  |---|---|
  | Expectation NBR | 52/52 exact |
  | Expectation residuals | 52/52 exact |
  | Target NBR | 61/61 exact |
  | Bins | 61/61 |
  | Probabilities (lag 1) | 363/363 exact |
  | Fitted with bulcd's time axis | 120/122 (expectation), 96/122 (target), max 0.0008 |
  | Fitted with legacy fracDOY | 122/122 and 122/122 exact |
  | Target residuals | 51/61 exact with bulcd's time axis (max 0.0007); 61/61 with legacy fracDOY |

  - This confirms what the expectation-residual chart plots: `expectationDifferenceOptical` = nbr − fitted.
- **The S2 scene filter matters much more at a stable pixel.**
  - bulcd as-is at the GUI location loses the same 2024-02-04 S2 scene (expectation) and 2025-06-23 scene (target)
    as at pixel 1. Those were 2 of 51 expectation values, but they shift the fit by up to 0.0125 NBR.
  - With z near 0, that flips 12/60 bins between the 4/5/6/7 neighbours. Probabilities: 300/363 exact, max diff
    0.155; GUI's last plotted value 0.055/0.899/0.045 vs Python 0.098/0.852/0.049.
  - At pixel 1 (z ≈ −10) the same filter changed nothing downstream.
- **The harmonic time axis is a real bin-flip risk here.** The nearest z is 0.006 from a cut, while bulcd's time axis
  is off by up to 0.0008 NBR (0.016 z). No bin flipped in this case.
- **Chart offset confirmed again.** The GUI's last plotted row (2026-01-02) is the posterior after the 2025-12-30
  step. The posterior after the final step (Python 0.046/0.911/0.043) is never plotted.
- **P(same) behaves as a stable pixel should.**
  - P(same) stays 0.85–0.91 from the first update to the end, except Nov 12–24 (minimum 0.753). There a bin-1
    observation on 2025-11-09 (z −2.13) and a bin-4 one briefly raise P(drop) to 0.18. It recovers to 0.899.
  - No threshold crossing. Bins: 35× 6, 14× 5, 5× 4, 4× 7, 2× 3, 1× 1.

## 2026-10-08 — Pixel 3 (increase, −123.54330474162032 44.847525314894625): equivalence now covers decrease, unchanged, and increase

Same settings as pixels 1–2. GUI exports are the `*_b.csv` files. All three pixels' exports moved to
`experiments/reference_data/legacy_gui_charts/pixel{1,2,3}/`, with filenames unchanged, coordinates, and settings in
the README there. Script: `experiments/legacy_gui_csv_compare.py`; outputs in
`experiments/output/legacy_gui_csv_compare/pixel3/`. Investigation only; bulcd and Early Detection are unchanged, and
the S2 test is a config-only variant.

**Overall conclusion.** We now have controlled GUI-vs-Python validation examples for all three outcomes:
- decrease (pixel 1);
- unchanged (pixel 2, at the GUI's sampled location);
- increase (pixel 3).

With legacy-compatible inputs and settings, each one shows:
- exact NBR and residuals;
- exact bins (60/60, 61/61, 61/61);
- probability trajectories that agree exactly once aligned for the chart offset (363/363 each).

Every remaining difference is one of three known, separately documented ones (below).

- **Point provenance.** The coordinate first given for pixel 3 (−123.54755, 44.83627) matched nothing.
  - 0/46 NBR values were exact, and no point on a 15 m grid within ±150 m reproduced the GUI series. It was a
    different click.
  - The GUI's Charts mode passes all four linked maps to `getChartResults(maps, ...)` (in the unfetched
    `HelperFunctions-BULCD`), which handles its own clicks. A temporary `maps[0].onClick()` listener is therefore
    not guaranteed to record the charted point.
  - The coordinate above was captured at full precision and matches directly; no offset scan was needed.
- **Results with the S2 scene filter removed (`s2_nofilter`):**

  | Stage | Agreement |
  |---|---|
  | Time steps | 122/122 identical dates in both periods |
  | Expectation NBR | 54/54 exact |
  | Expectation fitted | 117/122 with bulcd's time axis (max 0.0011); 122/122 with legacy fracDOY |
  | Expectation residuals | 52/54 with bulcd's time axis; 54/54 with legacy fracDOY |
  | Target NBR | 61/61 exact |
  | Target fitted | 23/122 with bulcd's time axis (max 0.0019); 122/122 with legacy fracDOY |
  | Target residuals | 13/61 with bulcd's time axis (max 0.0019); 61/61 with legacy fracDOY |
  | Bins | 61/61 |
  | Probabilities (lag 1) | 363/363 exact |
  | Final plotted probabilities | 0.044/0.055/0.900 in both |

  - It is a clear increase: z up to 4.45, P(up) 0.900 at the end, P(drop) never above 0.253. This is the first
    validation of the increase class and the upper bins (8–10).
  - The nearest z is 0.002 from a bin cut, the closest yet. The bin still agrees, although the edge rule at
    exactly a cut remains untested.
- **The three known differences, unchanged:**
  1. **Sentinel-2 scene filter (imagery; the only one that changes inputs).** bulcd drops S2 scenes with
     `CLOUDY_PIXEL_PERCENTAGE > 70`; the legacy Cloud Score+ path has no scene filter. Pixel 3 shows it can
     materially change the classification evidence:
     - as-is, bulcd loses two 2024 expectation scenes (2024-02-06, 2024-03-07);
     - that shifts the fit by up to 0.089 NBR and the residual SD from 0.126 to 0.096;
     - result: **30/61 bins change** (mostly 1–3 bins higher) and only 88/363 probabilities stay exact;
     - the final outcome is still increase here (0.043/0.043/0.914), but the evidence sequence is substantially
       different.

     Compare pixel 1 (0 bins changed) and pixel 2 (12/60).
  2. **Harmonic-fit time axis (fit stage).** Legacy uses fracDOY = (0-based DOY of bin end)/365; bulcd uses
     fractional years since 1970. The legacy axis reproduces every GUI fitted value and residual exactly. bulcd's
     is off by up to 0.0019 NBR (0.015 z with this pixel's SD), which flipped no bins here.
  3. **GUI probability-chart offset (chart construction, not algorithm).** GUI row k is the posterior after step
     k−1: row 1 is the 0.1/0.8/0.1 prior, and the posterior after the final step (Python 0.043/0.046/0.911) is
     never plotted. Lag-0 comparison: 207/366; lag 1: 363/363.
- **Still unverified:** the bin edge rule exactly at a cut, the exact transition-dampening code, and anything
  outside this one site, sensor set, and year pair. Three pixels, one case.

## 2026-10-08 (later) — BULC-D_rebuild decision 0011: legacy S2 behavior and time axis are now the default; GUI equivalence holds with no tweaks

**Validation result.** With normal/default settings, Python now exactly reproduces the legacy GUI for the
controlled decrease, unchanged, and increase pixels through observed NBR, fitted expectation, residuals, bins, and
aligned probability trajectories. The remaining GUI probability-date difference is a plotting offset, not an
algorithm difference. The GEE JavaScript engine (`../BULC-D_rebuild/gee/bulcd.js`) in turn matches Python to
floating-point precision (max difference 2.7e-15 over every per-step value at pixels 1–3 and a 30 m box of final
probabilities; `gee/tests/run_parity.py`).

**The existing `_v1` Early Detection assets are pre-0011 outputs and should not be treated as current results.**

BULC-D_rebuild changed two defaults to match legacy (decision 0011,
`../BULC-D_rebuild/docs/decisions/0011-legacy-s2-scene-filter-and-fracdoy-time-axis.md`):
- **No Sentinel-2 scene-cloud filter by default.** `cloud_cover_threshold` keeps the legacy meaning and applies to
  Landsat only. A new opt-in, `s2_scene_cloud_threshold`, re-enables the `CLOUDY_PIXEL_PERCENTAGE` filter.
- **Harmonic time axis is legacy fracDOY**, i.e. (0-based DOY of the bin end) / 365.

Configs keep the GUI's parameters as-is: cloud 70 for every sensor, and this repo's `config.py` is unchanged.

**Acceptance (normal implementation, no config workaround).** `experiments/legacy_gui_csv_compare.py` now has two
variants: `default` and the `s2_scene_filter` opt-in. Pre-0011 outputs were moved to
`experiments/output/legacy_gui_csv_compare/_pre_0011/`.

| Pixel | NBR (exp/target) | Fitted (exp/target) | Target residuals | Bins | Probabilities (lag 1) | Final plotted |
|---|---|---|---|---|---|---|
| 1 decrease | 50/50, 60/60 | 122/122, 122/122 | 60/60 | 60/60 | 363/363 | 0.914/0.043/0.043 |
| 2 unchanged (GUI location) | 52/52, 61/61 | 122/122, 122/122 | 61/61 | 61/61 | 363/363 | 0.055/0.899/0.045 |
| 3 increase | 54/54, 61/61 | 122/122, 122/122 | 61/61 | 61/61 | 363/363 | 0.044/0.055/0.900 |

- All are exact to the CSVs' 3-decimal rounding. The fitted curves now match with bulcd's own time axis, not only a
  numpy re-fit.
- Of the three documented differences, only the GUI chart's one-step plotting offset remains. It is a chart
  convention, not part of the algorithm.
- Pixel 2 at its *reported* coordinate still differs because that is a different S2 pixel (the location offset
  above).
- With the opt-in S2 filter, the old effects reappear: 0, 12 and 30 changed bins at pixels 1, 2 and 3.

**Effect on the Early Detection default testsite run** (app defaults: testsite, expectation 2018–2023, monitoring
2026 Jun 1–Sep 30, L8 baseline, L8+L9+S2 monitoring, forest and water masks, threshold 0.5). It was compared pixel by
pixel on the 30 m grid: 27,179 analyzed pixels. The "old with S2 filter off" run used the old code with the S2
threshold at 100, which isolates the two effects.

| Comparison | Pixels changing class | Main moves | Mean / p99 / max \|ΔP(decrease)\| |
|---|---|---|---|
| S2 filter only (old → old with S2 off) | 103 (0.38%) | 62 unchanged→decrease, 25 increase→unchanged, 13 decrease→unchanged | 0.003 / 0.096 / 0.72 |
| Time axis only (old S2-off → new) | 11 (0.04%) | small, mixed | 0.0002 / 0.0000 / 0.34 |
| Net (old → new) | 106 (0.39%) | 61 unchanged→decrease, 25 increase→unchanged, 14 decrease→unchanged | 0.003 / 0.098 / 0.72 |

Class totals went from 6,387 / 19,660 / 1,132 (old) to 6,434 / 19,632 / 1,113 (new) for decrease / unchanged /
increase.

- At this site and season, the change is small and comes almost entirely from S2: the extra, partly cloudy
  scenes in the 2026 monitoring season.
- The time axis barely matters here, because the 2018–2023 baseline is Landsat-only.
- Cloudier parks (Apostle Islands in June, North Cascades) were not measured. Their v1 assets are pre-0011 and
  `outputs.load_precomputed()` now warns when loading any `_v1` run.
