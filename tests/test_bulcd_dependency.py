"""Confirms this project can see the BULC-D core engine.

BULC-D (the Bayesian detection algorithm) lives in the separate
eMapR/BULC-D_rebuild repo and is installed as an ordinary dependency
(see pyproject.toml). This project never vendors or modifies it.
"""

import bulcd
from bulcd import bulc, engine, inputs
from bulcd.config.schema import BULCDConfig


def test_bulcd_is_importable():
    assert bulcd is not None


def test_bulcd_public_modules_are_importable():
    assert engine.run_bulcd is not None
    assert bulc.run_bulc is not None
    assert inputs.organize_inputs is not None
    assert BULCDConfig is not None
