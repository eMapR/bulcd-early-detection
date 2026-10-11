// Configuration for the GEE Early Detection app: the user-facing controls ->
// a bulcd config (the JSON form of BULCDConfig that bulcd.js takes).
//
// buildConfig(controls, aoi) mirrors the interactive notebook
// (src/bulcd_early_detection/config.py build_config() plus app.py
// EarlyDetectionApp.build()); RANGES are the notebook's widget limits.
// APP_DEFAULTS are the settings the app opens with: the original BULC-D GUI's
// values wherever it had a default (gee/tests/controls_check.js checks them
// against the legacy source), the notebook's elsewhere.
// gee/tests/run_app_parity.py checks the result against the Python app's own
// build() for the same settings.
//
// Plain ES5 (Code Editor compatible). No Earth Engine calls here.

// The legacy app's default transition matrix (rows = z-score bins, columns =
// decrease / unchanged / increase), as in BULC-D_rebuild configs/cell_8c_comparison.yaml.
var PRODUCTION_TRANSITION_MATRIX = [
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

// ---------------------------------------------------------------- notebook controls

// config.py: permissive scene-level prefilter (per-pixel cloud masking does the
// screening); expectation always Landsat 8 only (a multi-year L8+S2 fit ran out of
// Earth Engine memory); monitoring sensors selectable.
var CLOUD_COVER_THRESHOLD = 70;
var BASELINE_SENSORS = ['L8'];
var MONITORING_SENSORS = ['L8', 'L9', 'S2'];
var SENSOR_LABELS = {L8: 'Landsat 8', L9: 'Landsat 9', S2: 'Sentinel-2'};
var MAX_TIMING_SEASONS = 3;

// Starting probabilities, as in the original BULC-D GUI (initializingLeveler 0.7
// applied to "unchanged"): 0.1 decrease / 0.8 unchanged / 0.1 increase. Fixed;
// not a control.
var INITIALIZING_LEVELER = 0.7;

// The settings the app opens with.
//   Original BULC-D GUI defaults: sensitivity (ZScoreNumeratorFactor 1),
//   separate decrease/increase thresholds (its drop 0.65 / gain 0.75 sliders),
//   dampening (transitionLeveler 0.7), posterior leveler (posteriorLeveler 0.9),
//   no forest mask, water masked. (Also fixed above/in bulcd: INITIALIZING_LEVELER,
//   the transition matrix, bin cuts, z-score denominator 0.05, NBR, constant +
//   one annual cycle.)
//   No original default, so these are Early Detection choices: the original GUI
//   left the sensors, expectation and target years, days of year and cloud cover
//   blank for the user to enter.
// src/bulcd_early_detection/app.py LEGACY_DEFAULTS holds the same values.
var APP_DEFAULTS = {
  expectation_first: 2018, expectation_last: 2023,  // Early Detection choice
  monitoring_year: 2026,                            // Early Detection choice
  season_start: '06-01', season_end: '09-30',       // MM-DD; Early Detection choice
  sensitivity: 1.0,                                 // original GUI
  decrease_threshold: 0.65,                         // original GUI (drop)
  increase_threshold: 0.75,                         // original GUI (gain)
  timing: true,                                     // also map the first-detected season
  dampening: 0.7,                                   // original GUI
  posterior_leveler: 0.9,                           // original GUI
  sensors: {L8: true, L9: true, S2: true},          // monitoring sensors; Early Detection choice
  mask_forest: false,                               // original GUI: no forest mask
  mask_water: true,                                 // original GUI: water masked
  allow_large: false
};

// app.py widget limits.
var RANGES = {
  expectation_years: [2016, 2025],
  monitoring_years: [2024, 2025, 2026],
  sensitivity: {min: 0.25, max: 3.0, step: 0.05},
  threshold: {min: 0.5, max: 0.99, step: 0.01},     // each of the decrease and increase thresholds
  dampening: {min: 0.1, max: 1.0, step: 0.05},
  posterior_leveler: {min: 0.5, max: 1.0, step: 0.05}
};

var MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
var DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];  // Feb 29 left out, as in app.py

function copy(obj) {
  return JSON.parse(JSON.stringify(obj));
}

function round2(x) {
  return Math.round(x * 100) / 100;
}

// 1-based day of year of MM-DD in `year` (config.py MonitoringControls._doy).
function dayOfYear(year, monthDay) {
  var p = monthDay.split('-');
  return (Date.UTC(year, Number(p[0]) - 1, Number(p[1])) - Date.UTC(year, 0, 1)) / 86400000 + 1;
}

function monthDayLabel(monthDay) {
  var p = monthDay.split('-');
  return MONTH_NAMES[Number(p[0]) - 1] + ' ' + Number(p[1]);
}

// The settings problem that blocks a run, or null (app.py _describe() and
// MonitoringControls.__post_init__).
function validateControls(c) {
  if (c.expectation_first > c.expectation_last) {
    return 'The expectation years must run forward. Now: ' + c.expectation_first + '-' + c.expectation_last + '.';
  }
  if (c.expectation_last >= c.monitoring_year) {
    return 'The expectation years must end before the monitoring year. Now: ' + c.expectation_first + '-' +
           c.expectation_last + ' vs ' + c.monitoring_year + '.';
  }
  if (c.season_start >= c.season_end) {
    return 'The season must start before it ends. Now: ' + monthDayLabel(c.season_start) + ' to ' +
           monthDayLabel(c.season_end) + ". (A window can't wrap past Dec 31; each year's window runs within " +
           'that calendar year.)';
  }
  if (!(c.decrease_threshold >= 0.5 && c.decrease_threshold < 1.0)) return 'The decrease threshold must be in [0.5, 1).';
  if (!(c.increase_threshold >= 0.5 && c.increase_threshold < 1.0)) return 'The increase threshold must be in [0.5, 1).';
  if (!(c.sensitivity > 0)) return 'Sensitivity must be positive.';
  if (!MONITORING_SENSORS.some(function (s) { return c.sensors[s]; })) return 'Select at least one monitoring sensor.';
  return null;
}

