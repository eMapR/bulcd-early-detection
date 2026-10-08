# Legacy GUI chart exports (ground truth for the GUI-vs-Python equivalence test)

Chart CSVs exported by hand from the legacy GEE BULC-D GUI (V53e), one folder per
pixel. Filenames are kept exactly as exported, typos included, so they can be traced
back to the GUI; `experiments/legacy_gui_csv_compare.py` maps each to its chart.
Values are rounded to 3 decimals. Results: `docs/findings.md` (2026-10-04 and
2026-10-08 entries).

## Settings (identical for all three pixels)

Study area testsite; sensors L8 + L9 + S2 (Cross-Sensors, Cloud Score+ for S2); index NBR;
expectation 2024, target 2025; DOY 1–365; scene cloud 70 (not applied to S2 by the
legacy code); day step 3; modality constant + unimodal; z numerator 1; minimum
denominator 0.05; GUI-hardcoded BULC levelers 0.7/0.7/0.9, start class "unchanged"
(prior 0.1/0.8/0.1).

## Pixels

| Folder | Outcome | Coordinate (lon, lat) | Files |
|---|---|---|---|
| `pixel1/` | decrease (harvest-like drop) | −123.56922, 44.84283 | no suffix; no expectation-residual export |
| `pixel2/` | unchanged (stable) | −123.55299, 44.83292 as reported; the GUI actually sampled ≈ −123.552919, 44.832977 (10 m S2 pixel, see findings) | suffix `_g` |
| `pixel3/` | increase | −123.54330474162032, 44.847525314894625 (full precision) | suffix `_b` |

Charts per pixel: Expectation year vs fit (`nbr`, `fitted`), Target year vs fit,
Expectation residuals (`expectationDifferenceOptical`; pixels 2–3 only), Target
residuals (`targetDifference`), Bins (`band`), Probabilities (`drop`, `same`, `up`;
plotted one step late: row 1 is the starting prior).

Point provenance: the GUI's Charts mode receives all four linked maps
(`getChartResults(maps, ...)`) and handles clicks inside the unfetched
`HelperFunctions-BULCD` module. A listener on `maps[0]` alone can record a different click
than the one charted; a first pixel 3 coordinate (−123.54755, 44.83627) was such a
mismatch.
