"""Legacy GUI vs. Python rebuild: one-pixel equivalence diagnostic.

Reference case (a controlled run of the original BULC-D GEE GUI, V53e):
    AOI projects/bulcd-python-rebuild/assets/testsite, pixel (-123.56922, 44.84283)
    Cross-Sensors on; L8 + L9 + S2; NBR; day step 3; constant + unimodal;
    numerator 1; minimum denominator 0.05
    expectation 2024 DOY 1-365, target 2025 DOY 1-365, image cloud threshold 70
    BULC parameters: the GUI's hardcoded getBULCParameterDictionary()
    (legacy/6003.3c): production matrix, initializing/transition/posterior
    levelers 0.7/0.7/0.9, base land cover = "unchanged".

Investigation only: nothing in bulcd is tuned or changed. Everything comes
from bulcd itself, including a few private helpers used read-only to expose
intermediate values (expectation-period fit, bins). One independent numpy
re-derivation of the legacy formulas from the same binned observations
(`legacy_recon_*` columns) separates "different inputs" from "different
math": it uses the legacy time variable (fracDOY = 0-based day of year of
the bin end / 365), not bulcd's years-since-1970.

Outputs (experiments/output/legacy_gui_equivalence/):
    raw_observations.csv     every cloud-masked scene at the pixel, per sensor,
                             incl. S2 scenes bulcd's 70% scene filter drops
                             (legacy applies no S2 scene filter, see findings)
    expectation_bins.csv     2024 bins: observed, fitted, residual
    target_bins.csv          2025 bins: observed, fitted, residual, denominator,
                             z, bin, transition row, P(decrease/same/increase)
    summary.txt              fit coefficients, SD, divergence checks

    python experiments/legacy_gui_equivalence.py
"""

from __future__ import annotations

import csv
import datetime as dt
import math
from pathlib import Path

import ee

ee.Initialize(project="bulcd-python-rebuild")

import numpy as np
from bulcd.config.schema import (
    BULCAdvancedParams, BULCDConfig, EvidenceConfig, EvidencePeriodConfig, ModalityConfig,
    ReductionConfig, SensitivityConfig, SensorEvidenceConfig, StudyAreaConfig,
)
from bulcd.engine import _bin_zscore, run_bulcd
from bulcd.inputs import (
    _add_fitted_band, _add_harmonic_terms, _fit_expectation_model, _landsat_evidence, _s2_evidence,
    organize_inputs, resolve_study_area,
)

from bulcd_early_detection.config import PRODUCTION_TRANSITION_MATRIX

LON, LAT = -123.56922, 44.84283
AOI = "projects/bulcd-python-rebuild/assets/testsite"
SENSORS = ("L8", "L9", "S2")
# Legacy getBULCParameterDictionary() (legacy/6003.3c lines 63-65).
INIT_LEVELER, TRANSITION_LEVELER, POSTERIOR_LEVELER = 0.7, 0.7, 0.9
CLASSES = ("decrease", "unchanged", "increase")
OUT = Path(__file__).parent / "output" / "legacy_gui_equivalence"
# Sampling grid. The legacy chart module (HelperFunctions-BULCD.getChartResults)
# is not fetched, so its scale/CRS is unknown; ui.Chart defaults sample in
# EPSG:4326 at the given scale. UTM 30 m is this repo's product grid.
GRIDS = {"wgs84_30m": ("EPSG:4326", 30), "utm_30m": ("EPSG:32610", 30)}


def build_config() -> BULCDConfig:
    def period(year):
        return EvidencePeriodConfig(sensors={
            s: SensorEvidenceConfig(enabled=True, first_year=year, last_year=year + 1, first_doy=1, last_doy=365,
                                    cloud_cover_threshold=70)
            for s in SENSORS})
    return BULCDConfig(
        study_area=StudyAreaConfig(aoi_asset=AOI, mask_water=True, mask_non_forest=False),
        evidence=EvidenceConfig(expectation=period(2024), target=period(2025), day_step_size=3),
        reduction=ReductionConfig(band="nbr"),
        modality=ModalityConfig(constant=True, unimodal=True),
        sensitivity=SensitivityConfig(z_score_numerator_factor=1.0, z_score_denominator_factor=0.05),
        bulc_advanced_params=BULCAdvancedParams(
            custom_transition_matrix=PRODUCTION_TRANSITION_MATRIX, dampening_factor=TRANSITION_LEVELER,
            posterior_leveler=POSTERIOR_LEVELER, initializing_leveler=INIT_LEVELER, recency_factor=1.0),
    )


