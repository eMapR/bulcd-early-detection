// Check of the Export section, through app.js's own widgets (stub `ui`, live
// Earth Engine, a recording stand-in for `Export`; no tasks are started): before
// a run it asks for one; after a run on the test asset with default settings it
// lists every dataset, and Export creates one task per checked dataset with
// valid names, the area's UTM grid and the nodata value, for Google Drive and for
// a Cloud Storage bucket (bad bucket names create none); each exported image has
// the listed bands and a single band type. With #exports=off the section is left
// out of the panel and a run prepares no exports.
// usage: node export_check.js     (~2 min)
const assert = require('assert');
const path = require('path');

const BULCD_GEE = process.env.BULCD_GEE || path.join(__dirname, '..', '..', '..', 'BULC-D_rebuild', 'gee');
const { init, evaluate } = require(path.join(BULCD_GEE, 'tests', 'ee_node'));
const bulcd = require(path.join(BULCD_GEE, 'bulcd.js'));
const appConfig = require('../config.js');
const outputs = require('../outputs.js');
const inspector = require('../inspector.js');
const aoi = require('../aoi.js');
const controlsUi = require('../controls.js');
const app = require('../app.js');
const { makeUi } = require('./ui_stub');
const { TESTSITE } = require('./reference_case');

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

async function main() {
  await init();
  const { ui } = makeUi();
  global.ui = ui;
  const handle = app.main(bulcd, appConfig, outputs, inspector, aoi, controlsUi);
  const status = () => handle.exportStatus.state.value;
  const click = (button) => button.state.handlers.click();

  // Before a run.
  click(handle.exportButton);
  assert.match(status(), /Run the analysis first/);

  // Run on the test asset with default settings (first-detected season on).
  handle.source.setValue(handle.AREA_SOURCES.asset);
  handle.assetBox.setValue(TESTSITE);
  click(handle.runButton);
  await waitFor(() => handle.state.exports, 'the run');
  const items = handle.state.exports.items;
  const keys = items.map((i) => (i.settings ? 'settings' : i.dataset.key));
  const y = handle.controls.read().monitoring_year;
  assert.deepStrictEqual(keys, ['condition', 'first_detected', 'last_detection_episodes', 'true_color_' + (y - 2),
                                'true_color_' + (y - 1), 'true_color_' + y, 'nbr', 'settings']);
  assert.strictEqual(handle.exportChoices.state.children.length, items.length);

  // Outside the Code Editor there is no Export.
  click(handle.exportButton);
  assert.match(status(), /need the Code Editor/);

  // Export with one dataset unchecked.
  const tasks = [];
  const record = (kind, method) => (p) => tasks.push(Object.assign({ kind, method }, p));
  global.Export = {
    image: { toDrive: record('image', 'toDrive'), toCloudStorage: record('image', 'toCloudStorage') },
    table: { toDrive: record('table', 'toDrive'), toCloudStorage: record('table', 'toCloudStorage') },
  };
  items[keys.indexOf('true_color_' + (y - 2))].box.setValue(false);
  handle.folderBox.setValue('  my_folder ');
  click(handle.exportButton);
  assert.match(status(), /Created 7 export tasks/, status());
  assert.strictEqual(tasks.length, 7);
  const names = tasks.map((t) => t.description);
  assert.strictEqual(new Set(names).size, names.length, 'unique task names');
  tasks.forEach((t) => {
    assert.match(t.description, /^[A-Za-z0-9_-]{1,100}$/);
    assert.strictEqual(t.fileNamePrefix, t.description);
    assert.strictEqual(t.folder, 'my_folder');
    assert.strictEqual(t.method, 'toDrive');
    assert.strictEqual(t.bucket, undefined);
  });
  const images = tasks.filter((t) => t.kind === 'image');
  images.forEach((t) => {
    assert.strictEqual(t.crs, 'EPSG:32610');
    assert.strictEqual(t.formatOptions.noData, outputs.EXPORT_NODATA);
    assert.strictEqual(t.fileFormat, 'GeoTIFF');
  });
  assert(!names.some((n) => n.endsWith('true_color_' + (y - 2))), 'unchecked dataset not exported');

  // The same datasets to a Cloud Storage bucket. Bad names create no tasks.
  handle.destination.setValue(handle.EXPORT_DESTINATIONS.bucket);
  for (const bad of ['', 'gs://my-bucket', 'my-bucket/folder', 'My-Bucket', '-my-bucket']) {
    handle.bucketBox.setValue(bad);
    click(handle.exportButton);
    assert.match(status(), /bucket name/i, bad);
    assert.strictEqual(tasks.length, 7, 'no tasks for bucket ' + JSON.stringify(bad));
  }
  handle.bucketBox.setValue(' my-bucket_1.test ');
  handle.pathBox.setValue(' /runs/2026/ ');
  click(handle.exportButton);
  assert.match(status(), /Created 7 export tasks for gs:\/\/my-bucket_1\.test\/runs\/2026\//, status());
  const bucketTasks = tasks.slice(7);
  assert.strictEqual(bucketTasks.length, 7);
  bucketTasks.forEach((t, i) => {
    assert.strictEqual(t.method, 'toCloudStorage');
    assert.strictEqual(t.bucket, 'my-bucket_1.test');
    assert.strictEqual(t.folder, undefined);
    assert.strictEqual(t.description, names[i]);
    assert.strictEqual(t.fileNamePrefix, 'runs/2026/' + names[i]);
    assert.strictEqual(t.fileFormat, tasks[i].fileFormat);
    assert.deepStrictEqual(t.formatOptions, tasks[i].formatOptions);
    assert.strictEqual(t.crs, tasks[i].crs);
    assert.strictEqual(t.scale, tasks[i].scale);
  });
  handle.pathBox.setValue('');
  click(handle.exportButton);
  assert.strictEqual(tasks[tasks.length - 1].fileNamePrefix, names[names.length - 1], 'no path: name only');

  // Each image: the listed bands, one band type.
  const exported = items.filter((i) => !i.settings && i.box.getValue());
  for (const item of exported) {
    const info = await evaluate(ee.Dictionary({ names: item.dataset.image.bandNames(),
                                                types: item.dataset.image.bandTypes() }));
    assert.deepStrictEqual(info.names, item.dataset.bands, item.dataset.key);
    const types = new Set(Object.values(info.types).map((t) => JSON.stringify(t)));
    assert.strictEqual(types.size, 1, item.dataset.key + ' band types ' + [...types].join(' '));
    console.log(item.dataset.key + ': ' + info.names.join(', ') + ' (' + [...types][0] + ')');
  }
  const settings = await evaluate(tasks.find((t) => t.kind === 'table').collection.first().toDictionary());
  assert(JSON.parse(settings.config_json).study_area, 'settings CSV carries the configuration');

  // The section is in the panel by default, and left out with #exports=off.
  const panelText = (h) => h.panel.state.children.map((w) => w.state.value).filter((v) => typeof v === 'string');
  assert(panelText(handle).includes('4. Export'));
  assert(panelText(handle).includes('5. Pixel inspector'));
  const off = makeUi();
  off.ui.url.values.exports = 'off';
  global.ui = off.ui;
  const hidden = app.main(bulcd, appConfig, outputs, inspector, aoi, controlsUi);
  assert(!panelText(hidden).some((v) => /export/i.test(v)), panelText(hidden).join(' | '));
  assert(panelText(hidden).includes('4. Pixel inspector'));
  assert(!hidden.panel.state.children.includes(hidden.exportButton));
  hidden.source.setValue(hidden.AREA_SOURCES.asset);
  hidden.assetBox.setValue(TESTSITE);
  click(hidden.runButton);
  await waitFor(() => hidden.state.run, 'the run with exports off');
  assert(!hidden.state.exports, 'no exports prepared');

  console.log('export_check: OK (' + names.join(', ') + ')');
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
