"""Detection episodes (pixel.detection_episodes / gee/inspector.js
detectionEpisodes) and the last-detection legend (no Earth Engine). The
image form (outputs.decrease_episode_bands) is checked live in
gee/tests/run_app_parity.py."""

import csv
import datetime
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from bulcd_early_detection import render
from bulcd_early_detection.pixel import detection_episodes, episode_notes, first_crossing

GEE = Path(__file__).parents[1] / "gee"
PINE_MOUNTAIN = Path(__file__).parents[1] / "experiments" / "output" / "pine_mountain_fit_order" / "monitoring_order1.csv"


def _rows(values, start=datetime.date(2024, 6, 1)):
    """One row per 4-day bin; None = no observation (bulcd carries the previous probability)."""
    out, p = [], 0.1
    for i, v in enumerate(values):
        p = p if v is None else v
        out.append({"date": start + datetime.timedelta(days=4 * i), "decrease": p, "zscore": v})
    return out


# name: (P(decrease) per bin, None = empty bin; expected [(start index, end index or None)])
CASES = {
    "never crosses": ([0.2, 0.4, 0.6, 0.65], []),
    "exactly at the threshold is not above": ([0.5, 0.65, 0.65, 0.3], []),
    "one episode open at season end": ([0.2, 0.7, 0.9, 0.9], [(1, None)]),
    "one episode that ends": ([0.2, 0.7, 0.9, 0.65, 0.1], [(1, 3)]),
    "two episodes (spring false, fall)": ([0.1, 0.8, 0.9, 0.4, 0.05, 0.05, 0.7, 0.9], [(1, 3), (6, None)]),
    "empty bins inside an episode don't split it": ([0.1, 0.8, None, None, 0.9, 0.2], [(1, 5)]),
    "empty bins between episodes don't start one": ([0.1, 0.8, 0.3, None, None, 0.9], [(1, 2), (5, None)]),
    "flicker counts every crossing": ([0.64, 0.66, 0.64, 0.66, 0.64, 0.66], [(1, 2), (3, 4), (5, None)]),
    "above from the first bin": ([0.7, 0.9], [(0, None)]),
}


@pytest.mark.parametrize("name", CASES)
def test_detection_episodes(name):
    values, expected = CASES[name]
    rows = _rows(values)
    eps = detection_episodes(rows, 0.65)
    assert [(e["start"], e["end"]) for e in eps] == \
        [(rows[a]["date"], None if b is None else rows[b]["date"]) for a, b in expected]
    # The first episode starts at the existing first-detected date.
    assert (eps[0]["start"] if eps else None) == first_crossing(rows, 0.65)


def test_episode_notes():
    rows = _rows([0.1, 0.8, 0.9, 0.4, 0.05, 0.7])
    assert episode_notes(rows, 0.65) == [
        "decrease detection episodes above 0.65: 2 (2024-06-05 to 2024-06-13 (ended); 2024-06-21 to season end "
        "(still above)); first detection 2024-06-05, last detection 2024-06-21"]
    assert episode_notes(_rows([0.1, 0.2]), 0.65) == []


def test_pine_mountain_pixel():
    """Robert's pixel, order 1 (docs/findings.md, 2026-10-13): spring snowmelt false
    detection Apr 17 - Jun 8, fire from Sep 24 to season end."""
    with open(PINE_MOUNTAIN) as f:
        rows = [{"date": datetime.date.fromisoformat(r["date"]), "decrease": float(r["decrease"])}
                for r in csv.DictReader(f)]
    d = datetime.date
    assert detection_episodes(rows, 0.65) == [{"start": d(2024, 4, 17), "end": d(2024, 6, 8)},
                                              {"start": d(2024, 9, 24), "end": None}]
    assert first_crossing(rows, 0.65) == d(2024, 4, 17)


def test_python_and_gee_episodes_and_legend_match():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    cases = {name: [{"date": str(r["date"]), "decrease": r["decrease"]} for r in _rows(values)]
             for name, (values, _) in CASES.items()}
    script = ("const i = require('./inspector.js'), o = require('./outputs.js'), cases = %s; "
              "const out = {}; for (const k in cases) out[k] = [i.detectionEpisodes(cases[k], 0.65), "
              "i.episodeNotes(cases[k], 0.65)]; "
              "console.log(JSON.stringify({out, legend: o.lastDetectionLegend([2024, 2025, 2026], 'Jun 1', 'Sep 30'), "
              "palette: o.LAST_DETECTION_PALETTE, episodes: [o.EPISODE_COLORS, o.EPISODE_LABELS]}))" % json.dumps(cases))
    js = json.loads(subprocess.check_output([node, "-e", script], cwd=GEE))
    for name, (values, _) in CASES.items():
        rows = _rows(values)
        py = [{"start": str(e["start"]), "end": None if e["end"] is None else str(e["end"])}
              for e in detection_episodes(rows, 0.65)]
        assert js["out"][name] == [py, episode_notes(rows, 0.65)], name
    assert [list(x) for x in render.last_detection_legend([2024, 2025, 2026], "Jun 1", "Sep 30").items()] == \
        [[label, color] for color, label in js["legend"]]
    assert js["palette"] == render.LAST_DETECTION_PALETTE
    assert js["episodes"] == [render.EPISODE_COLORS, render.EPISODE_LABELS]
