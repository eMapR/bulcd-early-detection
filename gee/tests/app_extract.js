// JS side of the app parity test.
//   1. The legacy reference case (tests/reference_case.js; not in the GUI) run
//      through the app's modules: condition over a box and inspector rows and
//      chart tables at reference pixels 1-3.
//   2. app.js main() with a stub `ui`, driven through its own widgets: asset area
//      (the testsite), default settings, "Run Early Detection";
//      condition (with the final probabilities, to check the decision rule),
//      first-detected-season, last-detection and detection-episode layers over
//      the box; the inspector at pixel 1 by map click and at pixel 3 by typed
//      lon/lat + Submit Pixel, including the expectation period (observations
//      used in the fit, the fitted curve, the fit's coefficients/residual
//      SD/R2) and the timeline chart.
//   2b. The same GUI run with detection timing set to raw (Advanced settings):
//      first-detected-season and episode layers over the box.
//   3. The configs a non-default settings combination produces (no computation).
//   4. Expectation fit orders 2 and 3, each chosen in the GUI's Advanced settings
//      and run (order 1 is the default run in 2): configs, condition,
//      first-detected-season and episode layers over the box, and the inspector
//      (rows, expectation fit, summary) at pixel 1.
//   5. Robert's Pine Mountain pixel (docs/findings.md 2026-10-13): detection
//      timing image (first/last detection, episodes) and inspector rows there.
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
const { tablesClose } = require('./table_close');
const { TESTSITE, REFERENCE_CASE, REFERENCE_PIXELS, THRESHOLD } = require('./reference_case');

// Same box as BULC-D_rebuild gee/tests/cases.py BOX.
const BOX = [-123.5725, 44.8300, -123.5400, 44.8500];
// Must match run_app_parity.py VARIANT.
const VARIANT = {
  expectation_first: 2019, expectation_last: 2023, monitoring_year: 2025, season_start: '05-15',
  season_end: '10-15', sensitivity: 1.5, decrease_threshold: 0.6, increase_threshold: 0.8, timing: true,
  dampening: 0.5, posterior_leveler: 1.0, fit_order: 2, sensors: { L8: true, L9: true, S2: false },
  mask_forest: true, mask_water: true, allow_large: false,
};
// Must match run_app_parity.py FIT_ORDERS_RUN.
const FIT_ORDERS_RUN = [2, 3];
// Must match run_app_parity.py PINE_MOUNTAIN.
const PM = { lon: -120.95938356858395, lat: 43.69499215695442, half: 0.01 };
const PM_CONTROLS = Object.assign({}, appConfig.APP_DEFAULTS, {
  expectation_first: 2023, expectation_last: 2023, monitoring_year: 2024, season_start: '02-01', season_end: '11-15',
});
const TIMING_BOX_BANDS = ['first_decrease_year', 'first_decrease_doy'];

async function runGui(handle, what) {
  const prev = handle.state.run;
  handle.runButton.state.handlers.click();
  await waitFor(() => handle.state.run && handle.state.run !== prev, what);
  return handle.state.run;
}

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

function pixelRecord(p, rows, fit, prob, threshold, increaseThreshold) {
  return {
    lon: p.lon, lat: p.lat, rows,
    fit_table_rows: fit ? fit.rows.length : 0,
    prob_table: prob ? prob.rows.map((r) => r.c.slice(1).map((x) => x.v)) : null,
    notes: inspector.crossingNotes(rows, threshold, increaseThreshold),
  };
}

