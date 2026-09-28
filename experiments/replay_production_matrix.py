"""Real production transition-matrix baseline, recency_factor=1.0 (off).

Follow-up to docs/findings.md's provenance investigation: every replay
so far used Willis (2022)'s hand-picked ILLUSTRATIVE thesis matrix, not
BULC-D's real production values. `PRODUCTION_TRANSITION_MATRIX` below is
transcribed verbatim from `../BULC-D_rebuild/configs/cell_8c_comparison.yaml`,
itself read live from the legacy GUI's own Console output for cell 8C
(BULC-D_rebuild's docs/findings.md "Real production BULC-D parameters",
2026-08-10) - not something derived or adjusted here.

Only `custom_transition_matrix` changes from the approved harvest/fire
configs. `recency_factor=1.0` (off) deliberately, to get a clean
production-evidence baseline before testing any rebuild-specific
extension on top of it. Same sites, expectation/target periods, sensors,
DOY window, bin_cuts, dampening_factor=0.5, posterior_leveler, and
0.5 interpretation threshold as every prior replay - see
replay_harvest_2025.py/replay_fire_2026.py's build_config().

Uses BULC-D_rebuild's public API only. No BULC-D_rebuild code is
modified, and no other parameter is tuned.

Usage:
    conda run -n bulcd python experiments/replay_production_matrix.py
"""

from __future__ import annotations

from pathlib import Path

import ee

ee.Initialize(project="bulcd-python-rebuild")

import replay_fire_2026 as fire
import replay_harvest_2025 as harvest
from _replay_common import print_summary, run_replay, summarize

# Verbatim from ../BULC-D_rebuild/configs/cell_8c_comparison.yaml
# (custom_transition_matrix: REAL, read live from the legacy GUI Console
# for cell 8C - see that repo's docs/findings.md "Real production
# BULC-D parameters"). Rows sum to ~0.98-0.99 (real conditional
# probabilities), unlike Willis's hand-picked weights.
PRODUCTION_TRANSITION_MATRIX = [
    [0.83, 0.08, 0.08],
    [0.66, 0.24, 0.08],
    [0.53, 0.37, 0.08],
    [0.14, 0.76, 0.08],
    [0.08, 0.83, 0.08],
    [0.08, 0.83, 0.08],
    [0.08, 0.76, 0.14],
    [0.08, 0.37, 0.53],
    [0.08, 0.24, 0.66],
    [0.08, 0.08, 0.83],
]

RECENCY_FACTOR = 1.0

SITES = [
    {
        "name": "harvest_2025",
        "module": harvest,
        "reference_date": harvest.WINDOW_START,
    },
    {
        "name": "fire_2026",
        "module": fire,
        "reference_date": fire.KNOWN_POST_FIRE_DATE,
    },
]

OUTPUT_DIR = Path(__file__).parent / "output"


def main() -> None:
    for site in SITES:
        module = site["module"]
        output_csv = OUTPUT_DIR / f"{site['name']}_production_matrix.csv"
        config = module.build_config(RECENCY_FACTOR, PRODUCTION_TRANSITION_MATRIX)
        rows, year_at_point = run_replay(
            config=config,
            point=module.POINT,
            window_start=module.WINDOW_START,
            window_end=module.WINDOW_END,
            decrease_threshold=module.DECREASE_THRESHOLD,
            output_csv=output_csv,
        )
        print(f"\n--- {site['name']} (production matrix, recency_factor={RECENCY_FACTOR}) ---")
        print_summary(rows, output_csv, year_at_point)
        metrics = summarize(rows, site["reference_date"])
        print(f"Summary: {metrics}")


if __name__ == "__main__":
    main()
