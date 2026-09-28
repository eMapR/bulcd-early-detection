"""Diagnostic trace: decompose the fire_2026 replay's per-step Bayesian
update into its transition-matrix / bayes_update() / posterior_leveler /
recency-discount components, to explain why decrease_probability never
crosses 0.5 at gamma=1.0 and plateaus around 0.497 at gamma=0.85 despite
extreme post-fire z-scores (see docs/findings.md's recency_factor sweep
entry).

Investigation only - does not change BULC-D_rebuild code or the
approved fire config, and does not tune anything. Calls BULC-D_rebuild's
real functions directly for each step (including two "private" engine.py
helpers, _bin_zscore/_bin_to_update_factors - used here for
introspection, not modified) rather than re-deriving the math in
Python, so the trace is exactly faithful to what run_bulcd() actually
computed - not a reimplementation. Validated against the real
probability_stack values already saved in fire_2026_replay.csv /
fire_2026_recency_0.85.csv (see the "mismatch" check at the end of each
trace).

Usage:
    conda run -n bulcd python experiments/trace_fire_recency_mechanism.py
"""

from __future__ import annotations

from pathlib import Path

import ee

ee.Initialize(project="bulcd-python-rebuild")

from bulcd.bulc import bayes_update, dampen, discount
from bulcd.engine import _DECISION_CLASS_NAMES, _bin_to_update_factors, _bin_zscore

from _replay_common import load_rows
from replay_fire_2026 import NBR12_TRANSITION_MATRIX

# Same constants as the approved config (BULCDConfig defaults / fire script).
BIN_CUTS = [-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2]
DAMPENING_FACTOR = 0.5
POSTERIOR_LEVELER = 1.0

_ORIGIN = ee.Geometry.Point([0, 0])  # constant images - location is irrelevant


def _read(image: ee.Image) -> dict:
    return image.reduceRegion(ee.Reducer.first(), _ORIGIN, 1).getInfo()


def _as_prior_image(probs: dict) -> ee.Image:
    return ee.Image.cat(
        [ee.Image.constant(float(probs[name])).rename(name) for name in _DECISION_CLASS_NAMES]
    )


def _fmt(d: dict) -> str:
    return f"{d['decrease']:.3f}/{d['unchanged']:.3f}/{d['increase']:.3f}"


def trace(rows: list[dict], recency_factor: float, label: str) -> None:
    print(f"\n=== {label} (recency_factor={recency_factor}) ===")
    print(
        f"{'date':10} {'z':>6} {'bin':>3}  {'UF d/u/i':<20} {'prior d/u/i':<20} "
        f"{'post-bayes d/u/i':<20} {'post-leveler d/u/i':<20} {'post-discount d/u/i':<20} "
        f"argmax  vs-real"
    )
    prior = {"decrease": 1 / 3, "unchanged": 1 / 3, "increase": 1 / 3}  # initializing_leveler=0.0
    for row in rows:
        if not row["valid"]:
            print(f"{row['observation_date']:10} {'--':>6} {'--':>3}  (masked - prior carries forward unchanged)")
            continue

        prior_image = _as_prior_image(prior)
        z_image = ee.Image.constant(row["zscore"])
        binned = _bin_zscore(z_image, BIN_CUTS)
        update_factors = _bin_to_update_factors(binned, NBR12_TRANSITION_MATRIX)
        dampened_uf = dampen(update_factors, DAMPENING_FACTOR)
        post_bayes = bayes_update(prior_image, dampened_uf)
        post_leveler = dampen(post_bayes, POSTERIOR_LEVELER)
        post_discount = discount(post_leveler, recency_factor)

        bin_val = int(_read(binned)["bin"])
        uf, pb, pl, pd = _read(update_factors), _read(post_bayes), _read(post_leveler), _read(post_discount)
        argmax = max(pd, key=pd.get)

        real = {"decrease": row["decrease_probability"], "unchanged": row["unchanged_probability"], "increase": row["increase_probability"]}
        max_delta = max(abs(pd[c] - real[c]) for c in _DECISION_CLASS_NAMES)
        vs_real = "match" if max_delta < 1e-6 else f"DELTA={max_delta:.2e}"

        print(
            f"{row['observation_date']:10} {row['zscore']:6.2f} {bin_val:3d}  "
            f"{_fmt(uf):<20} {_fmt(prior):<20} {_fmt(pb):<20} {_fmt(pl):<20} {_fmt(pd):<20} "
            f"{argmax:<7} {vs_real}"
        )
        prior = pd
    print(f"Final reconstructed prior: {_fmt(prior)}")


def main() -> None:
    output_dir = Path(__file__).parent / "output"
    trace(load_rows(output_dir / "fire_2026_replay.csv"), recency_factor=1.0, label="fire_2026")
    trace(load_rows(output_dir / "fire_2026_recency_0.85.csv"), recency_factor=0.85, label="fire_2026")


if __name__ == "__main__":
    main()
