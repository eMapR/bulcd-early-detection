// Pixel inspector: one location's observations and BULC-D probabilities.
//
// JS mirror of src/bulcd_early_detection/pixel.py (pixel_history() and the
// two-chart layout of plot_pixel_history()): read-only interpretation of a
// bulcd.js result, no detection logic. gee/tests/run_app_parity.py checks
// historyRows() against Python's pixel_history() at the reference pixels.
//
// Sampling is on the 30 m UTM grid the products use, at the clicked/entered
// coordinate (not the legacy GUI's native-pixel sampling). Probabilities are
// plotted at each observation bin's own date (bins are dated at their END);
// the legacy chart plots each one a step late.
//
// expectationQuery() adds the expectation period: the binned observations the
// fit was computed from, the fitted curve at their dates (bulcd.js
// addFittedBand(), the same function that scores the monitoring year) and the
// fit's coefficients, residual SD and R2 at the pixel. Diagnostic only.
//
// historyQuery() builds the Earth Engine request; historyRows(), the table
// builders and crossingNotes() are pure functions; the chart builders need
// the Code Editor's `ui`. Plain ES5.

var CLASSES = ['decrease', 'unchanged', 'increase'];
// pixel.py CLASS_COLORS (decrease/increase = the map's outcome colors).
var CLASS_COLORS = {decrease: '#e34948', unchanged: '#8a887f', increase: '#2a78d6'};
var EXPECTED_COLOR = '#555555', OBSERVED_COLOR = '#b9b7ae';

// UTM zone EPSG code for a coordinate (same rule as pixel.utm_crs_for).
function utmCrsFor(lon, lat) {
  var zone = Math.floor((lon + 180) / 6) + 1;
  return 'EPSG:' + ((lat >= 0 ? 32600 : 32700) + zone);
}

// One ee.Dictionary holding the three getRegion tables pixel_history() reads:
// fitted/observed band, z-score, and the probability stack.
function historyQuery(result, config, lon, lat) {
  var point = ee.Geometry.Point([lon, lat]);
  var crs = utmCrsFor(lon, lat);
  var organized = result.organized;
  var band = config.reduction.band;
  return ee.Dictionary({
    fitted: organized.expectation_fitted_collection.select([band, 'fitted']).getRegion(point, 30, crs),
    zscore: organized.lof_zscore.getRegion(point, 30, crs),
    probability: result.probability_stack.select(CLASSES).getRegion(point, 30, crs)
  });
}

// The expectation period at one location (see the header).
function expectationQuery(bulcd, result, config, lon, lat) {
  var point = ee.Geometry.Point([lon, lat]);
  var crs = utmCrsFor(lon, lat);
  var organized = result.organized, fit = organized.expectation_fit;
  var band = config.reduction.band;
  var withFit = organized.expectation_collection.map(bulcd.addHarmonicTerms).map(function (image) {
    return bulcd.addFittedBand(image, fit.coefficients, fit.regressor_names);
  });
  return ee.Dictionary({
    observations: withFit.select([band, 'fitted']).getRegion(point, 30, crs),
    fit: fit.coefficients.addBands(fit.residual_stddev).addBands(fit.r2)
      .reduceRegion({reducer: ee.Reducer.first(), geometry: point, scale: 30, crs: crs}),
    regressors: fit.regressor_names
  });
}

// getRegion rows -> {time: {column: value}} (pixel._table).
function byTime(region) {
  var header = region[0], t = header.indexOf('time'), out = {};
  region.slice(1).forEach(function (row) {
    var rec = {};
    header.forEach(function (h, i) { rec[h] = row[i]; });
    out[row[t]] = rec;
  });
  return out;
}

// Which outcome one observation's evidence favors: its z-score bin's
// transition-matrix row, largest likelihood (pixel.supported_class; the bin is
// bisect_right on the cuts, first maximum wins).
function supportedClass(zscore, binCuts, matrix) {
  if (zscore === null || zscore === undefined) return null;
  var bin = 0;
  while (bin < binCuts.length && binCuts[bin] <= zscore) bin++;
  var row = matrix[bin], best = 0;
  for (var i = 1; i < 3; i++) if (row[i] > row[best]) best = i;
  return CLASSES[best];
}

