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
// screening); sensors selectable for each period, the expectation defaulting to
// Landsat 8 only (a multi-year L8+S2 fit ran out of Earth Engine memory).
var CLOUD_COVER_THRESHOLD = 70;
var SENSORS = ['L5', 'L7', 'L8', 'L9', 'S2'];
// Monitoring can't use Landsat 5 (it stopped imaging in 2011, before the earliest monitoring year).
var MONITORING_SENSORS = ['L7', 'L8', 'L9', 'S2'];
// Monitoring sensors on by default (config.py DEFAULT_MONITORING_SENSORS); Landsat 7 is an opt-in.
var DEFAULT_MONITORING_SENSORS = ['L8', 'L9', 'S2'];
var SENSOR_LABELS = {L5: 'Landsat 5', L7: 'Landsat 7', L8: 'Landsat 8', L9: 'Landsat 9', S2: 'Sentinel-2'};
// Years each sensor has no or fewer observations in, for the default Jun-Sep
// season: [first year, last year (inclusive; null = open-ended), 'none' or
// 'fewer', what is missing]. Same table as config.py SENSOR_GAPS
// (docs/findings.md, 2026-10-19 and 2026-11-02).
var SENSOR_GAPS = {
  L5: [[2012, null, 'none', 'no observations after 2011 (it stopped imaging in November 2011)']],
  L7: [[2024, null, 'none', 'no observations after 2023 (none from 2024 in tests)'],
       [2022, 2023, 'fewer', 'fewer observations in 2022-2023 (its orbit was lowered in 2022: about two thirds to ' +
                             'three quarters as many scenes in tests)']],
  L8: [[null, 2012, 'none', 'no observations before 2013 (its first scenes are from April 2013)']],
  L9: [[null, 2021, 'none', 'no observations before 2022 (its first scenes are from Oct 31, 2021)']],
  S2: [[null, 2015, 'none', 'no observations before 2016 (none in Earth Engine\'s surface-reflectance collection at ' +
                            'the testsite in tests)'],
       [2016, 2017, 'fewer', 'fewer observations before 2018 (one satellite until Sentinel-2B joined in mid-2017: ' +
                             'about a quarter to half as many scenes in tests)']]
};
// Said whenever a sensor is chosen for either period (config.py SENSOR_NOTES).
var SENSOR_NOTES = {
  L7: 'Landsat 7 images since 2003 have striped gaps (its scan-line corrector failed; about a fifth of each scene ' +
      'is missing), so it gives fewer clear observations per pixel than Landsat 8: about 75-95% as many in tests.'
};
// Landsat 5 and 7 (TM/ETM+) vs Landsat 8 and 9 (OLI): different instruments.
var TM_ETM = ['L5', 'L7'];
// Expectation length (years) above which a Sentinel-2 expectation is likely to
// exceed Earth Engine's interactive memory limit (config.py S2_EXPECTATION_MAX_YEARS).
var S2_EXPECTATION_MAX_YEARS = 2;
var MAX_TIMING_SEASONS = 3;

// Starting probabilities, as in the original BULC-D GUI (initializingLeveler 0.7
// applied to "unchanged"): 0.1 decrease / 0.8 unchanged / 0.1 increase. Fixed;
// not a control.
var INITIALIZING_LEVELER = 0.7;

// Expectation fit order N = a constant plus the first N annual harmonics (1, 2
// and 3 cycles per year): the legacy modalityDictionary's unimodal, bimodal and
// trimodal flags, which add their terms cumulatively. Order 1 (constant +
// unimodal) is the original BULC-D GUI's default. config.py FIT_ORDERS and
// app.py FIT_ORDER_LABELS hold the same values.
var FIT_ORDERS = [1, 2, 3];
var FIT_ORDER_LABELS = {1: '1: one annual cycle (original BULC-D)', 2: '2: adds 2 cycles per year',
                        3: '3: adds 2 and 3 cycles per year'};
