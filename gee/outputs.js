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

// {decrease: threshold, increase: increaseThreshold, or threshold when that is
// not given} (config.py class_thresholds()).
function classThresholds(threshold, increaseThreshold) {
  return {decrease: threshold, increase: increaseThreshold == null ? threshold : increaseThreshold};
}

// DECREASE where P(decrease) exceeds `threshold`, INCREASE where P(increase)
// exceeds `increaseThreshold` (default `threshold`; both >= 0.5, so at most one
// can), else UNCHANGED - the original BULC-D GUI's .gt() rule (its defaults:
// 0.65 decrease, 0.75 increase); NOT_ANALYZED on land excluded by the
// non-forest mask; masked on water. Band 'outcome', float.
function outcomeImage(bulcd, result, config, threshold, increaseThreshold) {
  var t = classThresholds(threshold, increaseThreshold);
  var final = result.final_probabilities;
  var dec = final.select('decrease'), inc = final.select('increase');

  var analyzed = bulcd.studyAreaMask(config);
  analyzed = analyzed === null ? ee.Image.constant(1) : analyzed;
  var waterOnly = copy(config);
  waterOnly.study_area.mask_water = true;
  waterOnly.study_area.mask_non_forest = false;
  var land = bulcd.studyAreaMask(waterOnly);

  var changed = ee.Image.constant(UNCHANGED).where(dec.gt(t.decrease), DECREASE).where(inc.gt(t.increase), INCREASE)
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
// `threshold` (the decrease threshold; bin END date), masked where it never did
// or the pixel isn't analyzed; plus `outcome`, the state at the end of the run
// (with `increaseThreshold`). outputs.py detection_timing_image().
// Detection episodes in one run (outputs.py decrease_episode_bands()): an
// episode starts at a bin where P(decrease) > threshold after one at or below
// it, and ends at the next bin at or below it; bins without an observation
// carry the previous probability, so they never start or end one. Bands
// decrease_episodes, last_decrease_year/doy (start of the most recent
// episode); 0 where there was none.
var EPISODE_BANDS = ['last_decrease_year', 'last_decrease_doy', 'decrease_episodes'];

function dateCode(img) {
  var date = ee.Date(img.get('system:time_start'));
  return date.get('year').multiply(1000).add(date.getRelative('day', 'year').add(1));
}

function decreaseEpisodeBands(probabilityStack, threshold) {
  var arr = probabilityStack.sort('system:time_start').map(function (img) {
    return img.select('decrease').gt(threshold).toInt32().rename('above')
      .addBands(ee.Image.constant(dateCode(img)).toInt32().rename('code'));
  }).toArray();                                                   // [bins, (above, code)]
  var above = arr.arraySlice(1, 0, 1);
  var before = ee.Image(ee.Array([[0]])).arrayCat(above.arraySlice(0, 0, -1), 0);  // below at the start
  var starts = above.gt(before);
  var count = starts.arrayReduce(ee.Reducer.sum(), [0]).arrayGet([0, 0]);
  var last = arr.arraySlice(1, 1, 2).multiply(starts).arrayReduce(ee.Reducer.max(), [0]).arrayGet([0, 0]);
  return ee.Image.cat(last.divide(1000).floor().rename('last_decrease_year'),
                      last.mod(1000).rename('last_decrease_doy'),
                      count.rename('decrease_episodes')).toFloat();
}

// `episodes` appends EPISODE_BANDS from the same run; the first three bands
// are the same either way.
function detectionTimingImage(bulcd, config, threshold, increaseThreshold, episodes) {
  var result = bulcd.runBulcd(config);
  var outcome = outcomeImage(bulcd, result, config, threshold, increaseThreshold);
  var first = result.probability_stack.map(function (img) {
    var date = ee.Date(img.get('system:time_start'));
    var value = date.get('year').multiply(1000).add(date.getRelative('day', 'year').add(1));
    return ee.Image.constant(value).toInt32().rename('code').updateMask(img.select('decrease').gt(threshold));
  }).min().updateMask(outcome.lte(INCREASE));
  var year = first.divide(1000).floor().rename('first_decrease_year');
  var doy = first.mod(1000).rename('first_decrease_doy');
  var out = ee.Image.cat(year.toFloat(), doy.toFloat(), outcome.toFloat());
  if (episodes) out = out.addBands(decreaseEpisodeBands(result.probability_stack, threshold).updateMask(first.mask()));
  return out;
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

// Last detection and detection episodes for the season combineSeasonTiming()
// (same `confirmed`) selects, from that season's own run
// (detectionTimingImage(..., true)). outputs.py combine_episode_metrics().
function combineEpisodeMetrics(seasons, confirmed) {
  confirmed = confirmed === undefined ? true : confirmed;
  var years = Object.keys(seasons).map(Number).sort(function (a, b) { return a - b; });
  var chosen = {};
  EPISODE_BANDS.forEach(function (b) { chosen[b] = ee.Image(0).toFloat(); });
  years.slice().reverse().forEach(function (y) {  // earliest season written last, so it wins
    var s = seasons[y];
    var crossed = s.select('first_decrease_year').mask().and(s.select('first_decrease_year').unmask(0).gt(0));
    if (confirmed) crossed = crossed.and(s.select('outcome').eq(DECREASE));
    EPISODE_BANDS.forEach(function (b) { chosen[b] = chosen[b].where(crossed, s.select(b).unmask(0)); });
  });
  var found = chosen.decrease_episodes.gt(0);
  var mask = seasons[years[years.length - 1]].select('outcome').mask();
  return ee.Image.cat(EPISODE_BANDS.map(function (b) {
    return chosen[b].updateMask(found).updateMask(mask).rename(b);
  }));
}

// Last-detection layer (render.py LAST_DETECTION_PALETTE): position in the
// seasons, season index + fraction of the season window, so dates within one
// season are told apart; earliest = darkest.
var LAST_DETECTION_PALETTE = ['#440154', '#3b528b', '#21918c', '#5ec962', '#fde725'];

function lastDetectionImage(metrics, years, firstDoy, lastDoy) {
  return metrics.select('last_decrease_year').subtract(years[0])
    .add(metrics.select('last_decrease_doy').subtract(firstDoy).divide(lastDoy - firstDoy + 1))
    .rename('last_detection');
}

function lastDetectionVis(years) {
  return {min: 0, max: years.length, palette: LAST_DETECTION_PALETTE.map(function (c) { return c.slice(1); })};
}

// Palette color at fraction f (0..1), linear in RGB (render.py palette_color()).
function paletteColor(palette, f) {
  f = Math.min(Math.max(f, 0), 1);
  var x = f * (palette.length - 1), i = Math.min(Math.floor(x), palette.length - 2), t = x - i;
  var rgb = function (c) { return [1, 3, 5].map(function (k) { return parseInt(c.substr(k, 2), 16); }); };
  var a = rgb(palette[i]), b = rgb(palette[i + 1]);
  return '#' + a.map(function (v, k) {
    var h = Math.round(v + (b[k] - v) * t).toString(16);
    return h.length < 2 ? '0' + h : h;
  }).join('');
}

// [[color, label]]: each season's start, middle and end (render.py last_detection_legend()).
function lastDetectionLegend(years, startLabel, endLabel) {
  var out = [];
  years.forEach(function (y, i) {
    [[0, startLabel + ' ' + y], [0.5, 'mid-season ' + y], [1, endLabel + ' ' + y]].forEach(function (p) {
      out.push([paletteColor(LAST_DETECTION_PALETTE, (i + p[0]) / years.length), p[1]]);
    });
  });
  return out;
}

// Detection-episodes layer: 1, 2, 3 or more.
var EPISODE_COLORS = ['#c6b3e6', '#8c6bc8', '#4b2991'];
var EPISODE_LABELS = ['1 detection episode', '2 detection episodes', '3 or more detection episodes'];

function episodesImage(metrics) {
  return metrics.select('decrease_episodes').min(3).rename('episodes');
}

function episodesVis() {
  return {min: 1, max: 3, palette: EPISODE_COLORS.map(function (c) { return c.slice(1); })};
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

exports.classThresholds = classThresholds;
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
exports.EPISODE_BANDS = EPISODE_BANDS;
exports.decreaseEpisodeBands = decreaseEpisodeBands;
exports.combineEpisodeMetrics = combineEpisodeMetrics;
exports.LAST_DETECTION_PALETTE = LAST_DETECTION_PALETTE;
exports.lastDetectionImage = lastDetectionImage;
exports.lastDetectionVis = lastDetectionVis;
exports.paletteColor = paletteColor;
exports.lastDetectionLegend = lastDetectionLegend;
exports.EPISODE_COLORS = EPISODE_COLORS;
exports.EPISODE_LABELS = EPISODE_LABELS;
exports.episodesImage = episodesImage;
exports.episodesVis = episodesVis;
exports.YEAR_COLORS = YEAR_COLORS;
exports.timingVis = timingVis;
exports.TRUE_COLOR = TRUE_COLOR;
exports.annualTrueColor = annualTrueColor;
exports.annualNbr = annualNbr;
exports.notWater = notWater;
exports.nbrStretchQuery = nbrStretchQuery;
exports.nbrStretchFromStats = nbrStretchFromStats;
