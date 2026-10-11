// Regression test: the inspected coordinate survives a settings change and rerun.
//
// Sequence, through app.js's own widgets and handlers (stub `ui`, live Earth Engine):
//   map click at A -> inspect -> change sensitivity -> Run Early Detection again
//   -> Submit Pixel
// Asserts the coordinate boxes, the coordinate every inspector query receives
// and the marker point all stay exactly A; that the rerun leaves the
// map-click handler, drawing-tool state and the single marker layer as they
// were; and that each inspection's charts equal a fresh, independent
// computation at A under that run's settings (so a chart change after the
// rerun comes from the settings, not from a different location).
// usage: node inspector_state_check.js     (~5 min)
const assert = require('assert');
const path = require('path');

const BULCD_GEE = process.env.BULCD_GEE || path.join(__dirname, '..', '..', '..', 'BULC-D_rebuild', 'gee');
const { init, evaluate } = require(path.join(BULCD_GEE, 'tests', 'ee_node'));
const bulcd = require(path.join(BULCD_GEE, 'bulcd.js'));
const appConfig = require('../config.js');
const outputs = require('../outputs.js');
const realInspector = require('../inspector.js');
const aoi = require('../aoi.js');
const controlsUi = require('../controls.js');
const app = require('../app.js');
const { makeUi } = require('./ui_stub');
const { tablesClose } = require('./table_close');
const { TESTSITE } = require('./reference_case');

// A full-precision coordinate, as a map click delivers it (near reference pixel 1).
const A = { lon: -123.56922417382812, lat: 44.84283591053214 };

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

async function main() {
  await init();
  const { ui, created } = makeUi();
  global.ui = ui;

  // The real inspector, recording the coordinate each query is built for.
  const queried = [];
  const inspector = Object.assign({}, realInspector, {
    historyQuery(result, config, lon, lat) {
      queried.push({ query: 'history', lon, lat });
      return realInspector.historyQuery(result, config, lon, lat);
    },
    expectationQuery(b, result, config, lon, lat) {
      queried.push({ query: 'expectation', lon, lat });
      return realInspector.expectationQuery(b, result, config, lon, lat);
    },
  });

  const handle = app.main(bulcd, appConfig, outputs, inspector, aoi, controlsUi);
  const map = created.maps[0];
  const tools = map.drawingTools();
  const sensitivity = created.sliders[0];
  handle.source.setValue(handle.AREA_SOURCES.asset);
  handle.assetBox.setValue(TESTSITE);

  const markers = () => map.state.layers.items.filter((l) => l.name === 'Selected pixel');
  const markerAt = () => {
    const m = markers();
    assert.strictEqual(m.length, 1, 'exactly one marker layer');
    return m[0].image.toGeoJSON().coordinates;
  };
  const boxes = () => [handle.lonBox.getValue(), handle.latBox.getValue()];
  const expectedBoxes = [String(A.lon), String(A.lat)];

  async function run(what) {
    const before = handle.state.run;
    handle.runButton.state.handlers.click();
    await waitFor(() => handle.state.run && handle.state.run !== before, what);
    return handle.state.run;
  }

  // Waits for an inspection's three charts; checks every query used A; checks
  // the charts equal a fresh computation at A under the given controls.
  async function inspected(how, controls, before) {
    const firstQuery = queried.length;
    if (how === 'click') map.state.handlers.click({ lon: A.lon, lat: A.lat });
    else handle.submit.state.handlers.click();
    await waitFor(() => created.charts.length >= before + 3, 'the inspector after ' + how);
    const mine = queried.slice(firstQuery);
    assert.deepStrictEqual(mine.map((q) => q.query), ['history', 'expectation'], how + ': one query of each kind');
    mine.forEach((q) => assert.deepStrictEqual([q.lon, q.lat], [A.lon, A.lat], how + ': ' + q.query + ' query at A'));
    assert.deepStrictEqual(markerAt(), [A.lon, A.lat], how + ': marker at A');
    assert.deepStrictEqual(boxes(), expectedBoxes, how + ': coordinate boxes hold A');

    const [timeline, fit, prob] = created.charts.slice(before, before + 3).map((c) => c.table);
    const config = bulcd.withDefaults(appConfig.buildConfig(controls, handle.state.area.aoi));
    const result = bulcd.runBulcd(config);
    const rows = realInspector.historyRows(await evaluate(realInspector.historyQuery(result, config, A.lon, A.lat)),
                                           config);
    const exp = await evaluate(realInspector.expectationQuery(bulcd, result, config, A.lon, A.lat));
    const expRows = realInspector.expectationRows(exp, config);
    const same = tablesClose;
    assert(same(prob, realInspector.probabilityTable(rows, controls.decision_threshold)),
           how + ': probability chart = fresh computation at A');
    assert(same(fit, realInspector.targetFitTable(rows, config.reduction.band)), how + ': fit chart = fresh at A');
    assert(same(timeline, realInspector.timelineTable(expRows, rows, config.reduction.band)),
           how + ': timeline chart = fresh at A');
    return rows;
  }

  // 1. Run with the defaults; click A.
  await run('the first run');
  const controls1 = handle.controls.read();
  const rows1 = await inspected('click', controls1, created.charts.length);
  console.log('map click at A: boxes, queries, marker and charts all at A - ok');

  const clickHandler = map.state.handlers.click, submitHandler = handle.submit.state.handlers.click;
  const viewsBefore = map.state.views.length;

  // 2. Change sensitivity; run again.
  sensitivity.setValue(2.0);
  const controls2 = handle.controls.read();
  assert.strictEqual(controls2.sensitivity, 2.0);
  await run('the second run');
  assert.deepStrictEqual(boxes(), expectedBoxes, 'rerun leaves the coordinate boxes at A');
  assert.deepStrictEqual(markerAt(), [A.lon, A.lat], 'rerun leaves the marker at A');
  assert.strictEqual(map.state.handlers.click, clickHandler, 'rerun keeps the same map-click handler');
  assert.strictEqual(handle.submit.state.handlers.click, submitHandler, 'rerun keeps the same Submit handler');
  assert.strictEqual(tools.getShape(), null, 'rerun leaves the drawing tools out of drawing mode');
  const views = map.state.views.slice(viewsBefore).map((v) => v[0]);
  console.log('rerun: boxes, marker, click/Submit handlers and drawing tools unchanged - ok; map view changes: ' +
              (views.length ? views.join(', ') : 'none'));

  // 3. Submit Pixel.
  const rows2 = await inspected('submit', controls2, created.charts.length);
  console.log('Submit Pixel after the rerun: boxes, queries, marker and charts all at A - ok');
  const differ = (k) => rows1.filter((r, i) => rows2[i] && r[k] !== rows2[i][k]).length;
  const clamped = rows2.filter((r) => r.zscore !== null && Math.abs(r.zscore) === 10).length;
  console.log('same pixel, same ' + rows1.length + ' dates; sensitivity ' + controls1.sensitivity + ' -> ' +
              controls2.sensitivity + ' changed the z-score on ' + differ('zscore') + ' and P(decrease) on ' +
              differ('decrease') + ' bins (' + clamped + ' observations at the +-10 z-score clamp, where ' +
              'sensitivity has no effect)');
  console.log('INSPECTOR STATE CHECK PASSED');
}

main().catch((e) => { console.error(e); process.exit(1); });