def region(collection: ee.ImageCollection, crs: str, scale: int) -> list[dict]:
    rows = collection.getRegion(ee.Geometry.Point([LON, LAT]), scale, crs).getInfo()
    header = rows[0]
    return [dict(zip(header, r)) for r in rows[1:]]


def date_of(millis) -> dt.datetime:
    return dt.datetime.fromtimestamp(millis / 1000, dt.timezone.utc)


def raw_observations(config: BULCDConfig, crs: str, scale: int) -> list[dict]:
    """Every scene per sensor/year at the pixel, cloud-masked by bulcd's own
    per-sensor functions. S2 is queried at scene threshold 100 and flagged
    with whether bulcd's <=70 CLOUDY_PIXEL_PERCENTAGE filter would keep it."""
    area = resolve_study_area(config.study_area)
    out = []
    for label, p in (("expectation", config.evidence.expectation), ("target", config.evidence.target)):
        for s, cfg in p.sensors.items():
            if s == "S2":
                loose = SensorEvidenceConfig(**{**cfg.__dict__, "cloud_cover_threshold": 100})
                coll = _s2_evidence(loose, area, "nbr")
                coll = coll.map(lambda im: im.addBands(ee.Image.constant(im.getNumber("CLOUDY_PIXEL_PERCENTAGE")).rename("scene_cloud").toFloat()))
            else:
                coll = _landsat_evidence(s, cfg, area, "nbr")
                coll = coll.map(lambda im: im.addBands(ee.Image.constant(im.getNumber("CLOUD_COVER")).rename("scene_cloud").toFloat()))
            for r in region(coll.select(["nbr", "scene_cloud"]), crs, scale):
                cloud = r["scene_cloud"]
                kept = cloud is not None and cloud <= 70 if s == "S2" else True
                out.append({"period": label, "datetime_utc": date_of(r["time"]).isoformat(timespec="seconds"),
                            "sensor": s, "scene_id": r["id"], "scene_cloud_pct": cloud, "nbr": r["nbr"],
                            "clear_at_pixel": r["nbr"] is not None, "in_bulcd_scene_filter": kept})
    return sorted(out, key=lambda r: r["datetime_utc"])


def legacy_fit(dates: list[dt.datetime], obs: list[float | None]):
    """Legacy afn_fitHarmonicToCollection + afn_summarizeICSimply("StdDev"),
    with legacy's time variable fracDOY = end.getRelative('day','year') / 365."""
    f = np.array([(d.timetuple().tm_yday - 1) / 365 for d in dates])
    X = np.column_stack([np.ones_like(f), np.cos(2 * math.pi * f), np.sin(2 * math.pi * f)])
    y = np.array([np.nan if v is None else v for v in obs], dtype=float)
    ok = ~np.isnan(y)
    beta, *_ = np.linalg.lstsq(X[ok], y[ok], rcond=None)
    resid = y[ok] - X[ok] @ beta
    return beta, float(np.std(resid, ddof=1)), X


