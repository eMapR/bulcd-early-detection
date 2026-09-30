"""North Cascades sensor-consistency experiment for the first-detected-season product.

Question: is the large North Cascades "first detected in 2024" class (and the
recurring early-season dip below expectation) tied to a particular sensor mix?

Everything is identical to the notebooks' timing setup - fixed 2018-2023
expectation, independent 2024/2025/2026 single-season runs from even odds,
same window, masks, sensitivity, threshold, transition matrix, dampening,
leveler and export grid - except the expectation/monitoring sensor sets:

    l8_l8        L8        -> L8
    l8_l89       L8        -> L8+L9
    l8_l89s2     L8        -> L8+L9+S2   (current configuration, re-run so every
                                         variant reads the same input versions)
    s2_s2        S2        -> S2
    l8s2_l89s2   L8+S2     -> L8+L9+S2   (may hit Earth Engine's memory limit)

Exports (one per variant x season) go to
projects/bulcd-python-rebuild/assets/north_cascades/noca_sens_<tag>_timing<year>_base2018_2023_v1_all.
No BULC-D code or parameter is changed.

    python experiments/noca_sensor_timing.py            # start exports and wait
"""

from __future__ import annotations

import dataclasses
import time

import ee

ee.Initialize(project="bulcd-python-rebuild")

from bulcd_early_detection import outputs  # noqa: E402
from bulcd_early_detection.config import MonitoringControls, build_config  # noqa: E402

FOLDER = "projects/bulcd-python-rebuild/assets/north_cascades"
SEASONS = (2024, 2025, 2026)
VARIANTS = {
    "l8_l8": (("L8",), ("L8",)),
    "l8_l89": (("L8",), ("L8", "L9")),
    "l8_l89s2": (("L8",), ("L8", "L9", "S2")),
    "s2_s2": (("S2",), ("S2",)),
    "l8s2_l89s2": (("L8", "S2"), ("L8", "L9", "S2")),
}


def run_name(tag: str, year: int) -> str:
    return f"noca_sens_{tag}_timing{year}_base2018_2023_v1"


def config_for(area: outputs.StudyArea, year: int, expectation: tuple[str, ...], monitoring: tuple[str, ...]):
    """The notebooks' timing config for one season, with only the sensor sets replaced
    (each sensor copies the default sensor settings: years, window, cloud prefilter)."""
    config = build_config(MonitoringControls(monitoring_year=year, baseline_last_year=2023), **area.aoi)
    exp_template = config.evidence.expectation.sensors["L8"]
    mon_template = config.evidence.target.sensors["L8"]
    config.evidence.expectation.sensors = {s: dataclasses.replace(exp_template) for s in expectation}
    config.evidence.target.sensors = {s: dataclasses.replace(mon_template) for s in monitoring}
    return config


def main() -> None:
    area = outputs.north_cascades()
    tasks = []
    for tag, (expectation, monitoring) in VARIANTS.items():
        for year in SEASONS:
            config = config_for(area, year, expectation, monitoring)
            controls = MonitoringControls(monitoring_year=year, baseline_last_year=2023)
            tasks += outputs.export_study_area(controls, build_config, area, FOLDER, run_name(tag, year),
                                               config=config, image_fn=outputs.detection_timing_image)
    t0 = time.time()
    print(f"started {len(tasks)} exports at {time.strftime('%H:%M:%S')}", flush=True)
    print(outputs.wait_for(tasks, poll_seconds=60), f"runtime_min {(time.time() - t0) / 60:.1f}")


if __name__ == "__main__":
    main()
