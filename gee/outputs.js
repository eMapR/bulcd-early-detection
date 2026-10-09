// Map products from bulcd.js results, and reference imagery.
//
// JS mirrors of src/bulcd_early_detection/outputs.py (_outcome_from_result()'s
// outcome band, detection_timing_image(), combine_season_timing(),
// annual_true_color(), annual_nbr(), nbr_stretch()) and the matching render.py
// colors. Interpretation of bulcd outputs only; no detection logic.
// gee/tests/run_app_parity.py checks the condition and timing layers against
// Python.
//
// Plain ES5 (Code Editor compatible); `ee` is the global client.

var DECREASE = 0, UNCHANGED = 1, INCREASE = 2, NOT_ANALYZED = 3;

var OUTCOME_LABELS = {};
OUTCOME_LABELS[DECREASE] = 'Decrease (below expected)';
OUTCOME_LABELS[UNCHANGED] = 'Unchanged (within expected)';
OUTCOME_LABELS[INCREASE] = 'Increase (above expected)';
OUTCOME_LABELS[NOT_ANALYZED] = 'Land not analyzed (non-forest mask)';

// Same colors as render.py OUTCOME_COLORS.
var OUTCOME_COLORS = {};
OUTCOME_COLORS[DECREASE] = '#e34948';
OUTCOME_COLORS[UNCHANGED] = '#bdbbb3';
OUTCOME_COLORS[INCREASE] = '#2a78d6';
OUTCOME_COLORS[NOT_ANALYZED] = '#e6e5e0';

function copy(obj) {
  return JSON.parse(JSON.stringify(obj));
}

// DECREASE/INCREASE where that class's final probability exceeds `threshold`
// (>= 0.5, so at most one can), else UNCHANGED; NOT_ANALYZED on land excluded
// by the non-forest mask; masked on water. Band 'outcome', float.
function outcomeImage(bulcd, result, config, threshold) {
  var final = result.final_probabilities;
  var dec = final.select('decrease'), inc = final.select('increase');

  var analyzed = bulcd.studyAreaMask(config);
  analyzed = analyzed === null ? ee.Image.constant(1) : analyzed;
  var waterOnly = copy(config);
  waterOnly.study_area.mask_water = true;
  waterOnly.study_area.mask_non_forest = false;
  var land = bulcd.studyAreaMask(waterOnly);

  var changed = ee.Image.constant(UNCHANGED).where(dec.gt(threshold), DECREASE).where(inc.gt(threshold), INCREASE)
    .updateMask(analyzed).updateMask(dec.mask());
  return ee.Image.constant(NOT_ANALYZED).where(changed.mask(), changed).updateMask(land).rename('outcome')
    .toFloat();
}

// The notebook's condition layer: analyzed pixels only (not-analyzed land is not
// drawn), decrease/unchanged/increase colors (app.py _compute()).
function conditionLayerImage(outcome) {
  return outcome.updateMask(outcome.lte(INCREASE));
}

function conditionVis() {
  return {min: DECREASE, max: INCREASE, palette: [DECREASE, UNCHANGED, INCREASE].map(function (k) {
    return OUTCOME_COLORS[k].slice(1);
  })};
}

function outcomeVis() {
  return {min: DECREASE, max: NOT_ANALYZED,
          palette: [DECREASE, UNCHANGED, INCREASE, NOT_ANALYZED].map(function (k) {
            return OUTCOME_COLORS[k].slice(1);
          })};
}

// ---------------------------------------------------------------- detection timing

// Year and day of year of the FIRST observation bin where P(decrease) exceeded
// `threshold` (bin END date), masked where it never did or the pixel isn't
// analyzed; plus `outcome`, the state at the end of the run.
// outputs.py detection_timing_image().
function detectionTimingImage(bulcd, config, threshold) {
  var result = bulcd.runBulcd(config);
  var outcome = outcomeImage(bulcd, result, config, threshold);
  var first = result.probability_stack.map(function (img) {
    var date = ee.Date(img.get('system:time_start'));
    var value = date.get('year').multiply(1000).add(date.getRelative('day', 'year').add(1));
    return ee.Image.constant(value).toInt32().rename('code').updateMask(img.select('decrease').gt(threshold));
  }).min().updateMask(outcome.lte(INCREASE));
  var year = first.divide(1000).floor().rename('first_decrease_year');
  var doy = first.mod(1000).rename('first_decrease_doy');
  return ee.Image.cat(year.toFloat(), doy.toFloat(), outcome.toFloat());
}

