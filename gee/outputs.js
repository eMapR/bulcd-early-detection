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
//
// One pass over the bins in time order, carrying (above, count, last start)
// per pixel. The probability history is referenced once: the Code Editor
// expands every repeated reference to it when it describes a map layer, and
// "Description length exceeds maximum" otherwise (docs/findings.md, 2026-10-13).
var EPISODE_BANDS = ['last_decrease_year', 'last_decrease_doy', 'decrease_episodes'];
// episode_code = episodes * EPISODE_CODE_SCALE + start date code (year * 1000 + doy).
var EPISODE_CODE_SCALE = 1e7;

function dateCode(img) {
  var date = ee.Date(img.get('system:time_start'));
  return date.get('year').multiply(1000).add(date.getRelative('day', 'year').add(1));
}

function episodeState(probabilityStack, threshold) {
  var start = ee.Image.constant([0, 0, 0]).rename(['above', 'count', 'last']).toInt32();
  return ee.Image(probabilityStack.sort('system:time_start').iterate(function (img, state) {
    state = ee.Image(state);
    var above = img.select('decrease').gt(threshold).toInt32();
    var starts = above.and(state.select('above').not());
    return ee.Image.cat(above.rename('above'), state.select('count').add(starts).rename('count'),
                        state.select('last').where(starts, ee.Image.constant(dateCode(img)).toInt32()).rename('last'));
  }, start));
}

function decreaseEpisodeBands(probabilityStack, threshold) {
  var state = episodeState(probabilityStack, threshold), last = state.select('last');
  return ee.Image.cat(last.divide(1000).floor().rename('last_decrease_year'),
                      last.mod(1000).rename('last_decrease_doy'),
                      state.select('count').rename('decrease_episodes')).toFloat();
}

// One season's last detection and episodes as a single band, episode_code
// (episodes * EPISODE_CODE_SCALE + start of the last episode), masked where the
// season doesn't count: no episode, not analyzed, or with `confirmed` (the
// default) not ending as decrease - the same rule combineSeasonTiming()
// applies. One BULC-D run. outputs.py detection_episode_image().
function detectionEpisodeImage(bulcd, config, threshold, increaseThreshold, confirmed) {
  confirmed = confirmed === undefined ? true : confirmed;
  var result = bulcd.runBulcd(config);
  var outcome = outcomeImage(bulcd, result, config, threshold, increaseThreshold);
  var state = episodeState(result.probability_stack, threshold);
  var counts = confirmed ? outcome.eq(DECREASE) : outcome.lte(INCREASE);
  return state.select('count').toDouble().multiply(EPISODE_CODE_SCALE).add(state.select('last'))
    .updateMask(state.select('count').gt(0).and(counts)).rename('episode_code');
}

