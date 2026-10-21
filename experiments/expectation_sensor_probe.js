// Expectation-sensor performance probe (docs/findings.md, 2026-10-19).
//
// Drives the GEE app (gee/app.js, stub `ui`, testsite asset, Run) with the
// default settings except the expectation: years 2022-2023, 2021-2023, 2020-2023,
// 2018-2023 and 2016-2023 (2, 3, 4, 6, 8 years), sensors L8 (today's default,
// the control), L8+S2 and L8+L9+S2. The config module passed to main() sets the
// expectation years and sensors (the app's expectation-sensor control);
// nothing else changes. For each run it records:
//   - each BULC-D layer's fully expanded description size (the Code Editor's
//     "Description length exceeds maximum" limit; gee/tests/layer_size_check.js);
//   - the map tiles at zoom 13 over the testsite for the condition,
//     first-detected-season, last-detection and detection-episode layers,
//     fetched in parallel per layer as a browser would: time and any error;
//   - the inspector query at reference pixel 1 (the app's own
//     historyQuery + expectationQuery): time and any error.
// Also counts raw L8/L9/S2 scenes over the testsite per year in the season window.
//
// usage: node experiments/expectation_sensor_probe.js [out.json]   (hours; run in the background)
// PROBE_SENSORS=L8+L9+S2 PROBE_YEARS=4,6,8 limit the runs (e.g. to resume an interrupted probe).
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const BULCD_GEE = process.env.BULCD_GEE || path.join(ROOT, '..', 'BULC-D_rebuild', 'gee');
const { ee, init, evaluate } = require(path.join(BULCD_GEE, 'tests', 'ee_node'));
const { makeUi } = require(path.join(ROOT, 'gee', 'tests', 'ui_stub'));
const { TESTSITE, REFERENCE_PIXELS } = require(path.join(ROOT, 'gee', 'tests', 'reference_case'));

const OUT = process.argv[2] || path.join(ROOT, 'experiments', 'output', 'expectation_sensor_probe', 'probe.json');
const SENSOR_SETS = (process.env.PROBE_SENSORS ? process.env.PROBE_SENSORS.split(',').map((s) => s.split('+'))
                     : [['L8'], ['L8', 'S2'], ['L8', 'L9', 'S2']]);
const YEARS = (process.env.PROBE_YEARS ? process.env.PROBE_YEARS.split(',').map(Number)
               : [2, 4, 6, 8]);  // expectation lengths, all ending 2023
const LAST_YEAR = 2023;
const ZOOM = 13;
const TILE_TIMEOUT_MS = 15 * 60 * 1000;
const LAYERS = ['Condition 2026', 'First detected season (decrease)', 'Last detection (decrease)',
                'Detection episodes (decrease)'];

// Same as gee/tests/layer_size_check.js expandedLength().
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

const getMap = (image, vis) => new Promise((resolve) => image.getMap(vis, (m, err) => resolve({ m, err })));

function tileXY(lon, lat, z) {
  const n = 2 ** z, r = lat * Math.PI / 180;
  return [Math.floor((lon + 180) / 360 * n), Math.floor((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * n)];
}

async function fetchTile(url) {
  const t0 = Date.now();
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TILE_TIMEOUT_MS);
  try {
    const res = await fetch(url, { signal: ctl.signal });
    const body = res.ok ? null : (await res.text()).slice(0, 300);
    if (res.ok) await res.arrayBuffer();
    return { s: (Date.now() - t0) / 1000, status: res.status, error: body };
  } catch (e) {
    return { s: (Date.now() - t0) / 1000, status: null, error: String(e.message || e) };
  } finally {
    clearTimeout(timer);
  }
}

// All zoom-13 tiles over the testsite, fetched in parallel.
async function layerTiles(layer, tiles) {
  const t0 = Date.now();
  const { m, err } = await getMap(layer.image, layer.vis);
  if (err) return { s: (Date.now() - t0) / 1000, ok: false, error: 'getMap: ' + err, tiles: [] };
  const results = await Promise.all(tiles.map(([x, y]) => fetchTile(ee.data.getTileUrl(m, x, y, ZOOM))));
  const failed = results.filter((r) => r.status !== 200);
  return { s: (Date.now() - t0) / 1000, ok: failed.length === 0, error: failed.length ? failed[0].error : null,
           max_tile_s: Math.max(...results.map((r) => r.s)), tiles: results };
}

async function availability(geom) {
  const counts = {};
  const ids = { L8: 'LANDSAT/LC08/C02/T1_L2', L9: 'LANDSAT/LC09/C02/T1_L2', S2: 'COPERNICUS/S2_SR_HARMONIZED',
                S2_cloud_score_plus: 'GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED' };
  for (const [k, id] of Object.entries(ids)) {
    const d = {};
    for (let y = 2013; y <= 2026; y++) {
      d[y] = ee.ImageCollection(id).filterBounds(geom).filterDate(y + '-06-01', y + '-10-01').size();
    }
    counts[k] = await evaluate(ee.Dictionary(d));
  }
  return counts;
}

