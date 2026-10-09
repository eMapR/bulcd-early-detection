// Classification map from a bulcd.js result: the Early Detection decision rule.
//
// JS mirror of src/bulcd_early_detection/outputs.py _outcome_from_result()
// (outcome band only, for Milestone 1). Interpretation of bulcd outputs only;
// no detection logic. gee/tests/run_app_parity.py checks it against Python.
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

function outcomeVis() {
  return {min: DECREASE, max: NOT_ANALYZED,
          palette: [DECREASE, UNCHANGED, INCREASE, NOT_ANALYZED].map(function (k) {
            return OUTCOME_COLORS[k].slice(1);
          })};
}

exports.DECREASE = DECREASE;
exports.UNCHANGED = UNCHANGED;
exports.INCREASE = INCREASE;
exports.NOT_ANALYZED = NOT_ANALYZED;
exports.OUTCOME_LABELS = OUTCOME_LABELS;
exports.OUTCOME_COLORS = OUTCOME_COLORS;
exports.outcomeImage = outcomeImage;
exports.outcomeVis = outcomeVis;
