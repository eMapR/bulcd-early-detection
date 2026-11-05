"""Three example pixels for the revised figures (read-only; live BULC-D point queries, nothing exported).

    python meeting_2026-10-28/scripts/fetch_examples.py

Picks the center of a uniform 5 x 5 patch (densest in 15 x 15) for each case, using the full-year results
(data/fullyear/) and Hansen loss year (data/reference.npz, an independent product):
  gap2024:  Hansen loss 2024; 2026 decrease under A, not under B
  late2025: Hansen loss 2025; 2026 decrease under A and B
  new2026:  no Hansen loss 2018-2025, Sentinel-2 NBR drop 2025 -> 2026; decrease under A and B
For each: all binned NBR observations 2018-2025 (config C's expectation) and the 2026 year-to-date
monitoring rows (observed, expected, P(decrease)) under A and B, full-year configs as in
expectation_compare_fullyear.py. Writes data/examples.json.
"""
import json

import ee
import numpy as np

from expectation_compare_fullyear import B, DATA, N, X0, Y1, config_for  # noqa: E402  (initializes ee)
from bulcd.inputs import organize_inputs  # noqa: E402

from bulcd_early_detection.pixel import pixel_history  # noqa: E402

P = np.load(DATA / "pilot.npz")
R = np.load(DATA / "reference.npz")
F = {k: np.load(DATA / "fullyear" / f"{k}.npz") for k in ("A26", "B26")}
land = P["condition_2026"] != 255
ly = R["hansen_lossyear"].astype(int)
dL = R["late2026_nbr"] - R["late2025_nbr"]
a, b = F["A26"]["outcome"] == 0, F["B26"]["outcome"] == 0
CASES = {"gap2024": land & (ly == 24) & a & ~b,
         "late2025": land & (ly == 25) & a & b,
         "new2026": land & (dL < -0.3) & ~((ly >= 18) & (ly <= 25)) & a & b}


def pick(m):
    best, score = None, -1
    for r in range(7, N - 7):
        for c in range(7, N - 7):
            if m[r, c] and m[r - 2:r + 3, c - 2:c + 3].all():
                s = m[r - 7:r + 8, c - 7:c + 8].sum()
                if s > score:
                    best, score = (r, c), s
    return best


def rows_json(rows):
    return [{**r, "date": r["date"].isoformat()} for r in rows]


out = {}
for case, m in CASES.items():
    r, c = pick(m)
    x, y = X0 + 30 * c + 15, Y1 - 30 * r - 15
    lon, lat = ee.Geometry.Point([x, y], "EPSG:5070").transform("EPSG:4326", 0.01).coordinates().getInfo()
    bx0, by1 = X0 + 30 * B * (c // B), Y1 - 30 * B * (r // B)   # the block the pixel was computed in
    hist = {k: rows_json(pixel_history(config_for(k + "26", bx0, by1), lon, lat)) for k in "AB"}
    cfg_c = config_for("C26", bx0, by1)
    band = cfg_c.reduction.band
    region = organize_inputs(cfg_c).expectation_collection.select(band).getRegion(
        ee.Geometry.Point([lon, lat]), 30).getInfo()
    head = region[0]
    past = sorted((int(row[head.index("time")]), row[head.index(band)]) for row in region[1:]
                  if row[head.index(band)] is not None)
    out[case] = {"row": r, "col": c, "lon": lon, "lat": lat, "hansen_lossyear": int(ly[r, c]) + 2000 if ly[r, c] else 0,
                 "outcome": {k: int(F[k + "26"]["outcome"][r, c]) for k in "AB"},
                 "past": [{"t": t, "nbr": v} for t, v in past], "monitoring": hist}
    print(case, r, c, round(lon, 5), round(lat, 5), "past obs", len(past), flush=True)
(DATA / "examples.json").write_text(json.dumps(out, indent=1))