async function main() {
  await init();
  const bulcd = require(path.join(BULCD_GEE, 'bulcd.js'));
  const appConfig = require(path.join(ROOT, 'gee', 'config.js'));
  let expectationSensors = null, expectationFirst = null;
  // The app's config module with only the expectation (first year, sensors) replaced. The same
  // config the app's own expectation-sensor control builds (every sensor gets the L8 entry's
  // years, window and cloud cover).
  const probeConfig = Object.assign({}, appConfig, {
    buildConfig(c, aoi) {
      const boxes = {};
      appConfig.SENSORS.forEach((s) => { boxes[s] = expectationSensors.includes(s); });
      return appConfig.buildConfig(Object.assign({}, c, { expectation_first: expectationFirst,
                                                          expectation_sensors: boxes }), aoi);
    },
  });
  const { ui, created } = makeUi();
  global.ui = ui;
  const handle = require(path.join(ROOT, 'gee', 'app.js')).main(
    bulcd, probeConfig, require(path.join(ROOT, 'gee', 'outputs.js')), require(path.join(ROOT, 'gee', 'inspector.js')),
    require(path.join(ROOT, 'gee', 'aoi.js')), require(path.join(ROOT, 'gee', 'controls.js')));
  const map = created.maps[0];
  const inspector = require(path.join(ROOT, 'gee', 'inspector.js'));
  handle.source.setValue(handle.AREA_SOURCES.asset);
  handle.assetBox.setValue(TESTSITE);

  const geom = ee.FeatureCollection(TESTSITE).geometry();
  const bounds = (await evaluate(geom.bounds())).coordinates[0];
  const lons = bounds.map((p) => p[0]), lats = bounds.map((p) => p[1]);
  const [x0, y0] = tileXY(Math.min(...lons), Math.max(...lats), ZOOM);
  const [x1, y1] = tileXY(Math.max(...lons), Math.min(...lats), ZOOM);
  const tiles = [];
  for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) tiles.push([x, y]);

  const out = { started: new Date().toISOString(), area: TESTSITE, zoom: ZOOM, tiles: tiles.length,
                pixel: REFERENCE_PIXELS[0], availability: await availability(geom), runs: [] };
  console.log('availability', JSON.stringify(out.availability));
  fs.mkdirSync(path.dirname(OUT), { recursive: true });

  for (const sensors of SENSOR_SETS) {
    for (const n of YEARS) {
      expectationSensors = sensors;
      expectationFirst = LAST_YEAR - n + 1;
      const name = sensors.join('+') + ' x ' + n + ' yr';
      const prev = handle.state.run;
      handle.runButton.state.handlers.click();
      await waitFor(() => handle.state.run && handle.state.run !== prev, 'the ' + name + ' run');
      const run = handle.state.run;
      const exp = run.config.evidence.expectation.sensors[sensors[0]];
      const rec = { name, sensors, years: n, expectation: [exp.first_year, exp.last_year - 1],
                    expectation_sensors: Object.keys(run.config.evidence.expectation.sensors), layers: {} };
      for (const lname of LAYERS) {
        const l = map.state.layers.items.find((x) => x.name === lname);
        rec.layers[lname] = { description_chars: expandedLength(l.image.visualize(l.vis)) };
      }
      const t0 = Date.now();
      try {
        const p = REFERENCE_PIXELS[0];
        await evaluate(ee.Dictionary({ history: inspector.historyQuery(run.result, run.config, p.lon, p.lat),
                                       expectation: inspector.expectationQuery(bulcd, run.result, run.config, p.lon,
                                                                               p.lat) }));
        rec.inspector = { s: (Date.now() - t0) / 1000, ok: true, error: null };
      } catch (e) {
        rec.inspector = { s: (Date.now() - t0) / 1000, ok: false, error: String(e.message || e).slice(0, 300) };
      }
      console.log(name + ' inspector', JSON.stringify(rec.inspector));
      for (const lname of LAYERS) {
        const l = map.state.layers.items.find((x) => x.name === lname);
        Object.assign(rec.layers[lname], await layerTiles(l, tiles));
        const r = rec.layers[lname];
        console.log(name + ' ' + lname + ': ' + (r.description_chars / 1e6).toFixed(1) + 'M chars, ' +
                    r.s.toFixed(0) + ' s, ' + (r.ok ? 'ok' : 'FAILED ' + r.error));
      }
      out.runs.push(rec);
      fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
    }
  }
  out.finished = new Date().toISOString();
  fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
  console.log('PROBE DONE ' + OUT);
}

main().catch((e) => { console.error(e); process.exit(1); });
