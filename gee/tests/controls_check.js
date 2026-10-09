// Offline check of the settings panel (no Earth Engine): the day list follows the
// month (an out-of-range day moves to the month's last day), and the
// expectation-year summary.
// usage: node controls_check.js
const assert = require('assert');
const { makeUi } = require('./ui_stub');
const appConfig = require('../config.js');

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

console.log('controls check: OK');
