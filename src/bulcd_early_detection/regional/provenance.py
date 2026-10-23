"""What produced a regional product (no Earth Engine): the git state of this
repo and of BULC-D_rebuild, and the bulcd and earthengine-api versions."""

from __future__ import annotations

import subprocess
from importlib import metadata
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def git_state(path: Path) -> dict:
    """{"commit", "branch", "dirty"} of the git checkout at `path`, or {"error"}."""
    def git(*args):
        return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, check=True).stdout.strip()
    try:
        return {"commit": git("rev-parse", "HEAD"), "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
                "dirty": bool(git("status", "--porcelain", "--untracked-files=no"))}
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        return {"error": str(e)}


def _version(dist: str) -> str | None:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return None


def provenance() -> dict:
    import bulcd
    bulcd_path = Path(bulcd.__file__).resolve().parents[1]
    return {"bulcd_early_detection": git_state(REPO), "bulcd": git_state(bulcd_path) | {"version": _version("bulcd")},
            "earthengine_api": _version("earthengine-api")}