function utcDateString(millis) {
  return new Date(millis).toISOString().slice(0, 10);
}

function value(rec, key) {
  return rec && rec[key] !== undefined ? rec[key] : null;
}

// Rows in pixel_history() form: one per observation bin, sorted by time.
// config is bulcd.withDefaults()'d (it needs bin_cuts).
function historyRows(tables, config) {
  var fitted = byTime(tables.fitted), zscores = byTime(tables.zscore), probs = byTime(tables.probability);
  var band = config.reduction.band, matrix = config.bulc_advanced_params.custom_transition_matrix;
  return Object.keys(probs).map(Number).sort(function (a, b) { return a - b; }).map(function (t) {
    var z = value(zscores[t], 'zscore'), f = fitted[t];
    var row = {time: t, date: utcDateString(t), observed: z !== null ? value(f, band) : null,
               expected: value(f, 'fitted'), zscore: z, supports: supportedClass(z, config.bin_cuts, matrix)};
    CLASSES.forEach(function (c) { row[c] = probs[t][c]; });
    return row;
  });
}

// Expectation-period rows, one per observation bin, sorted by time: observed
// is null for a bin with no clear observation; expected is the fitted curve.
function expectationRows(tables, config) {
  var obs = byTime(tables.observations), band = config.reduction.band;
  return Object.keys(obs).map(Number).sort(function (a, b) { return a - b; }).map(function (t) {
    return {time: t, date: utcDateString(t), observed: value(obs[t], band), expected: value(obs[t], 'fitted')};
  });
}

function round(x, digits) {
  return x === null || x === undefined ? 'n/a' : x.toFixed(digits);
}

// Plain-language summary of the expectation fit at the pixel.
function expectationSummary(tables, rows, config) {
  var fit = tables.fit || {}, regressors = tables.regressors, band = config.reduction.band.toUpperCase();
  var used = rows.filter(function (r) { return r.observed !== null; });
  // The configured years (inclusive); bins are dated at their end, so the last
  // bin of a Dec 31 season carries a January date.
  var first = Infinity, last = -Infinity, sensors = config.evidence.expectation.sensors;
  for (var k in sensors) {
    if (!sensors[k].enabled) continue;
    first = Math.min(first, sensors[k].first_year);
    last = Math.max(last, sensors[k].last_year - 1);  // bulcd's last_year is exclusive
  }
  var span = first === last ? String(first) : first + '-' + last;
  var lines = ['Expectation fit at this pixel: ' + used.length + ' clear observations (of ' + rows.length +
               ' ' + config.evidence.day_step_size + '-day bins) in ' + span + '.'];
  var shape = 'Fitted mean ' + band + ' ' + round(fit.constant, 3);
  if (regressors.indexOf('cos') >= 0 && fit.cos != null && fit.sin != null) {
    shape += ', seasonal amplitude ' + round(Math.sqrt(fit.cos * fit.cos + fit.sin * fit.sin), 3);
  }
  if (regressors.indexOf('t') >= 0) shape += ', within-year trend ' + round(fit.t, 3);
  lines.push(shape + '; residual SD ' + round(fit.residual_stddev, 3) + '; R2 ' + round(fit.r2, 2) + '.');
  lines.push('Model terms: ' + regressors.join(' + ') + '. The same curve is used for every year. Monitoring ' +
             'z-scores are (observed - fitted) x sensitivity / max(residual SD, ' +
             config.sensitivity.z_score_denominator_factor + ').');
  return lines;
}

function hasObservations(rows) {
  return rows.some(function (r) { return r.zscore !== null; });
}

function firstCrossing(rows, threshold, cls) {
  for (var i = 0; i < rows.length; i++) {
    if (rows[i][cls] !== null && rows[i][cls] > threshold) return rows[i].date;
  }
  return null;
}