// Seasons for the first-detected-season layer: up to the last three years
// between the expectation and the monitoring year (app.py _timing_years()).
function timingYears(c) {
  var years = [];
  for (var y = c.expectation_last + 1; y <= c.monitoring_year; y++) years.push(y);
  return years.slice(-MAX_TIMING_SEASONS);
}

// How many seasons the expectation years cover. Both years are inclusive and
// the season window is applied once in each; all of those observations are fit
// together into one expected value per pixel (buildConfig() passes last_year + 1
// because bulcd's last_year is exclusive).
function expectationSummary(c) {
  if (c.expectation_first > c.expectation_last) return '';
  var n = c.expectation_last - c.expectation_first + 1;
  var years = n === 1 ? String(c.expectation_first)
                      : n === 2 ? c.expectation_first + ' and ' + c.expectation_last
                                : 'each year ' + c.expectation_first + '-' + c.expectation_last;
  return c.expectation_first + '-' + c.expectation_last + ' uses ' + n + ' annual season' + (n === 1 ? '' : 's') +
         ' (the season window in ' + years + ').';
}

// The notebook's plain-language description of the periods (app.py _describe()).
function describeControls(c) {
  var win = monthDayLabel(c.season_start) + '-' + monthDayLabel(c.season_end);
  var lines = [
    'Expectation (' + c.expectation_first + '-' + c.expectation_last + ', ' + win + ' each year) defines what ' +
      'is normal for each pixel.',
    'Monitoring (' + win + ', ' + c.monitoring_year + ') is what gets evaluated against that normal.'
  ];
  var years = timingYears(c);
  if (c.timing && years.length) {
    lines.push('First detected season: separate runs for ' + years.join(', ') + ', each judged against the same ' +
               'expectation and starting from the same odds (10% decrease, 80% unchanged, 10% increase).');
  }
  return lines;
}

// controls + aoi ({aoi_coordinates: ring} or {aoi_asset: id}) -> bulcd config.
// config.py build_config() followed by app.py EarlyDetectionApp.build().
function buildConfig(c, aoi) {
  var problem = validateControls(c);
  if (problem) throw new Error(problem);
  if ((aoi.aoi_coordinates == null) === (aoi.aoi_asset == null)) {
    throw new Error('pass exactly one of aoi_coordinates / aoi_asset');
  }
  var firstDoy = dayOfYear(c.monitoring_year, c.season_start), lastDoy = dayOfYear(c.monitoring_year, c.season_end);
  function sensors(names, firstYear, lastYear) {
    var out = {};
    names.forEach(function (name) {
      // bulcd's last_year is EXCLUSIVE; the controls use inclusive years.
      out[name] = {enabled: true, first_year: firstYear, last_year: lastYear + 1, first_doy: firstDoy,
                   last_doy: lastDoy, cloud_cover_threshold: CLOUD_COVER_THRESHOLD};
    });
    return out;
  }
  var target = sensors(MONITORING_SENSORS, c.monitoring_year, c.monitoring_year);
  MONITORING_SENSORS.forEach(function (s) { target[s].enabled = !!c.sensors[s]; });
  return {
    study_area: {aoi_coordinates: aoi.aoi_coordinates == null ? null : aoi.aoi_coordinates,
                 aoi_asset: aoi.aoi_asset == null ? null : aoi.aoi_asset,
                 mask_non_forest: !!c.mask_forest, mask_water: !!c.mask_water},
    evidence: {expectation: {sensors: sensors(BASELINE_SENSORS, c.expectation_first, c.expectation_last)},
               target: {sensors: target}},
    reduction: {band: 'nbr'},
    modality: {constant: true, unimodal: true},
    sensitivity: {z_score_numerator_factor: round2(c.sensitivity)},
    bulc_advanced_params: {custom_transition_matrix: PRODUCTION_TRANSITION_MATRIX, recency_factor: 1.0,
                           dampening_factor: round2(c.dampening), posterior_leveler: round2(c.posterior_leveler),
                           initializing_leveler: INITIALIZING_LEVELER}
  };
}

// The same controls for another monitoring year (app.py controls(y), used for
// the first-detected-season runs).
function withMonitoringYear(c, year) {
  var out = copy(c);
  out.monitoring_year = year;
  return out;
}

exports.PRODUCTION_TRANSITION_MATRIX = PRODUCTION_TRANSITION_MATRIX;
exports.INITIALIZING_LEVELER = INITIALIZING_LEVELER;
exports.APP_DEFAULTS = APP_DEFAULTS;
exports.RANGES = RANGES;
exports.MONITORING_SENSORS = MONITORING_SENSORS;
exports.SENSOR_LABELS = SENSOR_LABELS;
exports.MONTH_NAMES = MONTH_NAMES;
exports.DAYS_IN_MONTH = DAYS_IN_MONTH;
exports.copy = copy;
exports.dayOfYear = dayOfYear;
exports.validateControls = validateControls;
exports.expectationSummary = expectationSummary;
exports.timingYears = timingYears;
exports.describeControls = describeControls;
exports.buildConfig = buildConfig;
exports.withMonitoringYear = withMonitoringYear;
