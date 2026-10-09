// BULC-D Early Detection - Earth Engine Code Editor app (Milestone 1).
//
// One known case with a fixed, read-only configuration (config.js
// REFERENCE_CASE): the classification map, pixel selection by map click or by
// longitude/latitude entry, and the two-chart pixel inspector. BULC-D itself
// runs in BULC-D_rebuild's gee/bulcd.js, held to JS <-> Python parity; this
// repo only interprets its outputs (outputs.js, inspector.js).
//
// Module paths are placeholders until the deployment location is decided
// (README.md). Plain ES5.

var BULCD_MODULE = 'users/OWNER/BULC-D_rebuild:gee/bulcd';
var APP_MODULE_ROOT = 'users/OWNER/bulcd-early-detection:gee/';

var MARKER_COLOR = '#ffd400';

function caseSummary(c, config) {
  var e = config.evidence, a = config.bulc_advanced_params;
  function years(p) {
    var codes = Object.keys(p.sensors).filter(function (k) { return p.sensors[k].enabled; });
    var s = p.sensors[codes[0]];
    return s.first_year + (s.last_year - 1 > s.first_year ? '-' + (s.last_year - 1) : '') + ', DOY ' +
           s.first_doy + '-' + s.last_doy + ', ' + codes.join('+');
  }
  return [
    'Expectation: ' + years(e.expectation),
    'Target: ' + years(e.target),
    'Index ' + config.reduction.band.toUpperCase() + ', day step ' + e.day_step_size +
      ', Landsat scene cloud < ' + e.target.sensors.L8.cloud_cover_threshold + ' (no S2 scene filter)',
    'Levelers: transition ' + a.dampening_factor + ', posterior ' + a.posterior_leveler + ', initializing ' +
      a.initializing_leveler,
    'Decision threshold ' + c.decision_threshold + '; water masked'
  ];
}

function legendRow(color, label) {
  return ui.Panel([
    ui.Label('', {backgroundColor: color, padding: '7px', margin: '4px 8px 4px 0', border: '1px solid #999'}),
    ui.Label(label, {margin: '4px 0'})
  ], ui.Panel.Layout.flow('horizontal'));
}

