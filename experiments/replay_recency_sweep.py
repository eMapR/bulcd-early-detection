"""recency_factor sweep against the two real-disturbance replays.

Tests whether BULC-D_rebuild's recency_factor/discount() mechanism
(bulcd/bulc.py, docs/decisions/0005-recency-weighting-extension.md)
addresses the "algorithm never crosses the decision threshold" finding
from the harvest/fire replays (see docs/PROJECT_STATE.md, Milestone 1b).

Changes ONLY recency_factor (1.00 control, 0.95, 0.90, 0.85, 0.80).
Everything else - AOI, expectation/target periods, sensors, transition
matrix, dampening_factor, posterior_leveler, modality, sensitivity - is
exactly the approved harvest/fire config, via each site script's
build_config(). recency_factor=1.00 is not rerun: it's numerically
identical to the existing harvest_2025_replay.csv/fire_2026_replay.csv
(discount() is an exact no-op at gamma=1.0 - see bulc.py), so those are
read back instead of spending another Earth Engine run on them.

Uses BULC-D_rebuild's public API only. No BULC-D_rebuild code is
modified, and no other parameter is tuned based on results.

Usage:
    conda run -n bulcd python experiments/replay_recency_sweep.py
"""

from __future__ import annotations

import csv
from pathlib import Path

import ee

ee.Initialize(project="bulcd-python-rebuild")

import replay_fire_2026 as fire
import replay_harvest_2025 as harvest
from _replay_common import load_rows, print_summary, run_replay, summarize

RECENCY_VALUES = [1.00, 0.95, 0.90, 0.85, 0.80]

SITES = [
    {
        "name": "harvest_2025",
        "module": harvest,
        # Known disturbance ONSET date - "calendar timing relative to the
        # known disturbance" is measured from here for the harvest case.
        "reference_date": harvest.WINDOW_START,
    },
    {
        "name": "fire_2026",
        "module": fire,
        # Exact ignition date unknown (see fire script's own docstring) -
        # measured from the known POST-fire confirmation date, a
        # deliberately conservative (lower-bound) latency reference, not
        # an invented ignition date.
        "reference_date": fire.KNOWN_POST_FIRE_DATE,
    },
]

OUTPUT_DIR = Path(__file__).parent / "output"
COMPARISON_CSV = OUTPUT_DIR / "recency_sweep_comparison.csv"


def main() -> None:
    comparison_rows = []
    for site in SITES:
        module = site["module"]
        for gamma in RECENCY_VALUES:
            if gamma == 1.00:
                # discount() is an exact no-op at gamma=1.0 - reuse the
                # already-run control CSV instead of spending another EE run.
                rows = load_rows(module.OUTPUT_CSV)
                print(f"{site['name']} gamma=1.00: reused {module.OUTPUT_CSV} (control, already run)")
            else:
                output_csv = OUTPUT_DIR / f"{site['name']}_recency_{gamma:.2f}.csv"
                config = module.build_config(gamma)
                rows, year_at_point = run_replay(
                    config=config,
                    point=module.POINT,
                    window_start=module.WINDOW_START,
                    window_end=module.WINDOW_END,
                    decrease_threshold=module.DECREASE_THRESHOLD,
                    output_csv=output_csv,
                )
                print(f"--- {site['name']} gamma={gamma:.2f} ---")
                print_summary(rows, output_csv, year_at_point)

            metrics = summarize(rows, site["reference_date"])
            comparison_rows.append({"site": site["name"], "recency_factor": gamma, **metrics})

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with COMPARISON_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(comparison_rows[0].keys()))
        writer.writeheader()
        writer.writerows(comparison_rows)
    print(f"\nWrote comparison table to {COMPARISON_CSV}")

    print("\nsite            gamma  crossed?  valid_post_obs  days_vs_ref  max_decrease  pre_change_false_pos")
    for r in comparison_rows:
        crossed = "yes" if r["crossing_date"] else "no"
        print(
            f"{r['site']:<15} {r['recency_factor']:.2f}  {crossed:<8}  "
            f"{str(r['valid_post_change_before_crossing']):<15} "
            f"{str(r['days_since_reference']):<11} "
            f"{r['max_decrease_probability']:.4f}      "
            f"{r['false_positive_pre_change']}"
        )


if __name__ == "__main__":
    main()