// Shortest seasonal window (days) at which an order-2/3 fit stays well
// conditioned (config.py MIN_WINDOW_DAYS; docs/findings.md, 2026-10-13).
var MIN_WINDOW_DAYS = {2: 183, 3: 245};

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
  // Detection timing (first detected season, last detection, detection episodes):
  // only seasons that end as decrease count (confirmed), else any crossing (raw).
  // No original default (the original GUI had no such product). app.py TIMING_CONFIRMED_DEFAULT.
  timing_confirmed: true,
  dampening: 0.7,                                   // original GUI
  posterior_leveler: 0.9,                           // original GUI
  fit_order: 1,                                     // original GUI (constant + unimodal)
  expectation_sensors: {L5: false, L7: false, L8: true, L9: false, S2: false},  // Early Detection choice (config.py BASELINE_SENSORS)
  sensors: {L7: false, L8: true, L9: true, S2: true},  // monitoring sensors (config.py DEFAULT_MONITORING_SENSORS)
  mask_forest: false,                               // original GUI: no forest mask
  mask_water: true,                                 // original GUI: water masked
  allow_large: false
};

// app.py widget limits.
var RANGES = {
  expectation_years: [2010, 2025],                  // config.py EXPECTATION_YEARS
  monitoring_years: [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026],  // MONITORING_YEARS
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

// bulcd modality for expectation fit order 1, 2 or 3 (config.py modality_for_order()).
// Only the flags that are on; bulcd.js defaults the rest to false, so order 1
// stays exactly the original {constant: true, unimodal: true}.
function modalityForOrder(order) {
  if (FIT_ORDERS.indexOf(order) < 0) throw new Error('fit_order must be one of ' + FIT_ORDERS.join(', '));
  var out = {constant: true, unimodal: true};
  if (order >= 2) out.bimodal = true;
  if (order >= 3) out.trimodal = true;
  return out;
}

// Days in the seasonal window, both ends included (MonitoringControls.window_days).
function windowDays(c) {
  return dayOfYear(c.monitoring_year, c.season_end) - dayOfYear(c.monitoring_year, c.season_start) + 1;
}

// Warning for a higher-order fit over a short seasonal window, or null. Same
// text as config.py fit_order_warning().
function fitOrderWarning(c) {
  var need = MIN_WINDOW_DAYS[c.fit_order], days = windowDays(c);
  if (need === undefined || days >= need) return null;
  return 'Expectation fit order ' + c.fit_order + ' with a ' + days + '-day season may be unstable: within a ' +
         'window shorter than about ' + need + ' days the harmonics are hard to tell apart, so the fitted curve ' +
         'can follow noise, especially with few expectation years or clear observations. Check the fit in the ' +
         'pixel inspector.';
}

function checked(boxes) {
  return SENSORS.filter(function (s) { return boxes[s]; });
}

function sensorList(codes) {
  var names = codes.map(function (s) { return SENSOR_LABELS[s]; });
  return names.length === 1 ? names[0] : names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
}

function yearsLabel(first, last) {
  return first === last ? 'year ' + first : 'years ' + first + '-' + last;
}

// [kind, text, overlap first, overlap last] for each of `code`'s gaps that
// overlaps firstYear..lastYear (config.py _gaps_within()).
function gapsWithin(code, firstYear, lastYear) {
  return (SENSOR_GAPS[code] || []).map(function (g) {
    var a = Math.max(firstYear, g[0] === null ? firstYear : g[0]);
    var b = Math.min(lastYear, g[1] === null ? lastYear : g[1]);
    return a <= b ? [g[2], g[3], a, b] : null;
  }).filter(function (x) { return x; });
}

// Whether `code` has observations in at least one of firstYear..lastYear (config.py has_data()).
function hasData(code, firstYear, lastYear) {
  var covered = 0;
  gapsWithin(code, firstYear, lastYear).forEach(function (g) { if (g[0] === 'none') covered += g[3] - g[2] + 1; });
  return covered < lastYear - firstYear + 1;
}

// The data-availability problem that blocks a run, or null: no chosen
// expectation sensor has observations in any expectation year, or no chosen
// monitoring sensor in the monitoring year. Same text as config.py availability_problem().
function availabilityProblem(c) {
  var periods = [['expectation', checked(c.expectation_sensors), c.expectation_first, c.expectation_last],
                 ['monitoring', checked(c.sensors), c.monitoring_year, c.monitoring_year]];
  for (var i = 0; i < periods.length; i++) {
    var p = periods[i], codes = p[1], y0 = p[2], y1 = p[3];
    if (!codes.length || codes.some(function (s) { return hasData(s, y0, y1); })) continue;
    var reasons = [];
    codes.forEach(function (s) {
      gapsWithin(s, y0, y1).forEach(function (g) { if (g[0] === 'none') reasons.push(SENSOR_LABELS[s] + ' has ' + g[1]); });
    });
    return 'No selected ' + p[0] + ' sensor has observations in ' + (y0 === y1 ? y0 : y0 + '-' + y1) + ': ' +
           reasons.join('; ') + '. Choose other sensors or years.';
  }
  return null;
}

// Warnings about the sensor choice (none blocks a run). Same text as config.py
// sensor_warnings(): the periods use different sensors (among those with
// observations in each period); an expectation sensor has no or fewer data in
// some expectation years; a monitoring sensor has no or fewer data in the
// monitoring year; a first-detected-season year with no monitoring data (when
// the first-detected season is on); notes on a chosen sensor; a Sentinel-2
// expectation long enough to likely exceed Earth Engine's interactive memory limit.
function sensorWarnings(c) {
  var exp = checked(c.expectation_sensors), mon = checked(c.sensors), out = [];
  var expUsed = exp.filter(function (s) { return hasData(s, c.expectation_first, c.expectation_last); });
  var monUsed = mon.filter(function (s) { return hasData(s, c.monitoring_year, c.monitoring_year); });
  if (expUsed.length && monUsed.length && expUsed.join() !== monUsed.join()) {
    var differ = SENSORS.filter(function (s) { return (expUsed.indexOf(s) >= 0) !== (monUsed.indexOf(s) >= 0); });
    var text = 'The expectation uses ' + sensorList(expUsed) + ' and monitoring uses ' + sensorList(monUsed) + '. ';
    if (differ.indexOf('S2') < 0 && differ.some(function (s) { return TM_ETM.indexOf(s) >= 0; })) {
      text += 'Landsat 5 and 7 (TM/ETM+) and Landsat 8 and 9 (OLI) measure slightly different wavelengths, and ' +
              'BULC-D does not adjust for it. In tests the NBR difference between them was small (median 0.013 or ' +
              'less) and caused no false change in stable forest, but decreases agreed best with real change when ' +
              'Landsat 8 was in both periods.';
    } else {
      text += 'Differences between sensors can register as change: in earlier tests, Sentinel-2 in monitoring but ' +
              'not in the expectation produced false decreases at stable sites that disappeared when both periods ' +
              'used the same sensors.';
    }
    out.push(text);
  }
  exp.forEach(function (s) {
    gapsWithin(s, c.expectation_first, c.expectation_last).forEach(function (g) {
      out.push(SENSOR_LABELS[s] + ' has ' + g[1] + ', which affects expectation ' + yearsLabel(g[2], g[3]) +
               (exp.length > 1 ? '; the sensor mix changes partway through the expectation.' : '.'));
    });
  });
  mon.forEach(function (s) {
    gapsWithin(s, c.monitoring_year, c.monitoring_year).forEach(function (g) {
      out.push(SENSOR_LABELS[s] + ' has ' + g[1] + ', which affects the monitoring year (' + c.monitoring_year + ').');
    });
  });
  var empty = (c.timing ? timingYears(c) : []).filter(function (y) {
    return y !== c.monitoring_year && !mon.some(function (s) { return hasData(s, y, y); });
  });
  if (empty.length) {
    out.push('No selected monitoring sensor has observations in ' + empty.join(', ') + ', so the ' +
             'first-detected-season run for ' + (empty.length === 1 ? 'that season' : 'those seasons') + ' has ' +
             'nothing to evaluate and shows no detection there.');
  }
  SENSORS.forEach(function (s) {
    if (SENSOR_NOTES[s] && (exp.indexOf(s) >= 0 || mon.indexOf(s) >= 0)) out.push(SENSOR_NOTES[s]);
  });
  var n = c.expectation_last - c.expectation_first + 1;
  if (exp.indexOf('S2') >= 0 && n > S2_EXPECTATION_MAX_YEARS) {
    out.push('A ' + n + '-year expectation with Sentinel-2 is likely to exceed Earth Engine\'s memory limit: in ' +
             'tests, Sentinel-2 expectations longer than ' + S2_EXPECTATION_MAX_YEARS + ' years failed ' +
             'with the pixel inspector failing every time (usually "User memory limit exceeded") and map layers ' +
             'failing intermittently. Use fewer expectation years or leave Sentinel-2 out of the expectation.');
  }
  return out;
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
  if (FIT_ORDERS.indexOf(c.fit_order) < 0) return 'The expectation fit order must be 1, 2 or 3.';
  if (!SENSORS.some(function (s) { return c.expectation_sensors[s]; })) return 'Select at least one expectation sensor.';
  if (!MONITORING_SENSORS.some(function (s) { return c.sensors[s]; })) return 'Select at least one monitoring sensor.';
  return availabilityProblem(c);
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
               'expectation and starting from the same odds (10% decrease, 80% unchanged, 10% increase). ' +
               (c.timing_confirmed ? 'A season counts only if it ends as decrease (confirmed).'
                                   : 'Any threshold crossing counts, even one BULC-D later retracts (raw).'));
  }
  var warning = fitOrderWarning(c);
  if (warning) lines.push('Warning: ' + warning);
  sensorWarnings(c).forEach(function (w) { lines.push('Warning: ' + w); });
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
  // The default monitoring sensors stay listed, enabled or not; an opt-in sensor
  // (Landsat 7) is added only when chosen (config.py with_monitoring_sensors()).
  var target = sensors(MONITORING_SENSORS.filter(function (s) {
    return DEFAULT_MONITORING_SENSORS.indexOf(s) >= 0 || c.sensors[s];
  }), c.monitoring_year, c.monitoring_year);
  Object.keys(target).forEach(function (s) { target[s].enabled = !!c.sensors[s]; });
  return {
    study_area: {aoi_coordinates: aoi.aoi_coordinates == null ? null : aoi.aoi_coordinates,
                 aoi_asset: aoi.aoi_asset == null ? null : aoi.aoi_asset,
                 mask_non_forest: !!c.mask_forest, mask_water: !!c.mask_water},
    evidence: {expectation: {sensors: sensors(checked(c.expectation_sensors), c.expectation_first, c.expectation_last)},
               target: {sensors: target}},
    reduction: {band: 'nbr'},
    modality: modalityForOrder(c.fit_order),
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
exports.FIT_ORDERS = FIT_ORDERS;
exports.FIT_ORDER_LABELS = FIT_ORDER_LABELS;
exports.MIN_WINDOW_DAYS = MIN_WINDOW_DAYS;
exports.modalityForOrder = modalityForOrder;
exports.windowDays = windowDays;
exports.fitOrderWarning = fitOrderWarning;
exports.APP_DEFAULTS = APP_DEFAULTS;
exports.RANGES = RANGES;
exports.SENSORS = SENSORS;
exports.MONITORING_SENSORS = MONITORING_SENSORS;
exports.DEFAULT_MONITORING_SENSORS = DEFAULT_MONITORING_SENSORS;
exports.SENSOR_GAPS = SENSOR_GAPS;
exports.hasData = hasData;
exports.availabilityProblem = availabilityProblem;
exports.S2_EXPECTATION_MAX_YEARS = S2_EXPECTATION_MAX_YEARS;
exports.sensorWarnings = sensorWarnings;
exports.SENSOR_LABELS = SENSOR_LABELS;
exports.MONTH_NAMES = MONTH_NAMES;
exports.DAYS_IN_MONTH = DAYS_IN_MONTH;
exports.copy = copy;
exports.dayOfYear = dayOfYear;
exports.monthDayLabel = monthDayLabel;
exports.validateControls = validateControls;
exports.expectationSummary = expectationSummary;
exports.timingYears = timingYears;
exports.describeControls = describeControls;
exports.buildConfig = buildConfig;
exports.withMonitoringYear = withMonitoringYear;
