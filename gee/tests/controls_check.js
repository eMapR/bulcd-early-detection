// Offline check of the settings panel (no Earth Engine): the defaults against
// the original BULC-D GUI's settings (legacy_gui.js), the day list following the
// month (an out-of-range day moves to the month's last day), and the
// expectation-year summary.
// usage: node controls_check.js
const assert = require('assert');
const { makeUi } = require('./ui_stub');
const appConfig = require('../config.js');
const { LEGACY_DEFAULTS } = require('./legacy_gui');
const path = require('path');
const bulcd = require(path.join(process.env.BULCD_GEE || path.join(__dirname, '..', '..', '..', 'BULC-D_rebuild', 'gee'),
                                'bulcd.js'));

const { ui, created } = makeUi();
global.ui = ui;
const controls = require('../controls.js').makeControls(appConfig);
const AOI = { aoi_asset: 'x' };
// selects in creation order: expectation first/last, monitoring, start month/day, end month/day
const [expFirst, expLast, , startMonth, startDay, endMonth, endDay] = created.selects;
const status = () => created.labels.map((l) => l.state.value).join('\n');

// Defaults are valid and unchanged.
assert.strictEqual(appConfig.validateControls(controls.read()), null);
assert.deepStrictEqual([controls.read().season_start, controls.read().season_end], ['06-01', '09-30']);

// Defaults match the original BULC-D GUI wherever it had one (legacy_gui.js).
const d = controls.read(), cfg = appConfig.buildConfig(d, AOI), adv = cfg.bulc_advanced_params;
assert.strictEqual(d.sensitivity, LEGACY_DEFAULTS.z_score_numerator_factor);
assert.strictEqual(cfg.sensitivity.z_score_numerator_factor, LEGACY_DEFAULTS.z_score_numerator_factor);
assert.strictEqual(d.dampening, LEGACY_DEFAULTS.dampening_factor);
assert.strictEqual(adv.dampening_factor, LEGACY_DEFAULTS.dampening_factor);
assert.strictEqual(d.posterior_leveler, LEGACY_DEFAULTS.posterior_leveler);
assert.strictEqual(adv.posterior_leveler, LEGACY_DEFAULTS.posterior_leveler);
assert.strictEqual(adv.initializing_leveler, LEGACY_DEFAULTS.initializing_leveler);
// bulcd's starting prior: one-hot "unchanged" leveled as x * L + (1 - L) / 3.
const L = adv.initializing_leveler;
const start = { decrease: (1 - L) / 3, unchanged: L + (1 - L) / 3, increase: (1 - L) / 3 };
Object.keys(start).forEach((k) =>
  assert(Math.abs(start[k] - LEGACY_DEFAULTS.starting_probabilities[k]) < 1e-12, 'starting P(' + k + ')'));
assert.deepStrictEqual(adv.custom_transition_matrix, appConfig.PRODUCTION_TRANSITION_MATRIX);
assert.strictEqual(d.mask_forest, LEGACY_DEFAULTS.mask_forest);
assert.strictEqual(cfg.study_area.mask_non_forest, LEGACY_DEFAULTS.mask_forest);
assert.strictEqual(d.mask_water, LEGACY_DEFAULTS.mask_water);
assert.strictEqual(cfg.study_area.mask_water, LEGACY_DEFAULTS.mask_water);
assert.deepStrictEqual(cfg.modality, LEGACY_DEFAULTS.modality);
assert.strictEqual(cfg.reduction.band, 'nbr');
// From bulcd's defaults: z-score denominator 0.05 and the bin cuts as in the
// original GUI; day step 4 (the original slider starts at 3; set to 4 to compare).
const full = bulcd.withDefaults(cfg);
assert.strictEqual(full.sensitivity.z_score_denominator_factor, LEGACY_DEFAULTS.z_score_denominator_factor);
assert.deepStrictEqual(full.bin_cuts, LEGACY_DEFAULTS.bin_cuts);
assert.strictEqual(full.evidence.day_step_size, 4);
// Separate thresholds, as the original GUI's drop/gain sliders.
assert.strictEqual(d.decrease_threshold, LEGACY_DEFAULTS.decrease_threshold);
assert.strictEqual(d.increase_threshold, LEGACY_DEFAULTS.increase_threshold);
assert.match(appConfig.validateControls(Object.assign({}, d, { increase_threshold: 1.0 })), /increase threshold/);

