"""Compact tables from experiments/output/sensor_consistency.csv.

    python experiments/summarize_sensor_consistency.py
"""

from __future__ import annotations

import csv
from pathlib import Path

CSV = Path(__file__).parent / "output" / "sensor_consistency.csv"
FIRE_START_DOY = 199  # 2026-07-18, replay_fire_2026.WINDOW_START


def main() -> None:
    rows = [r for r in csv.DictReader(CSV.open()) if r["status"] == "ok"]
    variants = list(dict.fromkeys(r["variant"] for r in rows))
    aois = list(dict.fromkeys(r["aoi"] for r in rows))
    get = {(r["aoi"], r["variant"]): r for r in rows}

    def table(title, fmt):
        print(f"\n{title}")
        print(f"{'':<24}" + "".join(f"{v:>19}" for v in variants))
        for a in aois:
            print(f"{a:<24}" + "".join(f"{fmt(get.get((a, v))):>19}" for v in variants))

    table("Decrease km^2 (forest-masked)", lambda r: r["decrease_km2"] if r else "-")
    table("Share of decrease first detected in the season's first 14 days",
          lambda r: (r["early_frac"] or "n/a") if r else "-")
    table("Median first-detection DOY (Jun 1 = 152)", lambda r: (r["median_first_doy"] or "n/a") if r else "-")

    def prefire(r):
        if not r or not r["doy_hist"]:
            return "-"
        h = [tuple(map(int, kv.split(":"))) for kv in r["doy_hist"].split()]
        n = sum(c for _, c in h)
        return f"{sum(c for d, c in h if d < FIRE_START_DOY) / n:.2f}"

    print("\nFire AOI: share of decrease pixels first detected BEFORE the fire (DOY < 199)")
    for v in variants:
        print(f"  {v:<20}{prefire(get.get(('fire_2026_wa', v)))}")


if __name__ == "__main__":
    main()