// First monitoring season in which P(decrease) crossed the threshold, from
// independent single-season runs ({year: detectionTimingImage}); with
// `confirmed` (the default) a season counts only if it ENDS as decrease.
// outputs.py combine_season_timing().
function combineSeasonTiming(seasons, confirmed) {
  confirmed = confirmed === undefined ? true : confirmed;
  var years = Object.keys(seasons).map(Number).sort(function (a, b) { return a - b; });
  var year = ee.Image(0).toFloat(), doy = ee.Image(0).toFloat();
  years.slice().reverse().forEach(function (y) {  // earliest season written last, so it wins
    var s = seasons[y];
    var crossed = s.select('first_decrease_year').mask().and(s.select('first_decrease_year').unmask(0).gt(0));
    if (confirmed) crossed = crossed.and(s.select('outcome').eq(DECREASE));
    year = year.where(crossed, y);
    doy = doy.where(crossed, s.select('first_decrease_doy').unmask(0));
  });
  var outcome = seasons[years[years.length - 1]].select('outcome');
  var found = year.gt(0);
  return ee.Image.cat(
    year.updateMask(found).updateMask(outcome.mask()).rename('first_decrease_year'),
    doy.updateMask(found).updateMask(outcome.mask()).rename('first_decrease_doy'),
    outcome);
}

// render.py YEAR_COLORS: earliest = darkest.
var YEAR_COLORS = ['#7c2d12', '#d4541a', '#f5a54a', '#fbd3a0'];

function timingVis(years) {
  return {min: years[0], max: years[years.length - 1],
          palette: YEAR_COLORS.slice(0, years.length).map(function (c) { return c.slice(1); })};
}

// ---------------------------------------------------------------- reference imagery (independent of BULC-D)

// Sentinel-2 SR for one year's MM-DD window, Cloud Score+-masked (outputs.py _clear_s2()).
function clearS2(region, year, window, csThreshold) {
  csThreshold = csThreshold === undefined ? 0.6 : csThreshold;
  var csp = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED');
  return ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(region)
    .filterDate(year + '-' + window[0], year + '-' + window[1])
    .linkCollection(csp, ['cs_cdf'])
    .map(function (i) { return i.updateMask(i.select('cs_cdf').gte(csThreshold)); });
}

// render.py TRUE_COLOR.
var TRUE_COLOR = {bands: ['B4', 'B3', 'B2'], min: [0, 0, 0], max: [1400, 1400, 1400], gamma: 1.3};

function annualTrueColor(region, year, window) {
  return clearS2(region, year, window).select(['B4', 'B3', 'B2']).median();
}

// Sentinel-2 NBR median for one year, on a fixed 30 m UTM grid unless
// `reproject` is false (large areas). outputs.py annual_nbr().
function annualNbr(region, year, window, crs, reproject) {
  var nbr = clearS2(region, year, window).map(function (i) { return i.normalizedDifference(['B8', 'B12']); })
    .median().rename('nbr_' + year);
  return reproject ? nbr.reproject({crs: crs, scale: 30}) : nbr;
}

// render.py _not_water().
function notWater() {
  return ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').unmask(0).lte(50);
}

// ONE stretch for all years: the 2nd and 98th percentiles across the years' NBR
// (outputs.py nbr_stretch()). Returns an ee.Dictionary; nbrStretchFromStats()
// turns its evaluated value into [low, high].
function nbrStretchQuery(nbrImages, region, scale) {
  return ee.Image.cat(nbrImages).reduceRegion({reducer: ee.Reducer.percentile([2, 98]), geometry: region,
                                               scale: scale, maxPixels: 1e10, bestEffort: true, tileScale: 4});
}

function nbrStretchFromStats(stats) {
  var lows = [], highs = [];
  Object.keys(stats).forEach(function (k) {
    if (stats[k] === null) return;
    if (/_p2$/.test(k)) lows.push(stats[k]);
    if (/_p98$/.test(k)) highs.push(stats[k]);
  });
  if (!lows.length || !highs.length) return null;
  return [Math.min.apply(null, lows), Math.max.apply(null, highs)];
}

exports.DECREASE = DECREASE;
exports.UNCHANGED = UNCHANGED;
exports.INCREASE = INCREASE;
exports.NOT_ANALYZED = NOT_ANALYZED;
exports.OUTCOME_LABELS = OUTCOME_LABELS;
exports.OUTCOME_COLORS = OUTCOME_COLORS;
exports.outcomeImage = outcomeImage;
exports.outcomeVis = outcomeVis;
exports.conditionLayerImage = conditionLayerImage;
exports.conditionVis = conditionVis;
exports.detectionTimingImage = detectionTimingImage;
exports.combineSeasonTiming = combineSeasonTiming;
exports.YEAR_COLORS = YEAR_COLORS;
exports.timingVis = timingVis;
exports.TRUE_COLOR = TRUE_COLOR;
exports.annualTrueColor = annualTrueColor;
exports.annualNbr = annualNbr;
exports.notWater = notWater;
exports.nbrStretchQuery = nbrStretchQuery;
exports.nbrStretchFromStats = nbrStretchFromStats;
