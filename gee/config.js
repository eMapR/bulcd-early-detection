// Fixed, read-only configuration for the GEE Early Detection app (Milestone 1).
//
// REFERENCE_CASE is the controlled legacy-GUI reference case: testsite, 2024
// expectation -> 2025 target, full year, L8+L9+S2, NBR, day step 3, the legacy
// GUI's hardcoded levelers. It is the JSON form of BULC-D_rebuild's
// gee/tests/cases.py legacy_reference() (dataclasses.asdict(BULCDConfig), the
// form bulcd.js takes); gee/tests/run_app_parity.py checks the two are equal.
// With it, Python bulcd reproduces the legacy GUI exactly at the three
// REFERENCE_PIXELS (BULC-D_rebuild decision 0011).
//
// Plain ES5 (Code Editor compatible). No Earth Engine calls here.

function period(year) {
  var sensors = {};
  ['L8', 'L9', 'S2'].forEach(function (code) {
    sensors[code] = {enabled: true, first_year: year, last_year: year + 1, first_doy: 1, last_doy: 365,
                     cloud_cover_threshold: 70, s2_scene_cloud_threshold: null};
  });
  return {sensors: sensors};
}

// The legacy app's default transition matrix (rows = z-score bins, columns =
// decrease / unchanged / increase), as in BULC-D_rebuild configs/cell_8c_comparison.yaml.
var LEGACY_TRANSITION_MATRIX = [
  [0.83, 0.08, 0.08],
  [0.66, 0.24, 0.08],
  [0.53, 0.37, 0.08],
  [0.14, 0.76, 0.08],
  [0.08, 0.83, 0.08],
  [0.08, 0.83, 0.08],
  [0.08, 0.76, 0.14],
  [0.08, 0.37, 0.53],
  [0.08, 0.24, 0.66],
  [0.08, 0.08, 0.83]
];

var REFERENCE_CASE = {
  name: 'Legacy reference case: testsite, 2024 expectation -> 2025 target',
  bulcd: {
    study_area: {aoi_asset: 'projects/bulcd-python-rebuild/assets/testsite', mask_water: true,
                 mask_non_forest: false},
    evidence: {expectation: period(2024), target: period(2025), day_step_size: 3},
    reduction: {band: 'nbr'},
    modality: {constant: true, unimodal: true},
    sensitivity: {z_score_numerator_factor: 1.0, z_score_denominator_factor: 0.05},
    bulc_advanced_params: {custom_transition_matrix: LEGACY_TRANSITION_MATRIX, dampening_factor: 0.7,
                           posterior_leveler: 0.9, initializing_leveler: 0.7, recency_factor: 1.0}
  },
  // Early Detection's decision rule (outputs.py): a change class is mapped where
  // its final probability exceeds this.
  decision_threshold: 0.5,
  map_center: {lon: -123.552, lat: 44.834, zoom: 13},
  // Controlled pixels that reproduce the legacy GUI exactly (lon, lat).
  reference_pixels: [
    {label: 'Pixel 1 (decrease)', lon: -123.56922, lat: 44.84283},
    {label: 'Pixel 2 (unchanged)', lon: -123.552919, lat: 44.832977},
    {label: 'Pixel 3 (increase)', lon: -123.54330474162032, lat: 44.847525314894625}
  ]
};

exports.REFERENCE_CASE = REFERENCE_CASE;