// {decrease: threshold, increase: increaseThreshold, or threshold when that is
// not given} (config.py class_thresholds()).
function classThresholds(threshold, increaseThreshold) {
  return {decrease: threshold, increase: increaseThreshold == null ? threshold : increaseThreshold};
}

// The same per-season sentences the Python inspector prints
// (pixel.py crossing_notes()): each change class against its own threshold.
function crossingNotes(rows, threshold, increaseThreshold) {
  var t = classThresholds(threshold, increaseThreshold);
  var notes = [];
  ['decrease', 'increase'].forEach(function (cls) {
    var crossed = firstCrossing(rows, t[cls], cls);
    if (!crossed) return;
    var finished = rows[rows.length - 1][cls] > t[cls];
    notes.push(cls + ' first crossed its threshold (' + t[cls] + ') on ' + crossed + ', ' +
               (finished ? 'finished the season as ' + cls + ' (counts as detected)'
                         : 'finished below its threshold (does not count)'));
  });
  if (!notes.length) {
    notes.push('never crossed a threshold (' + (t.decrease === t.increase ? t.decrease
      : 'decrease ' + t.decrease + ', increase ' + t.increase) + ')');
  }
  return notes;
}

// Chart x values: the bin's UTC calendar date as a local Date, so the browser
// doesn't shift it a day.
function chartDate(dateString) {
  var p = dateString.split('-');
  return new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
}

function cell(v) {
  return {v: v === undefined ? null : v};
}

// "Target Year vs. Fit": expected (baseline fit) line, observed NBR (broken
// where there is no clear observation), and each observation as a dot colored
// by the class its evidence favors.
function targetFitTable(rows, band) {
  var cols = [{label: 'Date', type: 'date'}, {label: 'expected (baseline fit)', type: 'number'},
              {label: 'observed ' + band.toUpperCase(), type: 'number'}];
  CLASSES.forEach(function (c) { cols.push({label: 'observation favors ' + c, type: 'number'}); });
  return {
    cols: cols,
    rows: rows.map(function (r) {
      var c = [cell(chartDate(r.date)), cell(r.expected), cell(r.observed)];
      CLASSES.forEach(function (k) { c.push(cell(r.supports === k ? r.observed : null)); });
      return {c: c};
    })
  };
}

// "Expectation -> Monitoring": the fitted curve through both periods, the
// expectation observations it was fit to, and each monitoring observation
// colored by the class its evidence favors. A blank row between the periods
// breaks the line across any gap.
function timelineTable(expRows, rows, band) {
  var cols = [{label: 'Date', type: 'date'}, {label: 'fitted expectation', type: 'number'},
              {label: 'expectation ' + band.toUpperCase() + ' (used in the fit)', type: 'number'}];
  CLASSES.forEach(function (c) { cols.push({label: 'monitoring favors ' + c, type: 'number'}); });
  var out = expRows.map(function (r) {
    return {c: [cell(chartDate(r.date)), cell(r.expected), cell(r.observed), cell(null), cell(null), cell(null)]};
  });
  if (expRows.length) {
    var last = expRows[expRows.length - 1].date.split('-');
    out.push({c: [cell(new Date(Number(last[0]), Number(last[1]) - 1, Number(last[2]) + 1)), cell(null), cell(null),
                  cell(null), cell(null), cell(null)]});
  }
  rows.forEach(function (r) {
    var c = [cell(chartDate(r.date)), cell(r.expected), cell(null)];
    CLASSES.forEach(function (k) { c.push(cell(r.supports === k ? r.observed : null)); });
    out.push({c: c});
  });
  return {cols: cols, rows: out};
}

// The threshold lines on "Probability Through Time": one shared line, or the
// decrease and increase thresholds when they differ ([{label, value, cls}]).
function thresholdLines(threshold, increaseThreshold) {
  var t = classThresholds(threshold, increaseThreshold);
  if (t.decrease === t.increase) return [{label: 'decision threshold (' + t.decrease + ')', value: t.decrease}];
  return ['decrease', 'increase'].map(function (cls) {
    return {label: cls + ' threshold (' + t[cls] + ')', value: t[cls], cls: cls};
  });
}

