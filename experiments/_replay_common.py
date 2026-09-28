"""Shared plumbing for BULC-D chronological replay experiments (Milestone 1).

Not part of the installable package - a small local helper so the
per-site replay scripts don't duplicate the getRegion()/CSV machinery
already proven in replay_bb_complex_fire.py. Uses only BULC-D_rebuild's
public API (bulcd.inputs.organize_inputs, bulcd.engine.run_bulcd,
bulcd.interpret.first_change_year) - no BULC-D_rebuild code is modified.
"""

from __future__ import annotations

import csv
import datetime
from pathlib import Path

import ee

from bulcd.engine import run_bulcd
from bulcd.interpret import first_change_year
from bulcd.inputs import organize_inputs

# bulc.py's fixed band-order/name contract (bulcd/engine.py's
# _DECISION_CLASS_NAMES); classification_stack's "class" band is the
# integer index into this list.
_CLASS_NAMES = ["decrease", "unchanged", "increase"]


def to_date(millis: float) -> datetime.date:
    return datetime.datetime.fromtimestamp(millis / 1000, datetime.timezone.utc).date()


def _region_table(
    image_collection: ee.ImageCollection, point: ee.Geometry, scale: int = 30
) -> dict[int, dict[str, float | None]]:
    """time (millis) -> {band_name: value}, via ONE getRegion() call at
    `point` covering every band the collection's images carry.

    Deliberately not one getRegion() call per band: each call forces
    Earth Engine to recompute the whole upstream graph (including
    organize_inputs()'s harmonic expectation fit) from scratch, and
    doing that 5+ times per run hit "User memory limit exceeded" in
    practice for the larger (multi-year, multi-sensor) expectation
    baselines these real-disturbance replays use, unlike the smaller
    single-sensor B&B plumbing test.
    """
    region = image_collection.getRegion(point, scale).getInfo()
    header, rows = region[0], region[1:]
    time_idx = header.index("time")
    skip = {"id", "longitude", "latitude", "time"}
    band_indices = {name: header.index(name) for name in header if name not in skip}
    return {row[time_idx]: {band: row[idx] for band, idx in band_indices.items()} for row in rows}


def phase_for(date: datetime.date, window_start: datetime.date, window_end: datetime.date) -> str:
    """pre_change (before window_start), disturbance_window (window_start..
    window_end inclusive), or post_change (after window_end). Callers
    decide what window_start/window_end mean for their disturbance - see
    each script's own comment, since "observed start/end" (harvest) and
    "known pre/post-fire dates" (fire) aren't quite the same kind of
    boundary."""
    if date < window_start:
        return "pre_change"
    if date > window_end:
        return "post_change"
    return "disturbance_window"


def run_replay(
    *,
    config,
    point: ee.Geometry,
    window_start: datetime.date,
    window_end: datetime.date,
    decrease_threshold: float,
    output_csv: Path,
) -> tuple[list[dict], dict]:
    """Runs organize_inputs()+run_bulcd() ONCE, reads probability_stack's
    per-Event trajectory at `point`, and writes the annotated CSV.

    Returns (rows, first_change_year_result) for the caller to summarize.
    """
    organized = organize_inputs(config)
    zscore_table = _region_table(organized.lof_zscore, point)

    result = run_bulcd(config)
    prob_table = _region_table(result.probability_stack, point)
    class_table = _region_table(result.classification_stack, point)

    times = sorted(prob_table)
    rows: list[dict] = []
    seen_first_post_change_valid = False
    seen_first_argmax_decrease = False
    seen_first_crossing = False
    for i, t in enumerate(times, start=1):
        date = to_date(t)
        zscore = zscore_table.get(t, {}).get("zscore")
        valid = zscore is not None
        phase = phase_for(date, window_start, window_end)
        decrease = prob_table[t]["decrease"]
        unchanged = prob_table[t]["unchanged"]
        increase = prob_table[t]["increase"]
        argmax_class = _CLASS_NAMES[int(class_table[t]["class"])]

        first_valid_post_change_evidence = (
            not seen_first_post_change_valid and valid and phase != "pre_change"
        )
        seen_first_post_change_valid = seen_first_post_change_valid or first_valid_post_change_evidence

        first_argmax_decrease = not seen_first_argmax_decrease and argmax_class == "decrease"
        seen_first_argmax_decrease = seen_first_argmax_decrease or first_argmax_decrease

        first_decrease_crossing = (
            not seen_first_crossing and decrease is not None and decrease > decrease_threshold
        )
        seen_first_crossing = seen_first_crossing or first_decrease_crossing

        rows.append(
            {
                "observation_date": date.isoformat(),
                "valid": valid,
                "phase": phase,
                "zscore": zscore,
                "decrease_probability": decrease,
                "unchanged_probability": unchanged,
                "increase_probability": increase,
                "argmax_class": argmax_class,
                "observation_number": i,
                "first_valid_post_change_evidence": first_valid_post_change_evidence,
                "first_argmax_decrease": first_argmax_decrease,
                "first_decrease_crossing": first_decrease_crossing,
            }
        )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    year_image = first_change_year(
        result.probability_stack, class_name="decrease", threshold=decrease_threshold
    )
    year_at_point = year_image.reduceRegion(ee.Reducer.first(), point, 30).getInfo()

    return rows, year_at_point


