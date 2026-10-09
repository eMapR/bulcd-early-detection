// JS side of the app parity test.
//   1. The legacy reference case (tests/reference_case.js; not in the GUI) run
//      through the app's modules: condition over a box and inspector rows and
//      chart tables at reference pixels 1-3.
//   2. app.js main() with a stub `ui`, driven through its own widgets: asset area
//      (the testsite), notebook-default settings, "Run Early Detection";
//      condition and first-detected-season layers over the box; the inspector at
//      pixel 1 by map click and at pixel 3 by typed lon/lat + Submit Pixel.
//   3. The configs a non-default settings combination produces (no computation).
// usage: node app_extract.js <out.json>
const fs = require('fs');
const path = require('path');

const BULCD_GEE = process.env.BULCD_GEE || path.join(__dirname, '..', '..', '..', 'BULC-D_rebuild', 'gee');
const { ee, init, evaluate } = require(path.join(BULCD_GEE, 'tests', 'ee_node'));
const bulcd = require(path.join(BULCD_GEE, 'bulcd.js'));
const appConfig = require('../config.js');
const outputs = require('../outputs.js');
const inspector = require('../inspector.js');
const aoi = require('../aoi.js');
const controlsUi = require('../controls.js');
const app = require('../app.js');
const { makeUi } = require('./ui_stub');
const { TESTSITE, REFERENCE_CASE, REFERENCE_PIXELS, THRESHOLD } = require('./reference_case');

// Same box as BULC-D_rebuild gee/tests/cases.py BOX.
const BOX = [-123.5725, 44.8300, -123.5400, 44.8500];
// Must match run_app_parity.py VARIANT.
const VARIANT = {
  expectation_first: 2019, expectation_last: 2023, monitoring_year: 2025, season_start: '05-15',
  season_end: '10-15', sensitivity: 1.5, decision_threshold: 0.6, timing: true, dampening: 0.7,
  posterior_leveler: 0.9, sensors: { L8: true, L9: true, S2: false }, mask_forest: false, mask_water: true,
  allow_large: false,
};

function waitFor(predicate, what, ms = 900000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    (function poll() {
      if (predicate()) return resolve();
      if (Date.now() - start > ms) return reject(new Error('timed out waiting for ' + what));
      setTimeout(poll, 250);
    })();
  });
}

function labelText(created) {
  return created.labels.map((l) => l.state.value).join('\n');
}

function pixelRecord(p, rows, fit, prob, threshold) {
  return {
    lon: p.lon, lat: p.lat, rows,
    fit_table_rows: fit ? fit.rows.length : 0,
    prob_table: prob ? prob.rows.map((r) => r.c.slice(1).map((x) => x.v)) : null,
    notes: inspector.crossingNotes(rows, threshold),
  };
}

// Selects each pixel the way a user does - a map click, or typing the coordinate and
// pressing Submit Pixel - and records what the inspector charted.
async function selectPixels(handle, created, map, pixels, how, threshold) {
  const out = {};
  for (const p of pixels) {
    const before = created.charts.length;
    if (how[p.label] === 'submit') {
      handle.lonBox.setValue(String(p.lon));
      handle.latBox.setValue(String(p.lat));
      handle.submit.state.handlers.click();
    } else {
      map.state.handlers.click({ lon: p.lon, lat: p.lat });
    }
    await waitFor(() => created.charts.length >= before + 2 || /No clear|failed/.test(labelText(created)),
                  'the inspector at ' + p.label);
    const [fit, prob] = created.charts.slice(before);
    const run = handle.state.run;
    const tables = await evaluate(inspector.historyQuery(run.result, run.config, p.lon, p.lat));
    const rows = inspector.historyRows(tables, run.config);
    out[p.label] = pixelRecord(p, rows, fit && fit.table, prob && prob.table, threshold);
    out[p.label].how = how[p.label] || 'click';
    out[p.label].boxes = [handle.lonBox.getValue(), handle.latBox.getValue()];
  }
  return out;
}

function boxRegion(image) {
  return evaluate(ee.ImageCollection([image.set('system:time_start', 0)])
    .getRegion(ee.Geometry.Rectangle(BOX), 30, 'EPSG:32610'));
}

async function main(out) {
  await init();
  const { ui, created } = makeUi();
  global.ui = ui;
  const data = { reference: {}, notebook: {}, variant: {} };

  // 1. Legacy reference case, through the app's modules (no GUI).
  const refConfig = bulcd.withDefaults(REFERENCE_CASE);
  const refResult = bulcd.runBulcd(refConfig);
  data.reference.config = refConfig;
  data.reference.outcome_box = await boxRegion(outputs.outcomeImage(bulcd, refResult, refConfig, THRESHOLD));
  data.reference.pixels = {};
  for (const p of REFERENCE_PIXELS) {
    const rows = inspector.historyRows(await evaluate(inspector.historyQuery(refResult, refConfig, p.lon, p.lat)),
                                       refConfig);
    data.reference.pixels[p.label] = pixelRecord(p, rows, inspector.targetFitTable(rows, 'nbr'),
                                                 inspector.probabilityTable(rows, THRESHOLD), THRESHOLD);
  }

  // 2. The GUI: asset area, notebook-default settings, Run Early Detection.
  const handle = app.main(bulcd, appConfig, outputs, inspector, aoi, controlsUi);
  const map = created.maps[0];
  data.gui_labels = created.labels.map((l) => l.state.value).filter(Boolean);
  data.gui_buttons = created.buttons.map((b) => b.state.value);
  data.gui_area_sources = handle.source.items().items;
  handle.source.setValue(handle.AREA_SOURCES.asset);
  handle.assetBox.setValue(TESTSITE);
  // 2. Notebook defaults, through the widgets and the Run button.
  const controls = handle.controls.read();
  data.notebook.controls = controls;
  handle.runButton.state.handlers.click();
  await waitFor(() => handle.state.run, 'the notebook-default run');
  const run = handle.state.run, area = handle.state.area;
  data.area_report = area.report;
  data.notebook.label = run.label;
  data.notebook.config = run.config;
  data.notebook.timing_years = appConfig.timingYears(controls);
  data.notebook.timing_configs = data.notebook.timing_years.map((y) =>
    bulcd.withDefaults(appConfig.buildConfig(appConfig.withMonitoringYear(controls, y), area.aoi)));
  await waitFor(() => map.state.layers.items.some((l) => /^NBR composite/.test(l.name) && !/loading/.test(l.name)),
                'the NBR composite stretch');
  data.notebook.layers = map.state.layers.items.map((l) => ({ name: l.name, shown: l.shown, opacity: l.opacity }));
  data.notebook.outcome_box = await boxRegion(run.outcome.select('outcome'));
  data.notebook.timing_box = await boxRegion(run.timing.select(['first_decrease_year', 'first_decrease_doy']));
  data.notebook.pixels = await selectPixels(handle, created, map, [REFERENCE_PIXELS[0], REFERENCE_PIXELS[2]],
                                            { [REFERENCE_PIXELS[2].label]: 'submit' }, controls.decision_threshold);

  // 3. Non-default settings: configs only.
  data.variant.config = bulcd.withDefaults(appConfig.buildConfig(VARIANT, area.aoi));
  data.variant.timing_years = appConfig.timingYears(VARIANT);
  data.variant.timing_configs = data.variant.timing_years.map((y) =>
    bulcd.withDefaults(appConfig.buildConfig(appConfig.withMonitoringYear(VARIANT, y), area.aoi)));

  fs.writeFileSync(out, JSON.stringify(data));
}

main(process.argv[2]).catch((e) => { console.error(e); process.exit(1); });