// "Probability Through Time": P(decrease/unchanged/increase) at each
// observation's own date, plus the threshold line(s).
function probabilityTable(rows, threshold, increaseThreshold) {
  var lines = thresholdLines(threshold, increaseThreshold);
  var cols = [{label: 'Date', type: 'date'}];
  CLASSES.forEach(function (c) { cols.push({label: 'P(' + c + ')', type: 'number'}); });
  lines.forEach(function (l) { cols.push({label: l.label, type: 'number'}); });
  return {
    cols: cols,
    rows: rows.map(function (r) {
      var c = [cell(chartDate(r.date))];
      CLASSES.forEach(function (k) { c.push(cell(r[k])); });
      lines.forEach(function (l) { c.push(cell(l.value)); });
      return {c: c};
    })
  };
}

var CHART_BASE = {
  legend: {position: 'bottom', maxLines: 3},
  hAxis: {format: 'MMM', gridlines: {color: 'transparent'}},
  chartArea: {left: 48, right: 12, top: 32, bottom: 72},
  height: 300,
  interpolateNulls: false
};

function options(extra) {
  var out = JSON.parse(JSON.stringify(CHART_BASE));
  for (var k in extra) out[k] = extra[k];
  return out;
}

function targetFitChart(rows, band) {
  var series = {0: {color: EXPECTED_COLOR, lineWidth: 2, pointSize: 0},
                1: {color: OBSERVED_COLOR, lineWidth: 1, pointSize: 0}};
  CLASSES.forEach(function (c, i) { series[2 + i] = {color: CLASS_COLORS[c], lineWidth: 0, pointSize: 5}; });
  return ui.Chart(targetFitTable(rows, band), 'LineChart',
                  options({title: 'Target Year vs. Fit', vAxis: {title: band.toUpperCase()}, series: series}));
}

function timelineChart(expRows, rows, band) {
  var series = {0: {color: EXPECTED_COLOR, lineWidth: 2, pointSize: 0},
                1: {color: '#222222', lineWidth: 0, pointSize: 4}};
  CLASSES.forEach(function (c, i) { series[2 + i] = {color: CLASS_COLORS[c], lineWidth: 0, pointSize: 5}; });
  return ui.Chart(timelineTable(expRows, rows, band), 'LineChart',
                  options({title: 'Expectation -> Monitoring: observations and fit',
                           hAxis: {format: 'MMM yyyy', gridlines: {color: 'transparent'}},
                           vAxis: {title: band.toUpperCase()}, series: series}));
}

function probabilityChart(rows, threshold, increaseThreshold) {
  var series = {};
  CLASSES.forEach(function (c, i) { series[i] = {color: CLASS_COLORS[c], lineWidth: 2, pointSize: 3}; });
  thresholdLines(threshold, increaseThreshold).forEach(function (l, i) {
    series[3 + i] = {color: l.cls ? CLASS_COLORS[l.cls] : EXPECTED_COLOR, lineWidth: 1, pointSize: 0,
                     lineDashStyle: [3, 3]};
  });
  return ui.Chart(probabilityTable(rows, threshold, increaseThreshold), 'LineChart',
                  options({title: 'Probability Through Time',
                           vAxis: {title: 'Probability', viewWindow: {min: 0, max: 1}}, series: series}));
}

exports.CLASSES = CLASSES;
exports.CLASS_COLORS = CLASS_COLORS;
exports.utmCrsFor = utmCrsFor;
exports.historyQuery = historyQuery;
exports.supportedClass = supportedClass;
exports.historyRows = historyRows;
exports.expectationQuery = expectationQuery;
exports.expectationRows = expectationRows;
exports.expectationSummary = expectationSummary;
exports.timelineTable = timelineTable;
exports.timelineChart = timelineChart;
exports.hasObservations = hasObservations;
exports.firstCrossing = firstCrossing;
exports.classThresholds = classThresholds;
exports.crossingNotes = crossingNotes;
exports.targetFitTable = targetFitTable;
exports.probabilityTable = probabilityTable;
exports.targetFitChart = targetFitChart;
exports.probabilityChart = probabilityChart;
