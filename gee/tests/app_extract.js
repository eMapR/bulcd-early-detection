// JS side of the app parity test: run app.js main() on the fixed reference case
// (with a stub `ui`), drive the inspector at each reference pixel exactly as a
// map click would, and record the rows and chart tables it produced, plus the
// classification over a small box. usage: node app_extract.js <out.json>
const fs = require('fs');
const path = require('path');

const BULCD_GEE = process.env.BULCD_GEE || path.join(__dirname, '..', '..', '..', 'BULC-D_rebuild', 'gee');
const { ee, init, evaluate } = require(path.join(BULCD_GEE, 'tests', 'ee_node'));
const bulcd = require(path.join(BULCD_GEE, 'bulcd.js'));
const appConfig = require('../config.js');
const outputs = require('../outputs.js');
const inspector = require('../inspector.js');
const app = require('../app.js');
const { makeUi } = require('./ui_stub');

// Same box as BULC-D_rebuild gee/tests/cases.py BOX.
const BOX = [-123.5725, 44.8300, -123.5400, 44.8500];

function waitFor(predicate, ms = 600000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    (function poll() {
      if (predicate()) return resolve();
      if (Date.now() - start > ms) return reject(new Error('timed out waiting for the inspector'));
      setTimeout(poll, 250);
    })();
  });
}

async function main(out) {
  await init();
  const { ui, created } = makeUi();
  global.ui = ui;
  const c = appConfig.REFERENCE_CASE;
  const handle = app.main(bulcd, appConfig, outputs, inspector);
  const config = bulcd.withDefaults(c.bulcd);
  const map = created.maps[0];
  const data = { config, outcome_box: null, pixels: {}, ui: { map_layers: map.state.layers.map((l) => l.name) } };

  for (const p of c.reference_pixels) {
    const before = created.charts.length;
    map.state.handlers.click({ lon: p.lon, lat: p.lat });  // what a map click does
    await waitFor(() => created.charts.length >= before + 2 ||
                        /No clear|failed/.test(created.labels.map((l) => l.state.value).join('\n')));
    const [fit, prob] = created.charts.slice(before);
    // Re-run the pure pieces for the row-level comparison (same request the app made).
    const tables = await evaluate(inspector.historyQuery(handle.result, config, p.lon, p.lat));
    data.pixels[p.label] = {
      lon: p.lon, lat: p.lat,
      rows: inspector.historyRows(tables, config),
      fit_table_rows: fit ? fit.table.rows.length : 0,
      prob_table: prob ? prob.table.rows.map((r) => r.c.slice(1).map((x) => x.v)) : null,
      notes: inspector.crossingNotes(inspector.historyRows(tables, config), c.decision_threshold),
    };
  }
  const box = ee.Geometry.Rectangle(BOX);
  data.outcome_box = await evaluate(ee.ImageCollection([handle.outcome.set('system:time_start', 0)])
    .getRegion(box, 30, 'EPSG:32610'));
  fs.writeFileSync(out, JSON.stringify(data));
}

main(process.argv[2]).catch((e) => { console.error(e); process.exit(1); });
