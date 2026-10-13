// Map-layer description size check (Earth Engine login; no pixel computation).
//
// The Code Editor writes out a map layer's description with every repeated
// sub-expression expanded, and fails with "Layer error: Description length
// exceeds maximum" when that gets too long. Found 2026-10-13: the first
// episode layers repeated the probability history, and the first-detected
// season layer had grown because its seasons carried them
// (docs/findings.md, 2026-10-13). Drives app.js (stub `ui`, testsite asset,
// Run) for the default settings, raw detection timing and fit order 3, and
// checks every BULC-D layer it adds:
//   - First detected season: the same description as before the episode
//     layers (combineSeasonTiming over plain detectionTimingImage seasons).
//   - Last detection and Detection episodes: expanded description no longer
//     than the First detected season layer's, which renders in the Code Editor.
//   - Earth Engine accepts each layer's map request (getMap).
// usage: node layer_size_check.js   (~1 min)
const assert = require('assert');
const path = require('path');

const BULCD_GEE = process.env.BULCD_GEE || path.join(__dirname, '..', '..', '..', 'BULC-D_rebuild', 'gee');
const { ee, init } = require(path.join(BULCD_GEE, 'tests', 'ee_node'));
const { makeUi } = require('./ui_stub');
const { TESTSITE } = require('./reference_case');

// Length of the fully expanded JSON description (no shared references),
// computed from the compound encoding with memoization (the expanded string
// itself can exceed JavaScript's maximum string length).
function expandedLength(obj) {
  const enc = ee.Serializer.encode(obj, true);
  const scope = {};
  (enc.scope || []).forEach(([k, v]) => { scope[k] = v; });
  const memo = {};
  function size(node) {
    if (node && typeof node === 'object' && node.type === 'ValueRef') {
      if (memo[node.value] === undefined) memo[node.value] = size(scope[node.value]);
      return memo[node.value];
    }
    let extra = 0;
    const json = JSON.stringify(node, (key, v) => {
      if (v && typeof v === 'object' && v.type === 'ValueRef') { extra += size(v) - 3; return '#'; }
      return v;
    });
    return json.length + extra;
  }
  return size(enc.type === 'CompoundValue' ? enc.value : enc);
}

function waitFor(predicate, what, ms = 300000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    (function poll() {
      if (predicate()) return resolve();
      if (Date.now() - start > ms) return reject(new Error('timed out waiting for ' + what));
      setTimeout(poll, 250);
    })();
  });
}

const getMap = (image, vis) => new Promise((resolve) => image.getMap(vis, (m, err) => resolve(err || null)));
const M = (n) => (n / 1e6).toFixed(1) + 'M';

async function main() {
  await init();
  const bulcd = require(path.join(BULCD_GEE, 'bulcd.js'));
  const appConfig = require('../config.js');
  const outputs = require('../outputs.js');
  const { ui, created } = makeUi();
  global.ui = ui;
  const handle = require('../app.js').main(bulcd, appConfig, outputs, require('../inspector.js'), require('../aoi.js'),
                                           require('../controls.js'));
  const map = created.maps[0];
  handle.source.setValue(handle.AREA_SOURCES.asset);
  handle.assetBox.setValue(TESTSITE);

  const cases = [['default', () => {}],
                 ['raw detection timing', () => handle.controls.timingConfirmed.setValue(false)],
                 ['fit order 3', () => { handle.controls.timingConfirmed.setValue(true); handle.controls.fitOrder.setValue('3'); }]];
  for (const [name, set] of cases) {
    set();
    const prev = handle.state.run;
    handle.runButton.state.handlers.click();
    await waitFor(() => handle.state.run && handle.state.run !== prev, 'the ' + name + ' run');
    const c = handle.controls.read();
    const layer = (n) => map.state.layers.items.find((l) => l.name === n);
    const first = layer('First detected season (decrease)');
    const last = layer('Last detection (decrease)');
    const episodes = layer('Detection episodes (decrease)');
    const condition = layer('Condition ' + c.monitoring_year);
    assert(first && last && episodes && condition, name + ': missing a BULC-D layer');

    // The First detected season layer, built as before the episode layers.
    const seasons = {};
    appConfig.timingYears(c).forEach((y) => {
      seasons[y] = outputs.detectionTimingImage(bulcd, appConfig.buildConfig(appConfig.withMonitoringYear(c, y),
                                                handle.state.area.aoi), c.decrease_threshold, c.increase_threshold);
    });
    const before = outputs.combineSeasonTiming(seasons, c.timing_confirmed).clip(handle.state.area.geometry)
      .select('first_decrease_year');
    assert.strictEqual(ee.Serializer.toJSON(first.image), ee.Serializer.toJSON(before),
                       name + ': the First detected season layer changed');

    const sizes = {};
    for (const l of [condition, first, last, episodes]) {
      sizes[l.name] = expandedLength(l.image.visualize(l.vis));
      const err = await getMap(l.image, l.vis);
      assert.strictEqual(err, null, name + ': ' + l.name + ' map request failed: ' + err);
    }
    console.log(name + ': ' + Object.entries(sizes).map(([k, v]) => k + ' ' + M(v)).join(', ') + '; all map requests ok');
    for (const l of [last, episodes]) {
      assert(sizes[l.name] <= sizes[first.name],
             name + ': ' + l.name + ' description ' + M(sizes[l.name]) + ' > First detected season ' + M(sizes[first.name]));
    }
  }
  console.log('LAYER SIZE CHECK PASSED');
}

main().catch((e) => { console.error(e); process.exit(1); });