// Selects each pixel the way a user does - a map click, or typing the coordinate and
// pressing Submit Pixel - and records what the inspector charted.
async function selectPixels(handle, created, map, pixels, how, thresholds) {
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
    await waitFor(() => created.charts.length >= before + 3 || /No clear|failed/.test(labelText(created)),
                  'the inspector at ' + p.label);
    const [timeline, fit, prob] = created.charts.slice(before);
    const run = handle.state.run;
    const tables = await evaluate(inspector.historyQuery(run.result, run.config, p.lon, p.lat));
    const rows = inspector.historyRows(tables, run.config);
    const exp = await evaluate(inspector.expectationQuery(bulcd, run.result, run.config, p.lon, p.lat));
    const expRows = inspector.expectationRows(exp, run.config);
    out[p.label] = pixelRecord(p, rows, fit && fit.table, prob && prob.table, thresholds.decrease,
                               thresholds.increase);
    out[p.label].expectation = {
      rows: expRows, fit: exp.fit, regressors: exp.regressors,
      summary: inspector.expectationSummary(exp, expRows, run.config),
      timeline_matches: !!timeline &&
        tablesClose(timeline.table, inspector.timelineTable(expRows, rows, run.config.reduction.band)),
      timeline_rows: timeline ? timeline.table.rows.length : 0,
    };
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

  // 2. The GUI: asset area, default settings, Run Early Detection.
  const handle = app.main(bulcd, appConfig, outputs, inspector, aoi, controlsUi);
  const map = created.maps[0];
  data.gui_labels = created.labels.map((l) => l.state.value).filter(Boolean);
  data.gui_buttons = created.buttons.map((b) => b.state.value);
  data.gui_area_sources = handle.source.items().items;
  handle.source.setValue(handle.AREA_SOURCES.asset);
  handle.assetBox.setValue(TESTSITE);
  // 2. Default settings (config.js APP_DEFAULTS), through the widgets and the Run button.
  const controls = handle.controls.read();
  data.notebook.controls = controls;
  handle.runButton.state.handlers.click();
  await waitFor(() => handle.state.run, 'the default run');
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
  data.notebook.final_box = await boxRegion(run.result.final_probabilities.select(['decrease', 'increase']));
  data.notebook.timing_box = await boxRegion(run.timing.select(TIMING_BOX_BANDS));
  data.notebook.episodes_box = await boxRegion(run.episodes);
  data.notebook.pixels = await selectPixels(handle, created, map, [REFERENCE_PIXELS[0], REFERENCE_PIXELS[2]],
                                            { [REFERENCE_PIXELS[2].label]: 'submit' }, run.thresholds);

  // 2b. Detection timing raw (Advanced settings), Run.
  handle.controls.timingConfirmed.setValue(false);
  const raw = await runGui(handle, 'the raw-timing run');
  data.raw = { label: raw.label, controls: handle.controls.read(),
               timing_box: await boxRegion(raw.timing.select(TIMING_BOX_BANDS)),
               episodes_box: await boxRegion(raw.episodes) };
  handle.controls.timingConfirmed.setValue(true);

  // 3. Non-default settings: configs only.
  data.variant.config = bulcd.withDefaults(appConfig.buildConfig(VARIANT, area.aoi));
  data.variant.timing_years = appConfig.timingYears(VARIANT);
  data.variant.timing_configs = data.variant.timing_years.map((y) =>
    bulcd.withDefaults(appConfig.buildConfig(appConfig.withMonitoringYear(VARIANT, y), area.aoi)));

  // 4. Expectation fit orders 2 and 3: chosen in Advanced settings, then Run.
  data.orders = {};
  for (const order of FIT_ORDERS_RUN) {
    handle.controls.fitOrder.setValue(String(order));
    const c = handle.controls.read();
    const r = await runGui(handle, 'the fit order ' + order + ' run');
    const o = data.orders[order] = { controls: c, label: r.label, config: r.config,
                                     description: appConfig.describeControls(c) };
    o.timing_configs = appConfig.timingYears(c).map((y) =>
      bulcd.withDefaults(appConfig.buildConfig(appConfig.withMonitoringYear(c, y), area.aoi)));
    o.outcome_box = await boxRegion(r.outcome.select('outcome'));
    o.timing_box = await boxRegion(r.timing.select(TIMING_BOX_BANDS));
    o.episodes_box = await boxRegion(r.episodes);
    o.pixels = await selectPixels(handle, created, map, [REFERENCE_PIXELS[0]], {}, r.thresholds);
  }
  handle.controls.fitOrder.setValue('1');

  // 5. Pine Mountain pixel: the detection timing image and the inspector rows there.
  const ring = [[PM.lon - PM.half, PM.lat - PM.half], [PM.lon + PM.half, PM.lat - PM.half],
                [PM.lon + PM.half, PM.lat + PM.half], [PM.lon - PM.half, PM.lat + PM.half],
                [PM.lon - PM.half, PM.lat - PM.half]];
  const pmConfig = bulcd.withDefaults(appConfig.buildConfig(PM_CONTROLS, { aoi_coordinates: ring }));
  const pmCrs = inspector.utmCrsFor(PM.lon, PM.lat);
  const pmImage = outputs.detectionTimingImage(bulcd, pmConfig, PM_CONTROLS.decrease_threshold,
                                               PM_CONTROLS.increase_threshold).addBands(
    outputs.combineEpisodeMetrics({ 2024: outputs.detectionEpisodeImage(bulcd, pmConfig, PM_CONTROLS.decrease_threshold,
                                                                        PM_CONTROLS.increase_threshold) }));
  const pmResult = bulcd.runBulcd(pmConfig);
  const pmRows = inspector.historyRows(
    await evaluate(inspector.historyQuery(pmResult, pmConfig, PM.lon, PM.lat)), pmConfig);
  data.pine_mountain = {
    config: pmConfig,
    image: await evaluate(pmImage.reduceRegion({ reducer: ee.Reducer.first(), geometry: ee.Geometry.Point([PM.lon, PM.lat]),
                                                 scale: 30, crs: pmCrs })),
    combined: await evaluate(outputs.decreaseEpisodeBands(pmResult.probability_stack, PM_CONTROLS.decrease_threshold)
      .reduceRegion({
      reducer: ee.Reducer.first(), geometry: ee.Geometry.Point([PM.lon, PM.lat]), scale: 30, crs: pmCrs })),
    episodes: inspector.detectionEpisodes(pmRows, PM_CONTROLS.decrease_threshold),
    notes: inspector.episodeNotes(pmRows, PM_CONTROLS.decrease_threshold),
  };

  fs.writeFileSync(out, JSON.stringify(data));
}

main(process.argv[2]).catch((e) => { console.error(e); process.exit(1); });