def legacy_bulc(zs: list[float | None], cuts: list[float], matrix: list[list[float]]):
    """Legacy BULC-Minimal-Module-107 fold: transition row leveled
    (row*0.7 + 0.1), Bayes on valid pixels, posterior leveled (p*0.9 + 1/30),
    masked steps carry the prior. Start = 0.7*one-hot(unchanged) + 0.1."""
    p = np.array([0.0, 1.0, 0.0]) * INIT_LEVELER + (1 - INIT_LEVELER) / 3
    out = []
    for z in zs:
        if z is not None:
            b = 1 + sum(z > c for c in cuts)
            L = np.array(matrix[b - 1]) * TRANSITION_LEVELER + (1 - TRANSITION_LEVELER) / 3
            p = p * L / (p @ L)
            p = p * POSTERIOR_LEVELER + (1 - POSTERIOR_LEVELER) / 3
        out.append(p.copy())
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    config = build_config()
    cuts, matrix = config.bin_cuts, config.bulc_advanced_params.custom_transition_matrix
    organized = organize_inputs(config)
    fit = _fit_expectation_model(organized.expectation_collection, config.modality, "nbr")
    exp_fitted = organized.expectation_collection.map(_add_harmonic_terms).map(
        lambda im: _add_fitted_band(im, fit.coefficients, fit.regressor_names))
    tgt = organized.expectation_fitted_collection  # target bins + 'fitted'
    zs = organized.lof_zscore
    bins = zs.map(lambda im: _bin_zscore(im.select("zscore"), cuts).updateMask(im.select("zscore").mask())
                  .copyProperties(im, ["system:time_start"]))
    probs = run_bulcd(config).probability_stack
    summary = []

    for grid, (crs, scale) in GRIDS.items():
        gdir = OUT / grid
        gdir.mkdir(exist_ok=True)
        raw = raw_observations(config, crs, scale)
        write(gdir / "raw_observations.csv", raw)

        e = sorted(region(exp_fitted.select(["nbr", "fitted"]), crs, scale), key=lambda r: r["time"])
        t = {r["time"]: r for r in region(tgt.select(["nbr", "fitted"]), crs, scale)}
        z = {r["time"]: r for r in region(zs, crs, scale)}
        b = {r["time"]: r for r in region(bins, crs, scale)}
        p = {r["time"]: r for r in region(probs, crs, scale)}
        coef = region(ee.ImageCollection([fit.coefficients.addBands(fit.residual_stddev).set("system:time_start", 0)]), crs, scale)[0]
        sd = coef["residual_stddev"]
        denom = max(sd, 0.05)

        e_dates = [date_of(r["time"]) for r in e]
        beta, l_sd, _ = legacy_fit(e_dates, [r["nbr"] for r in e])
        t_times = sorted(t)
        t_dates = [date_of(k) for k in t_times]
        f_t = np.array([(d.timetuple().tm_yday - 1) / 365 for d in t_dates])
        l_fit_t = beta[0] + beta[1] * np.cos(2 * math.pi * f_t) + beta[2] * np.sin(2 * math.pi * f_t)
        l_denom = max(l_sd, 0.05)
        l_z = [None if t[k]["nbr"] is None else float(np.clip((t[k]["nbr"] - l_fit_t[i]) / l_denom, -10, 10))
               for i, k in enumerate(t_times)]
        l_p = legacy_bulc(l_z, cuts, matrix)
        f_e = np.array([(d.timetuple().tm_yday - 1) / 365 for d in e_dates])
        l_fit_e = beta[0] + beta[1] * np.cos(2 * math.pi * f_e) + beta[2] * np.sin(2 * math.pi * f_e)

        # Which sensors contributed to each bin (from the raw scenes bulcd keeps).
        def contributors(period, end):
            start = end - dt.timedelta(days=3)
            return "+".join(sorted({r["sensor"] for r in raw if r["period"] == period and r["clear_at_pixel"]
                                    and r["in_bulcd_scene_filter"]
                                    and start <= dt.datetime.fromisoformat(r["datetime_utc"]) < end}))

        def dropped_s2(period, end):
            start = end - dt.timedelta(days=3)
            return "+".join(r["datetime_utc"][:10] for r in raw if r["period"] == period and r["sensor"] == "S2"
                            and r["clear_at_pixel"] and not r["in_bulcd_scene_filter"]
                            and start <= dt.datetime.fromisoformat(r["datetime_utc"]) < end)

        exp_rows = []
        for i, r in enumerate(e):
            end = e_dates[i]
            exp_rows.append({
                "bin_end_utc": end.date().isoformat(), "bin_start": (end - dt.timedelta(days=3)).date().isoformat(),
                "sensors": contributors("expectation", end), "s2_clear_but_scene_filtered": dropped_s2("expectation", end),
                "observed_nbr": r["nbr"], "fitted_nbr": r["fitted"],
                "residual": None if r["nbr"] is None else r["nbr"] - r["fitted"],
                "legacy_recon_fitted": float(l_fit_e[i]),
            })
        write(gdir / "expectation_bins.csv", exp_rows)

        tgt_rows = []
        for i, k in enumerate(t_times):
            end, obs, fitted = t_dates[i], t[k]["nbr"], t[k]["fitted"]
            zz = z.get(k, {}).get("zscore")
            bb = b.get(k, {}).get("bin")
            row = matrix[int(bb) - 1] if bb is not None else None
            tgt_rows.append({
                "bin_end_utc": end.date().isoformat(), "bin_start": (end - dt.timedelta(days=3)).date().isoformat(),
                "sensors": contributors("target", end), "s2_clear_but_scene_filtered": dropped_s2("target", end),
                "observed_nbr": obs, "fitted_nbr": fitted,
                "residual": None if obs is None else obs - fitted,
                "denominator": denom, "zscore": zz, "bin": None if bb is None else int(bb),
                "transition_row_raw": "" if row is None else "/".join(f"{v:.2f}" for v in row),
                "transition_row_leveled": "" if row is None else "/".join(
                    f"{v * TRANSITION_LEVELER + (1 - TRANSITION_LEVELER) / 3:.3f}" for v in row),
                **{f"P_{c}": p[k][c] for c in CLASSES},
                "legacy_recon_fitted": float(l_fit_t[i]), "legacy_recon_z": l_z[i],
                **{f"legacy_recon_P_{c}": float(l_p[i][j]) for j, c in enumerate(CLASSES)},
            })
        write(gdir / "target_bins.csv", tgt_rows)

        n_exp = sum(r["observed_nbr"] is not None for r in exp_rows)
        n_tgt = sum(r["observed_nbr"] is not None for r in tgt_rows)
        dfit = max(abs(r["fitted_nbr"] - r["legacy_recon_fitted"]) for r in tgt_rows)
        dp = max(abs(r[f"P_{c}"] - r[f"legacy_recon_P_{c}"]) for r in tgt_rows for c in CLASSES)
        n_drop = sum(1 for r in raw if r["sensor"] == "S2" and r["clear_at_pixel"] and not r["in_bulcd_scene_filter"])
        first_dec = next((r["bin_end_utc"] for r in tgt_rows if r["P_decrease"] > 0.5), None)
        summary += [
            f"[{grid}] {crs} {scale} m",
            f"  bins: expectation {len(exp_rows)} ({n_exp} with data), target {len(tgt_rows)} ({n_tgt} with data)",
            f"  bulcd coefficients: " + ", ".join(f"{n}={coef[n]:.4f}" for n in fit.regressor_names),
            f"  bulcd residual SD = {sd:.4f}; denominator = max(SD, 0.05) = {denom:.4f}",
            f"  legacy-recon (fracDOY) coefficients: constant={beta[0]:.4f}, cos={beta[1]:.4f}, sin={beta[2]:.4f}; SD = {l_sd:.4f}",
            f"  max |bulcd fitted - legacy-recon fitted| over target bins = {dfit:.5f}",
            f"  max |bulcd P - legacy-recon P| over target bins = {dp:.5f}",
            f"  clear S2 scenes legacy would use but bulcd's scene filter drops: {n_drop}",
            f"  first bin with P(decrease) > 0.5: {first_dec}; final P = "
            + "/".join(f"{tgt_rows[-1][f'P_{c}']:.3f}" for c in CLASSES),
        ]
    (OUT / "summary.txt").write_text("\n".join(summary) + "\n")
    print("\n".join(summary))


def write(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
