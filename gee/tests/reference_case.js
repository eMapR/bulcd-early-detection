// Validation fixtures for the parity tests only; not deployed to the Code Editor.
//
// REFERENCE_CASE is the controlled legacy-GUI reference case: testsite, 2024
// expectation -> 2025 target, full year, L8+L9+S2, NBR, day step 3, the legacy
// GUI's hardcoded levelers. It is the JSON form of BULC-D_rebuild's
// gee/tests/cases.py legacy_reference(); run_app_parity.py checks the two are
// equal. With it, Python bulcd reproduces the legacy GUI exactly at the three
// REFERENCE_PIXELS (BULC-D_rebuild decision 0011).
const { PRODUCTION_TRANSITION_MATRIX } = require('../config.js');

const TESTSITE = 'projects/bulcd-python-rebuild/assets/testsite';

function period(year) {
  const sensors = {};
  for (const code of ['L8', 'L9', 'S2']) {
    sensors[code] = { enabled: true, first_year: year, last_year: year + 1, first_doy: 1, last_doy: 365,
                      cloud_cover_threshold: 70, s2_scene_cloud_threshold: null };
  }
  return { sensors };
}

const REFERENCE_CASE = {
  study_area: { aoi_asset: TESTSITE, mask_water: true, mask_non_forest: false },
  evidence: { expectation: period(2024), target: period(2025), day_step_size: 3 },
  reduction: { band: 'nbr' },
  modality: { constant: true, unimodal: true },
  sensitivity: { z_score_numerator_factor: 1.0, z_score_denominator_factor: 0.05 },
  bulc_advanced_params: { custom_transition_matrix: PRODUCTION_TRANSITION_MATRIX, dampening_factor: 0.7,
                          posterior_leveler: 0.9, initializing_leveler: 0.7, recency_factor: 1.0 },
};

// Controlled pixels that reproduce the legacy GUI exactly (lon, lat).
const REFERENCE_PIXELS = [
  { label: 'Pixel 1 (decrease)', lon: -123.56922, lat: 44.84283 },
  { label: 'Pixel 2 (unchanged)', lon: -123.552919, lat: 44.832977 },
  { label: 'Pixel 3 (increase)', lon: -123.54330474162032, lat: 44.847525314894625 },
];

module.exports = { TESTSITE, REFERENCE_CASE, REFERENCE_PIXELS, THRESHOLD: 0.5 };
