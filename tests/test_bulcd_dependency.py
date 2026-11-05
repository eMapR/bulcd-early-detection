"""Confirms this project can see the BULC-D core engine.

BULC-D (the Bayesian detection algorithm) lives in the separate
eMapR/BULC-D_rebuild repo and is installed as an ordinary dependency
(see pyproject.toml). This project never vendors or modifies it.
"""

import dataclasses
import subprocess
from pathlib import Path

import pytest

import bulcd
from bulcd import bulc, engine, inputs
from bulcd.config.schema import BULCDConfig, SensorEvidenceConfig

# BULC-D_rebuild decision 0011, the engine version this project is validated
# against (pyproject.toml `engine` extra, README "Relationship to BULC-D_rebuild").
DECISION_0011 = "8e9c5d52e21b5ec57ccc2ad3328b5e7ce0b21bbb"


def test_bulcd_is_importable():
    assert bulcd is not None


def test_bulcd_public_modules_are_importable():
    assert engine.run_bulcd is not None
    assert bulc.run_bulc is not None
    assert inputs.organize_inputs is not None
    assert BULCDConfig is not None


def test_bulcd_includes_decision_0011():
    """Decision 0011 made the legacy Sentinel-2 scene behavior the default: the
    scene-cloud filter became the opt-in s2_scene_cloud_threshold (default None).
    An engine without it (e.g. BULC-D_rebuild's main) gives different results."""
    fields = {f.name: f for f in dataclasses.fields(SensorEvidenceConfig)}
    assert "s2_scene_cloud_threshold" in fields, "bulcd predates decision 0011 (BULC-D_rebuild 8e9c5d5)"
    assert fields["s2_scene_cloud_threshold"].default is None


def test_bulcd_checkout_contains_the_pinned_commit():
    """For a git checkout of bulcd (editable install), the pinned commit is in its history."""
    root = Path(bulcd.__file__).resolve().parents[1]
    if not (root / ".git").exists():
        pytest.skip("bulcd is not a git checkout")
    r = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", DECISION_0011, "HEAD"],
                       capture_output=True, text=True)
    assert r.returncode == 0, f"{root} does not contain {DECISION_0011[:7]} (decision 0011): {r.stderr.strip()}"