function main(bulcd, appConfig, outputs, inspector) {
  var c = appConfig.REFERENCE_CASE;
  var config = bulcd.withDefaults(c.bulcd);
  var threshold = c.decision_threshold;
  var result = bulcd.runBulcd(config);
  var outcome = outputs.outcomeImage(bulcd, result, config, threshold);
  var region = bulcd.resolveStudyArea(config.study_area);

  // ---------------------------------------------------------------- map
  var map = ui.Map();
  map.setOptions('HYBRID');
  map.style().set('cursor', 'crosshair');
  map.setCenter(c.map_center.lon, c.map_center.lat, c.map_center.zoom);
  map.addLayer(outcome, outputs.outcomeVis(), 'Classification (P > ' + threshold + ')');
  map.addLayer(ee.FeatureCollection([ee.Feature(region)]).style({color: '4a4a48', fillColor: '00000000', width: 2}),
               {}, 'Study area');
  var markerLayer = null;

  // ---------------------------------------------------------------- panel
  var panel = ui.Panel({style: {width: '440px', padding: '8px'}});
  panel.add(ui.Label('BULC-D Early Detection', {fontSize: '20px', fontWeight: 'bold', margin: '4px 8px'}));
  panel.add(ui.Label(c.name, {fontWeight: 'bold'}));
  caseSummary(c, config).forEach(function (line) {
    panel.add(ui.Label(line, {fontSize: '12px', color: '#444', margin: '0 8px'}));
  });
  panel.add(ui.Label('Configuration is fixed in this version.', {fontSize: '11px', color: '#777'}));

  [outputs.DECREASE, outputs.UNCHANGED, outputs.INCREASE].forEach(function (k) {
    panel.add(legendRow(outputs.OUTCOME_COLORS[k], outputs.OUTCOME_LABELS[k]));
  });

  panel.add(ui.Label('Pixel inspector', {fontSize: '16px', fontWeight: 'bold', margin: '12px 8px 4px'}));
  panel.add(ui.Label('Click the map, or enter a coordinate (decimal degrees) and press Submit Pixel.',
                     {fontSize: '12px'}));
  var lonBox = ui.Textbox({placeholder: 'Longitude', style: {width: '180px'}});
  var latBox = ui.Textbox({placeholder: 'Latitude', style: {width: '180px'}});
  var submit = ui.Button('Submit Pixel');
  panel.add(ui.Panel([ui.Label('Longitude', {width: '70px'}), lonBox], ui.Panel.Layout.flow('horizontal')));
  panel.add(ui.Panel([ui.Label('Latitude', {width: '70px'}), latBox], ui.Panel.Layout.flow('horizontal')));
  var reference = ui.Select({
    placeholder: 'Reference pixels',
    items: c.reference_pixels.map(function (p, i) { return {label: p.label, value: i}; }),
    onChange: function (i) {
      var p = c.reference_pixels[i];
      lonBox.setValue(String(p.lon));
      latBox.setValue(String(p.lat));
      inspect(p.lon, p.lat);
    }
  });
  panel.add(ui.Panel([submit, reference], ui.Panel.Layout.flow('horizontal')));
  var status = ui.Label('', {fontSize: '12px', whiteSpace: 'pre'});
  var results = ui.Panel();
  panel.add(status);
  panel.add(results);

  // ---------------------------------------------------------------- inspector
  var request = 0;  // only the latest request's answer is shown

  function showMarker(lon, lat) {
    if (markerLayer) map.layers().remove(markerLayer);
    markerLayer = ui.Map.Layer(ee.Geometry.Point([lon, lat]), {color: MARKER_COLOR}, 'Selected pixel');
    map.layers().add(markerLayer);
  }

  function inspect(lon, lat) {
    var mine = ++request;
    showMarker(lon, lat);
    results.clear();
    status.setValue('Loading the pixel history at ' + lat.toFixed(5) + ', ' + lon.toFixed(5) + '...');
    inspector.historyQuery(result, config, lon, lat).evaluate(function (tables, error) {
      if (mine !== request) return;
      if (error) {
        status.setValue('Pixel history failed: ' + error + '\nTry again or another pixel.');
        return;
      }
      var rows = inspector.historyRows(tables, config);
      if (!inspector.hasObservations(rows)) {
        status.setValue('No clear observations here: outside the study area, masked (water), or always ' +
                        'cloudy. Try another pixel.');
        return;
      }
      status.setValue('Pixel at ' + lat.toFixed(5) + ' N, ' + Math.abs(lon).toFixed(5) + (lon < 0 ? ' W' : ' E') +
                      '\nCoordinate: ' + lon + ', ' + lat + ' (lon, lat); sampled on the 30 m result grid');
      results.add(inspector.targetFitChart(rows, config.reduction.band));
      results.add(inspector.probabilityChart(rows, threshold));
      inspector.crossingNotes(rows, threshold).forEach(function (note) {
        results.add(ui.Label('Target season: ' + note, {fontSize: '12px'}));
      });
    });
  }

  map.onClick(function (coords) {
    lonBox.setValue(String(coords.lon));
    latBox.setValue(String(coords.lat));
    inspect(coords.lon, coords.lat);
  });

  submit.onClick(function () {
    var lon = parseFloat(lonBox.getValue()), lat = parseFloat(latBox.getValue());
    if (!isFinite(lon) || !isFinite(lat)) {
      status.setValue('Enter a numeric longitude and latitude (decimal degrees).');
      return;
    }
    if (lon < -180 || lon > 180 || lat < -90 || lat > 90) {
      status.setValue('Longitude must be within +-180 and latitude within +-90.');
      return;
    }
    inspect(lon, lat);
  });

  ui.root.clear();
  ui.root.add(ui.SplitPanel(panel, map));
  return {map: map, panel: panel, inspect: inspect, result: result, outcome: outcome};
}

if (typeof exports !== 'undefined') exports.main = main;

// Code Editor entry point. Node (the tests) has `process` and calls main()
// itself with locally required modules.
if (typeof process === 'undefined') {
  main(require(BULCD_MODULE), require(APP_MODULE_ROOT + 'config'), require(APP_MODULE_ROOT + 'outputs'),
       require(APP_MODULE_ROOT + 'inspector'));
}