function detectionTimingImage(bulcd, config, threshold, increaseThreshold) {
  var result = bulcd.runBulcd(config);
  var outcome = outcomeImage(bulcd, result, config, threshold, increaseThreshold);
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

// Last detection and detection episodes from the earliest season that counts
// ({year: detectionEpisodeImage}, all built with the same `confirmed`): the
// same season combineSeasonTiming() selects. Each season is referenced once
// (an ImageCollection min over season index * 1e9 + episode_code), which keeps
// the layer description small. outputs.py combine_episode_metrics().
function combineEpisodeMetrics(seasonCodes) {
  var years = Object.keys(seasonCodes).map(Number).sort(function (a, b) { return a - b; });
  var earliest = ee.ImageCollection(years.map(function (y, i) {
    return seasonCodes[y].add(i * 1e9).rename('key');
  })).min().mod(1e9);
  var last = earliest.mod(EPISODE_CODE_SCALE);
  return ee.Image.cat(last.divide(1000).floor().rename('last_decrease_year'),
                      last.mod(1000).rename('last_decrease_doy'),
                      earliest.divide(EPISODE_CODE_SCALE).floor().rename('decrease_episodes')).toFloat();
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

// Reference imagery source: Sentinel-2 when every year shown is from
// REFERENCE_S2_FROM on, else Landsat for all of them, so one composite never
// mixes sources (outputs.py REFERENCE_S2_FROM, reference_source()).
var REFERENCE_S2_FROM = 2017;
var REFERENCE_SOURCE_LABELS = {S2: 'Sentinel-2', Landsat: 'Landsat'};
// Landsat Collection 2 Level 2 SR bands named as Sentinel-2's (outputs.py _LANDSAT_REFERENCE).
var LANDSAT_REFERENCE = {
  'LANDSAT/LT05/C02/T1_L2': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B7'],
  'LANDSAT/LE07/C02/T1_L2': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B7'],
  'LANDSAT/LC08/C02/T1_L2': ['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7'],
  'LANDSAT/LC09/C02/T1_L2': ['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7']
};
var S2_NAMES = ['B2', 'B3', 'B4', 'B8', 'B12'];  // blue, green, red, NIR, SWIR2

function referenceSource(years) {
  return Math.min.apply(null, years) >= REFERENCE_S2_FROM ? 'S2' : 'Landsat';
}

// Landsat 5/7/8/9 SR for one year's MM-DD window, QA_PIXEL-masked, with
// Sentinel-2 band names and scale (outputs.py _clear_landsat()).
function clearLandsat(region, year, window) {
  var out = null;
  Object.keys(LANDSAT_REFERENCE).forEach(function (id) {
    var bands = LANDSAT_REFERENCE[id];
    var col = ee.ImageCollection(id).filterBounds(region)
      .filterDate(year + '-' + window[0], year + '-' + window[1])
      .map(function (image) {
        var clear = image.select('QA_PIXEL').bitwiseAnd(31).eq(0);
        return image.select(bands, S2_NAMES).multiply(0.275).add(-2000).updateMask(clear);
      });
    out = out ? out.merge(col) : col;
  });
  return out;
}

function clearImagery(region, year, window, source) {
  return source === 'Landsat' ? clearLandsat(region, year, window) : clearS2(region, year, window);
}

// outputs.py annual_true_color(); source 'S2' (default) or 'Landsat'.
function annualTrueColor(region, year, window, source) {
  return clearImagery(region, year, window, source).select(['B4', 'B3', 'B2']).median();
}

// Sentinel-2 NBR median for one year, on a fixed 30 m UTM grid unless
// `reproject` is false (large areas). outputs.py annual_nbr().
function annualNbr(region, year, window, crs, reproject, source) {
  var nbr = clearImagery(region, year, window, source).map(function (i) { return i.normalizedDifference(['B8', 'B12']); })
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

// ---------------------------------------------------------------- export
// Data (not the colored map layers) a run can export to Google Drive or a Cloud
// Storage bucket as GeoTIFFs. Masked pixels (water, outside the area, no detection) are written
// as EXPORT_NODATA, since 0 is a real value in several bands (outcome 0 =
// decrease).
var EXPORT_NODATA = -9999;

// Earth Engine allows letters, digits, '_' and '-' (and a few others) in task
// descriptions and file names, at most 100 characters.
function exportName(parts) {
  return parts.join('_').replace(/[^A-Za-z0-9_-]+/g, '_').replace(/_+/g, '_').replace(/^_|_$/g, '').slice(0, 100);
}

// The run's datasets, in the app's layer order: [{key, label, image, scale,
// bands}]. `run`: {result, outcome, timing, episodes, monitoringYear, imgYears,
// window, imgSource, geom, crs}. Images are clipped to the area and cast to one
// type per file (GeoTIFF bands must share a type).
function exportDatasets(run) {
  var geom = run.geom, list = [];
  function add(key, label, image, bands, scale) {
    list.push({key: key, label: label, image: image.select(bands).clip(geom), bands: bands, scale: scale});
  }
  var final = run.result.final_probabilities;
  add('condition', 'Condition ' + run.monitoringYear + ': outcome (0 decrease, 1 unchanged, 2 increase, ' +
      '3 not analyzed) and final probabilities',
      ee.Image.cat(run.outcome.select('outcome'), final.select(['decrease', 'unchanged', 'increase']))
        .rename(['outcome', 'p_decrease', 'p_unchanged', 'p_increase']).toFloat(),
      ['outcome', 'p_decrease', 'p_unchanged', 'p_increase'], 30);
  if (run.timing) {
    add('first_detected', 'First detected season (decrease): year, day of year', run.timing.toFloat(),
        ['first_decrease_year', 'first_decrease_doy'], 30);
    add('last_detection_episodes', 'Last detection (year, day of year) and detection episodes (decrease)',
        run.episodes.toFloat(), ['last_decrease_year', 'last_decrease_doy', 'decrease_episodes'], 30);
  }
  var landsat = run.imgSource !== 'S2', src = REFERENCE_SOURCE_LABELS[run.imgSource];
  run.imgYears.forEach(function (y) {
    add('true_color_' + y, 'True color ' + y + ' (' + src + ' median, B4 B3 B2' +
        (landsat ? ' on the Sentinel-2 scale' : '') + ')',
        annualTrueColor(geom, y, run.window, run.imgSource).toInt16(), ['B4', 'B3', 'B2'], landsat ? 30 : 10);
  });
  var nbrBands = run.imgYears.map(function (y) { return 'nbr_' + y; });
  add('nbr', 'NBR ' + run.imgYears.join(', ') + ' (' + src + ' median, one band per year)',
      ee.Image.cat(run.imgYears.map(function (y) {
        return annualNbr(geom, y, run.window, run.crs, false, run.imgSource);
      })).toFloat(), nbrBands, 30);
  return list;
}

// Why a Cloud Storage bucket name can't be used, or null. Earth Engine only
// reports a missing bucket or missing write access when the task runs.
function bucketProblem(bucket) {
  if (!bucket) return 'Enter a bucket name.';
  if (!/^[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]$/.test(bucket)) {
    return '"' + bucket + '" is not a bucket name: enter the name only (no gs:// or /), using lowercase ' +
           'letters, digits, "-", "_" and ".". A folder inside the bucket goes in Path.';
  }
  return null;
}

// The task name and destination shared by every export. `target`: {folder} for
// Google Drive, or {bucket, path} for Cloud Storage (path optional, no outer /).
function exportTarget(target, name) {
  if (target.bucket) {
    return {description: name, bucket: target.bucket, fileNamePrefix: (target.path ? target.path + '/' : '') + name};
  }
  return {description: name, folder: target.folder, fileNamePrefix: name};
}

// Export.image.toDrive() / toCloudStorage() parameters for one dataset.
function exportParams(dataset, run, target, prefix) {
  var params = exportTarget(target, exportName([prefix, dataset.key]));
  params.image = dataset.image;
  params.region = run.geom;
  params.scale = dataset.scale;
  params.crs = run.crs;
  params.maxPixels = 1e13;
  params.fileFormat = 'GeoTIFF';
  params.formatOptions = {cloudOptimized: true, noData: EXPORT_NODATA};
  return params;
}

// Export.table.toDrive() / toCloudStorage() parameters for the run settings CSV.
function exportSettingsParams(settings, target, prefix) {
  var params = exportTarget(target, exportName([prefix, 'settings']));
  params.collection = settings;
  params.fileFormat = 'CSV';
  return params;
}

exports.EXPORT_NODATA = EXPORT_NODATA;
exports.exportName = exportName;
exports.exportDatasets = exportDatasets;
exports.bucketProblem = bucketProblem;
exports.exportParams = exportParams;
exports.exportSettingsParams = exportSettingsParams;
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
exports.detectionEpisodeImage = detectionEpisodeImage;
exports.EPISODE_CODE_SCALE = EPISODE_CODE_SCALE;
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
exports.referenceSource = referenceSource;
exports.REFERENCE_S2_FROM = REFERENCE_S2_FROM;
exports.REFERENCE_SOURCE_LABELS = REFERENCE_SOURCE_LABELS;
exports.annualNbr = annualNbr;
exports.notWater = notWater;
exports.nbrStretchQuery = nbrStretchQuery;
exports.nbrStretchFromStats = nbrStretchFromStats;
