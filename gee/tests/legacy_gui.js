// The original BULC-D GUI's settings, read from its source in ../BULC-D_rebuild
// (test fixture only; never deployed). controls_check.js holds the app's
// defaults to these.
//
// Settings with a default in the original GUI:
const LEGACY_DEFAULTS = {
  // guiBULCD.rtf "Sensitivity": ZScoreNumeratorFactor: 1, ZScoreDenominatorFactor: 0.05
  z_score_numerator_factor: 1.0,
  z_score_denominator_factor: 0.05,
  // legacy/6003.3c-BULC-AdvancedParameters.txt getBULCParameterDictionary()
  // (required by guiBULCD.rtf): transitionLeveler = 0.7, posteriorLeveler = 0.9,
  // initializingLeveler = 0.7 applied to baseLandCoverImage = ee.Image(2)
  // ("unchanged"), i.e. one_hot * 0.7 + 0.3 / 3 (BULC-Minimal-Module-107.txt
  // afn_LevelInitialLCExploded).
  dampening_factor: 0.7,
  posterior_leveler: 0.9,
  initializing_leveler: 0.7,
  starting_probabilities: { decrease: 0.1, unchanged: 0.8, increase: 0.1 },
  // guiBULCD.rtf analysis sliders: dropThresholdToDenoteChange setValue(0.65),
  // gainThresholdToDenoteChange setValue(0.75); applied with .gt() in
  // legacy/6002.C2-BULCD-Module-analyzeOutputs.txt.
  decrease_threshold: 0.65,
  increase_threshold: 0.75,
  // guiBULCD.rtf day-step slider: min 1, max 16, value 3. The app keeps bulcd's
  // 4 (the original GUI's slider was set to 4 for the same-pixel comparison).
  day_step_slider: 3,
  // guiBULCD.rtf: theWaterMask = afn_waterMask().not() on the outputs; no forest mask.
  mask_water: true,
  mask_forest: false,
  // guiBULCD.rtf: binCuts [-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2]; modality constant + unimodal.
  bin_cuts: [-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2],
  modality: { constant: true, unimodal: true },
};

// Entered by the user, with no default in the original GUI (blank boxes or
// unchecked boxes): one sensor selection shared by both periods (datasetSelection,
// all false), the expectation and target years (unchecked year boxes), first/last
// day of year ("Choose between 1 and 365") and cloud cover ("choose percentage").
const LEGACY_USER_ENTERED = ['sensors', 'expectation_years', 'monitoring_year', 'season', 'cloud_cover'];

module.exports = { LEGACY_DEFAULTS, LEGACY_USER_ENTERED };