def load_rows(csv_path: Path) -> list[dict]:
    """Reads back a CSV written by run_replay(), restoring bool/float types."""
    with csv_path.open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    bool_fields = ["valid", "first_valid_post_change_evidence", "first_argmax_decrease", "first_decrease_crossing"]
    float_fields = ["zscore", "decrease_probability", "unchanged_probability", "increase_probability"]
    for row in rows:
        for field in bool_fields:
            row[field] = row[field] == "True"
        for field in float_fields:
            row[field] = float(row[field]) if row[field] not in ("", None) else None
        row["observation_number"] = int(row["observation_number"])
    return rows


def summarize(rows: list[dict], reference_date: datetime.date) -> dict:
    """Derives the recency_factor-sweep summary metrics from one run's rows:
    first crossing (if any), how many valid post-change observations that
    took, calendar timing relative to `reference_date` (site-specific - the
    known disturbance-onset date for harvest, the known post-fire date for
    fire), the max decrease_probability reached anywhere, and whether a
    false decrease>0.5 crossing occurred during the pre_change phase.
    """
    crossing = next((r for r in rows if r["first_decrease_crossing"]), None)
    valid_post_change_before_crossing = None
    days_since_reference = None
    if crossing is not None:
        valid_post_change_before_crossing = sum(
            1
            for r in rows
            if r["phase"] != "pre_change"
            and r["valid"]
            and r["observation_number"] <= crossing["observation_number"]
        )
        crossing_date = datetime.date.fromisoformat(crossing["observation_date"])
        days_since_reference = (crossing_date - reference_date).days

    max_decrease = max(r["decrease_probability"] for r in rows if r["decrease_probability"] is not None)

    false_positive_pre_change = any(
        r["phase"] == "pre_change" and r["decrease_probability"] is not None and r["decrease_probability"] > 0.5
        for r in rows
    )

    return {
        "crossing_date": crossing["observation_date"] if crossing else None,
        "crossing_phase": crossing["phase"] if crossing else None,
        "valid_post_change_before_crossing": valid_post_change_before_crossing,
        "days_since_reference": days_since_reference,
        "max_decrease_probability": max_decrease,
        "false_positive_pre_change": false_positive_pre_change,
    }


def print_summary(rows: list[dict], output_csv: Path, year_at_point: dict) -> None:
    n_valid = sum(1 for r in rows if r["valid"])
    print(f"Wrote {len(rows)} Events ({n_valid} valid) to {output_csv}")
    print(f"bulcd.interpret.first_change_year() at point: {year_at_point}")

    for label, key in [
        ("First valid post-change evidence", "first_valid_post_change_evidence"),
        ("First argmax flip to decrease", "first_argmax_decrease"),
        ("First decrease-probability > threshold crossing", "first_decrease_crossing"),
    ]:
        match = next((r for r in rows if r[key]), None)
        if match:
            print(
                f"{label}: {match['observation_date']} "
                f"(observation #{match['observation_number']}, phase={match['phase']})"
            )
        else:
            print(f"{label}: none in this run.")