// The inspector applies each class's own threshold, strictly (> as legacy .gt()).
const inspector = require('../inspector.js');
const rows = [
  { date: '2026-06-01', decrease: 0.65, unchanged: 0.25, increase: 0.10 },   // at, not above, 0.65
  { date: '2026-06-05', decrease: 0.66, unchanged: 0.24, increase: 0.10 },
  { date: '2026-06-09', decrease: 0.10, unchanged: 0.20, increase: 0.70 },   // above 0.65, below 0.75
  { date: '2026-06-13', decrease: 0.10, unchanged: 0.10, increase: 0.80 },
];
assert.deepStrictEqual(inspector.crossingNotes(rows, d.decrease_threshold, d.increase_threshold), [
  'decrease first crossed its threshold (0.65) on 2026-06-05, finished below its threshold (does not count)',
  'increase first crossed its threshold (0.75) on 2026-06-13, finished the season as increase (counts as detected)',
]);
assert.deepStrictEqual(inspector.crossingNotes(rows.slice(0, 1), 0.65, 0.75),
                       ['never crossed a threshold (decrease 0.65, increase 0.75)']);
const prob = inspector.probabilityTable(rows, d.decrease_threshold, d.increase_threshold);
assert.deepStrictEqual(prob.cols.slice(4).map((c) => c.label), ['decrease threshold (0.65)', 'increase threshold (0.75)']);
assert.deepStrictEqual(prob.rows[0].c.slice(4).map((x) => x.v), [0.65, 0.75]);
// One shared threshold still draws one line (the reference case).
assert.deepStrictEqual(inspector.probabilityTable(rows, 0.5).cols.slice(4).map((c) => c.label),
                       ['decision threshold (0.5)']);

// Expectation years are inclusive: one season per year.
expFirst.setValue('2024'); expLast.setValue('2024');
assert.match(status(), /2024-2024 uses 1 annual season \(the season window in 2024\)/);
expFirst.setValue('2023');
assert.match(status(), /2023-2024 uses 2 annual seasons \(the season window in 2023 and 2024\)/);
assert.strictEqual(appConfig.buildConfig(Object.assign(controls.read(), { monitoring_year: 2025 }), AOI)
  .evidence.expectation.sensors.L8.last_year, 2025);  // exclusive end = 2024 + 1
expFirst.setValue('2018'); expLast.setValue('2023');

// The day list follows the month: Mar 31 -> April becomes Apr 30; Feb has 28 days.
const days = (sel) => sel.items().items;
startMonth.setValue('3'); startDay.setValue('31'); startMonth.setValue('4');
assert.strictEqual(controls.read().season_start, '04-30');
assert.strictEqual(days(startDay).length, 30);
startDay.setValue('30'); startMonth.setValue('2');
assert.strictEqual(controls.read().season_start, '02-28');
assert.strictEqual(days(startDay).length, 28);
startMonth.setValue('6'); startDay.setValue('1');
assert.strictEqual(appConfig.validateControls(controls.read()), null);

// Dec 31 is valid.
endMonth.setValue('12'); endDay.setValue('31');
assert.strictEqual(days(endDay).length, 31);
assert.strictEqual(appConfig.validateControls(controls.read()), null);
assert.strictEqual(appConfig.buildConfig(Object.assign(controls.read(), { monitoring_year: 2025 }), AOI)
  .evidence.target.sensors.L8.last_doy, 365);

console.log('defaults vs original BULC-D GUI: sensitivity ' + d.sensitivity + ', thresholds ' + d.decrease_threshold +
            ' decrease / ' + d.increase_threshold + ' increase, dampening ' + d.dampening +
            ', posterior ' + d.posterior_leveler + ', starting odds ' + [start.decrease, start.unchanged,
            start.increase].map((x) => x.toFixed(2)).join('/') + ', forest mask ' + d.mask_forest + ', water mask ' +
            d.mask_water + ' - ok');
console.log('controls check: OK');
