// BULC-D Early Detection - Earth Engine Code Editor app.
//
// The interactive Early Detection notebook (src/bulcd_early_detection/app.py)
// is the UI reference: choose or draw an area -> set expectation and monitoring
// -> Run -> condition, first-detected season and reference-imagery layers ->
// click a pixel or enter its lon/lat to inspect it. BULC-D itself runs in
// BULC-D_rebuild's gee/bulcd.js, held to JS <-> Python parity; this repo only
// builds configs and interprets outputs (config.js, outputs.js, inspector.js).
// Validation fixtures (reference case and pixels) live in gee/tests only.
//
// The require() paths at the bottom use OWNER as a placeholder;
// tools/build_gee_deploy.py fills in the Earth Engine username. Plain ES5.

var MARKER_COLOR = '#00e5ff';
var OUTLINE_COLOR = 'ffd400';
var AREA_SOURCES = {draw: 'Draw on the map', asset: 'Earth Engine asset'};
// Starting view (the notebook's default map center).
var MAP_CENTER = {lon: -123.552, lat: 44.834, zoom: 12};

var H2 = {fontSize: '16px', fontWeight: 'bold', margin: '12px 8px 4px'};
var SMALL = {fontSize: '12px'};
var ERROR = {fontSize: '12px', color: '#b00', whiteSpace: 'pre-wrap'};
var INFO = {fontSize: '12px', color: '#222', whiteSpace: 'pre-wrap'};

function legendRow(color, label) {
  return ui.Panel([
    ui.Label('', {backgroundColor: color, padding: '7px', margin: '4px 8px 4px 0', border: '1px solid #999'}),
    ui.Label(label, {margin: '4px 0', fontSize: '12px'})
  ], ui.Panel.Layout.flow('horizontal'));
}

function setMessage(label, text, isError) {
  label.setValue(text);
  label.style().set(isError ? ERROR : INFO);
}

// One line naming the settings a run used, shown with the inspector's charts
// so reruns at the same pixel can be told apart.
function runLabel(c) {
  return 'Monitoring ' + c.monitoring_year + ' (' + c.season_start + ' to ' + c.season_end + '), expectation ' +
         c.expectation_first + '-' + c.expectation_last + '; sensitivity ' + c.sensitivity + ', thresholds ' +
         c.decrease_threshold + ' decrease / ' + c.increase_threshold + ' increase, dampening ' + c.dampening +
         ', posterior ' + c.posterior_leveler + ', expectation fit order ' + c.fit_order + '; sensors ' +
         Object.keys(c.sensors).filter(function (k) { return c.sensors[k]; }).join('+') +
         (c.mask_forest ? '; forest only' : '') + (c.mask_water ? '; water masked' : '') +
         (c.timing ? '; detection timing ' + (c.timing_confirmed ? 'confirmed' : 'raw') : '');
}

function main(bulcd, appConfig, outputs, inspector, aoi, controlsUi) {
  var state = {area: null, run: null, request: 0, runToken: 0};

  // ---------------------------------------------------------------- map
  var map = ui.Map();
  map.setOptions('HYBRID');
  map.style().set('cursor', 'crosshair');
  map.setCenter(MAP_CENTER.lon, MAP_CENTER.lat, MAP_CENTER.zoom);
  var tools = map.drawingTools();
  tools.setShown(true);
  tools.setLinked(false);
  tools.setDrawModes(['polygon', 'rectangle']);
  tools.addLayer([], 'Drawn area', OUTLINE_COLOR);
  // Keep exactly one drawn shape: the latest. Then leave drawing mode so map clicks inspect pixels again.
  tools.onDraw(function (geometry, layer) {
    var geoms = layer.geometries();
    while (geoms.length() > 1) geoms.remove(geoms.get(0));
    tools.setShape(null);
  });
  var resultLayers = [], outlineLayer = null, markerLayer = null;

  function removeLayer(layer) {
    if (layer) map.layers().remove(layer);
  }

  function addLayer(image, vis, name, shown, opacity) {
    var layer = ui.Map.Layer(image, vis, name, shown, opacity === undefined ? 1 : opacity);
    map.layers().add(layer);
    resultLayers.push(layer);
    return layer;
  }

  // Outline and marker stay on top of the result layers.
  function keepOnTop() {
    [outlineLayer, markerLayer].forEach(function (layer) {
      if (layer) {
        map.layers().remove(layer);
        map.layers().add(layer);
      }
    });
  }

  // ---------------------------------------------------------------- panel
  var panel = ui.Panel({style: {width: '460px', padding: '8px'}});
  panel.add(ui.Label('BULC-D Early Detection', {fontSize: '20px', fontWeight: 'bold', margin: '4px 8px'}));

  // 1. Area
  panel.add(ui.Label('1. Choose an area', H2));
  var source = ui.Select({items: [AREA_SOURCES.draw, AREA_SOURCES.asset], value: AREA_SOURCES.draw,
                          style: {width: '260px'}});
  var assetBox = ui.Textbox({placeholder: 'projects/<project>/assets/<feature_collection>',
                             style: {width: '420px', shown: false}});
  var drawHint = ui.Label('Draw a polygon or rectangle with the drawing tools on the map (top left). ' +
                          'Only the latest shape is used.', {fontSize: '12px'});
  var useArea = ui.Button('Use this area');
  var areaInfo = ui.Label('', INFO);
  panel.add(source).add(assetBox).add(drawHint).add(useArea).add(areaInfo);
  source.onChange(function (v) {
    assetBox.style().set('shown', v === AREA_SOURCES.asset);
    drawHint.style().set('shown', v === AREA_SOURCES.draw);
    tools.setShown(v === AREA_SOURCES.draw);
  });

  // 2. Settings
  panel.add(ui.Label('2. Expectation and monitoring', H2));
  var controls = controlsUi.makeControls(appConfig);
  panel.add(controls.panel);

  // 3. Run
  panel.add(ui.Label('3. Run', H2));
  var runButton = ui.Button({label: 'Run Early Detection', style: {fontWeight: 'bold'}});
  panel.add(runButton);
  var status = ui.Label('', INFO);
  panel.add(status);
  var legend = ui.Panel();
  panel.add(legend);

  // 4. Pixel inspector
  panel.add(ui.Label('4. Pixel inspector', H2));
  panel.add(ui.Label('After a run, click the map, or enter a coordinate (decimal degrees) and press Submit Pixel. ' +
                     'A click fills the boxes, so after changing settings and running again, Submit Pixel ' +
                     'inspects the same 30 m pixel.', SMALL));
  var lonBox = ui.Textbox({placeholder: 'Longitude', style: {width: '180px'}});
  var latBox = ui.Textbox({placeholder: 'Latitude', style: {width: '180px'}});
  var submit = ui.Button('Submit Pixel');
  panel.add(ui.Panel([ui.Label('Longitude', {width: '70px'}), lonBox], ui.Panel.Layout.flow('horizontal')));
  panel.add(ui.Panel([ui.Label('Latitude', {width: '70px'}), latBox], ui.Panel.Layout.flow('horizontal')));
  panel.add(submit);
  var inspectStatus = ui.Label('', INFO);
  var results = ui.Panel();
  panel.add(inspectStatus);
  panel.add(results);

  // ---------------------------------------------------------------- area
  // Resolves the chosen area (async: a drawn shape and the size check need the
  // server), then calls done(area) or reports why it can't be used.
  function chooseArea(done) {
    var v = source.getValue(), allowLarge = controls.read().allow_large;
    function sized(area) {
      setMessage(areaInfo, 'Checking the area size...');
      aoi.sizeQuery(area.geometry).evaluate(function (stats, error) {
        if (error) return setMessage(areaInfo, 'Could not use this area: ' + error, true);
        area.report = aoi.sizeReport(stats);
        var verdict = aoi.assess(area.report, allowLarge);
        if (!verdict.ok) {
          state.area = null;
          return setMessage(areaInfo, verdict.message, true);
        }
        setMessage(areaInfo, 'Using ' + area.name + ': ' + verdict.message);
        state.area = area;
        var b = area.report.bbox_degrees;
        map.centerObject(ee.Geometry.Rectangle(b), null);
        removeLayer(outlineLayer);
        outlineLayer = ui.Map.Layer(ee.FeatureCollection([ee.Feature(area.geometry)])
          .style({color: OUTLINE_COLOR, fillColor: '00000000', width: 2}), {}, 'Study area');
        map.layers().add(outlineLayer);
        keepOnTop();
        if (done) done(area);
      });
    }
    if (v === AREA_SOURCES.asset) {
      var id = assetBox.getValue().trim();
      if (!id) return setMessage(areaInfo, 'Enter an Earth Engine FeatureCollection asset ID.', true);
      return sized({name: id.split('/').pop(), geometry: ee.FeatureCollection(id).geometry(), aoi: {aoi_asset: id}});
    }
    var layer = tools.layers().length() ? tools.layers().get(0) : null;
    if (!layer || layer.geometries().length() === 0) {
      return setMessage(areaInfo, 'Draw a polygon or rectangle on the map first.', true);
    }
    setMessage(areaInfo, 'Reading the drawn shape...');
    var drawn = layer.getEeObject();
    ee.Dictionary({type: drawn.type(), coordinates: drawn.coordinates()}).evaluate(function (g, error) {
      if (error) return setMessage(areaInfo, 'Could not read the drawn shape: ' + error, true);
      if (g.type !== 'Polygon') return setMessage(areaInfo, 'Draw a single polygon or rectangle.', true);
      var ring = g.coordinates[0];
      sized({name: 'the drawn area', geometry: ee.Geometry.Polygon([ring]), aoi: {aoi_coordinates: ring}});
    });
  }

  useArea.onClick(function () { chooseArea(null); });

  // ---------------------------------------------------------------- runs
  function clearResults() {
    resultLayers.forEach(removeLayer);
    resultLayers = [];
    legend.clear();
    state.runToken++;
  }

  // Stores the run the inspector reads, and tells the user how to compare.
  function setRun(run) {
    state.run = run;
    state.request++;  // drop any inspection still loading from the previous run
    results.clear();
    var lon = lonBox.getValue(), lat = latBox.getValue();
    setMessage(inspectStatus, 'Inspector now uses: ' + run.label +
               (lon && lat ? '\nPress Submit Pixel to inspect ' + lon + ', ' + lat + ' under these settings.' : ''));
  }

  function conditionLegend(title) {
    legend.add(ui.Label(title, {fontWeight: 'bold', fontSize: '12px', margin: '8px 8px 0'}));
    [outputs.DECREASE, outputs.UNCHANGED, outputs.INCREASE].forEach(function (k) {
      legend.add(legendRow(outputs.OUTCOME_COLORS[k], outputs.OUTCOME_LABELS[k]));
    });
  }

  // The notebook's run (app.py _compute()): condition map, first-detected
  // season, true color and NBR composite for three years.
  function runControls(c, area) {
    var config = appConfig.buildConfig(c, area.aoi);
    var full = bulcd.withDefaults(config);
    var thresholds = {decrease: c.decrease_threshold, increase: c.increase_threshold};
    var geom = area.geometry, token = state.runToken;
    var result = bulcd.runBulcd(full);
    var outcome = outputs.outcomeImage(bulcd, result, full, thresholds.decrease, thresholds.increase).clip(geom);

    var years = c.timing ? appConfig.timingYears(c) : [];
    var timing = null, episodes = null;
    if (years.length) {
      var seasons = {};
      // First-detected season, last detection and detection episodes: the decrease threshold.
      years.forEach(function (y) {
        seasons[y] = outputs.detectionTimingImage(bulcd, appConfig.buildConfig(appConfig.withMonitoringYear(c, y),
                                                                             area.aoi), thresholds.decrease,
                                                  thresholds.increase);
      });
      timing = outputs.combineSeasonTiming(seasons, c.timing_confirmed).clip(geom);
      // Separate per-season images for the episode layers, so each layer's description stays small.
      var codes = {};
      years.forEach(function (y) {
        codes[y] = outputs.detectionEpisodeImage(bulcd, appConfig.buildConfig(appConfig.withMonitoringYear(c, y),
                                                                            area.aoi), thresholds.decrease,
                                                 thresholds.increase, c.timing_confirmed);
      });
      episodes = outputs.combineEpisodeMetrics(codes).clip(geom);
    }

    // Layers, bottom to top (the notebook's order); only the condition layer starts on.
    var imgYears = [c.monitoring_year - 2, c.monitoring_year - 1, c.monitoring_year];
    var window = [c.season_start, c.season_end];
    imgYears.forEach(function (y) {
      addLayer(outputs.annualTrueColor(geom, y, window).clip(geom), outputs.TRUE_COLOR, 'True color ' + y, false);
    });
    var nbrName = 'NBR composite R=' + imgYears[0] + ' G=' + imgYears[1] + ' B=' + imgYears[2];
    // Added now so it keeps its place in the layer order; its image and stretch are set once the stretch is known.
    var nbrLayer = addLayer(ee.Image(), {}, nbrName + ' (loading)', false);
    if (timing) {
      addLayer(timing.select('first_decrease_year'), outputs.timingVis(years), 'First detected season (decrease)',
               false);
      var firstDoy = appConfig.dayOfYear(c.monitoring_year, c.season_start);
      var lastDoy = appConfig.dayOfYear(c.monitoring_year, c.season_end);
      addLayer(outputs.lastDetectionImage(episodes, years, firstDoy, lastDoy), outputs.lastDetectionVis(years),
               'Last detection (decrease)', false);
      addLayer(outputs.episodesImage(episodes), outputs.episodesVis(), 'Detection episodes (decrease)', false);
    }
    addLayer(outputs.conditionLayerImage(outcome.select('outcome')), outputs.conditionVis(),
             'Condition ' + c.monitoring_year, true, 0.85);
    keepOnTop();

    // NBR composite: one stretch across the three years, water masked (app.py nbr_vis()).
    var large = area.report.area_km2 > aoi.TESTED_LIVE_KM2;
    var crs = aoi.utmCrs(area.report.centroid[0], area.report.centroid[1]);
    var land = imgYears.map(function (y) {
      return outputs.annualNbr(geom, y, window, crs, !large).updateMask(outputs.notWater());
    });
    outputs.nbrStretchQuery(land, geom, large ? 120 : 30).evaluate(function (stats, error) {
      if (token !== state.runToken) return;  // a newer run replaced these layers
      var stretch = stats && outputs.nbrStretchFromStats(stats);
      if (error || !stretch) {
        nbrLayer.setName(nbrName + ' (failed to load)');
        legend.add(ui.Label(nbrName + ': failed to load (' + (error || 'no clear Sentinel-2 data') + ')', ERROR));
        return;
      }
      nbrLayer.setEeObject(ee.Image.cat(land).clip(geom));
      nbrLayer.setVisParams({min: [stretch[0], stretch[0], stretch[0]], max: [stretch[1], stretch[1], stretch[1]]});
      nbrLayer.setName(nbrName);
      legend.add(ui.Label(nbrName + ': one stretch ' + stretch[0].toFixed(2) + ' to ' + stretch[1].toFixed(2) +
                          '; colors are spectral timing clues, not confirmed disturbance dates.',
                          {fontSize: '11px', color: '#666'}));
    });

    conditionLegend(c.monitoring_year + ' condition relative to expectation (' + c.expectation_first + '-' +
                    c.expectation_last + ')');
    if (timing) {
      legend.add(ui.Label('First detected season (layer off by default)', {fontWeight: 'bold', fontSize: '12px',
                                                                          margin: '8px 8px 0'}));
      years.forEach(function (y, i) {
        legend.add(legendRow(outputs.YEAR_COLORS[i], 'Decrease first detected in ' + y));
      });
      legend.add(ui.Label('Last detection (layer off by default): in the same season, the start of the most ' +
                          'recent period above the decrease threshold' +
                          (c.timing_confirmed ? ' (it lasted to the end of the season)' : ''),
                          {fontWeight: 'bold', fontSize: '12px', margin: '8px 8px 0', whiteSpace: 'pre-wrap'}));
      outputs.lastDetectionLegend(years, appConfig.monthDayLabel(c.season_start), appConfig.monthDayLabel(c.season_end))
        .forEach(function (row) { legend.add(legendRow(row[0], row[1])); });
      legend.add(ui.Label('Detection episodes (layer off by default): separate times P(decrease) rose above the ' +
                          'threshold in that season; no smoothing',
                          {fontWeight: 'bold', fontSize: '12px', margin: '8px 8px 0', whiteSpace: 'pre-wrap'}));
      outputs.EPISODE_COLORS.forEach(function (color, i) { legend.add(legendRow(color, outputs.EPISODE_LABELS[i])); });
      legend.add(ui.Label(c.timing_confirmed ? 'Timing layers: confirmed (only seasons that end as decrease).'
                                             : 'Timing layers: raw (any crossing counts, even one later retracted).',
                          {fontSize: '11px', color: '#666', margin: '4px 8px'}));
    }
    setRun({result: result, config: full, thresholds: thresholds, label: runLabel(c), outcome: outcome,
            timing: timing, episodes: episodes});
  }

  runButton.onClick(function () {
    var c = controls.read(), problem = appConfig.validateControls(c);
    if (problem) return setMessage(status, 'Check the settings: ' + problem, true);
    setMessage(status, 'Setting up the run...');
    chooseArea(function (area) {
      clearResults();
      try {
        runControls(c, area);
      } catch (e) {
        return setMessage(status, 'Run failed: ' + (e.message || e), true);
      }
      setMessage(status, 'Running. Layers draw as Earth Engine computes them (a ~25 km2 area takes a few ' +
                         'minutes). Use the map\'s Layers control to turn layers on and set opacity.');
    });
  });

  // ---------------------------------------------------------------- inspector
  function showMarker(lon, lat) {
    removeLayer(markerLayer);
    markerLayer = ui.Map.Layer(ee.Geometry.Point([lon, lat]), {color: MARKER_COLOR}, 'Selected pixel');
    map.layers().add(markerLayer);
  }

  function inspect(lon, lat) {
    var run = state.run;
    if (!run) return setMessage(inspectStatus, 'Run the analysis first, then select a pixel.', true);
    var mine = ++state.request;
    showMarker(lon, lat);
    results.clear();
    setMessage(inspectStatus, 'Loading the pixel history at ' + lat.toFixed(5) + ', ' + lon.toFixed(5) + '...');
    ee.Dictionary({history: inspector.historyQuery(run.result, run.config, lon, lat),
                   expectation: inspector.expectationQuery(bulcd, run.result, run.config, lon, lat)})
      .evaluate(function (both, error) {
      if (mine !== state.request) return;
      if (error) return setMessage(inspectStatus, 'Pixel history failed: ' + error + '\nTry again or another pixel.',
                                   true);
      var rows = inspector.historyRows(both.history, run.config);
      var expRows = inspector.expectationRows(both.expectation, run.config);
      if (!inspector.hasObservations(rows)) {
        return setMessage(inspectStatus, 'No clear observations here: outside the study area, masked (water or ' +
                                         'non-forest), or always cloudy. Try another pixel.', true);
      }
      setMessage(inspectStatus, 'Pixel at ' + lat.toFixed(5) + ' N, ' + Math.abs(lon).toFixed(5) +
                 (lon < 0 ? ' W' : ' E') + '\nCoordinate: ' + lon + ', ' + lat +
                 ' (lon, lat); sampled on the 30 m result grid\nRun: ' + run.label);
      results.add(inspector.timelineChart(expRows, rows, run.config.reduction.band));
      inspector.expectationSummary(both.expectation, expRows, run.config).forEach(function (line) {
        results.add(ui.Label(line, SMALL));
      });
      results.add(inspector.targetFitChart(rows, run.config.reduction.band));
      results.add(inspector.probabilityChart(rows, run.thresholds.decrease, run.thresholds.increase));
      inspector.crossingNotes(rows, run.thresholds.decrease, run.thresholds.increase).forEach(function (note) {
        results.add(ui.Label('Monitoring season: ' + note, SMALL));
      });
      inspector.episodeNotes(rows, run.thresholds.decrease).forEach(function (note) {
        results.add(ui.Label('Monitoring season: ' + note, SMALL));
      });
    });
  }

  map.onClick(function (coords) {
    if (tools.getShape()) return;  // drawing an area, not selecting a pixel
    lonBox.setValue(String(coords.lon));
    latBox.setValue(String(coords.lat));
    inspect(coords.lon, coords.lat);
  });

  submit.onClick(function () {
    var lon = parseFloat(lonBox.getValue()), lat = parseFloat(latBox.getValue());
    if (!isFinite(lon) || !isFinite(lat)) {
      return setMessage(inspectStatus, 'Enter a numeric longitude and latitude (decimal degrees).', true);
    }
    if (lon < -180 || lon > 180 || lat < -90 || lat > 90) {
      return setMessage(inspectStatus, 'Longitude must be within +-180 and latitude within +-90.', true);
    }
    inspect(lon, lat);
  });

  ui.root.clear();
  ui.root.add(ui.SplitPanel(panel, map));
  return {map: map, state: state, controls: controls, source: source, assetBox: assetBox, useArea: useArea,
          runButton: runButton, lonBox: lonBox, latBox: latBox, submit: submit, AREA_SOURCES: AREA_SOURCES};
}

if (typeof exports !== 'undefined') exports.main = main;

// Code Editor entry point. Node (the tests) has `process` and calls main()
// itself with locally required modules.
// require() paths MUST be string literals: the Code Editor only loads modules it
// finds as literal require('...') calls in the source, so require(variable)
// fails with "Module not found" (README.md).
if (typeof process === 'undefined') {
  main(require('users/OWNER/BULC-D_rebuild:bulcd'),
       require('users/OWNER/bulcd-early-detection:config'),
       require('users/OWNER/bulcd-early-detection:outputs'),
       require('users/OWNER/bulcd-early-detection:inspector'),
       require('users/OWNER/bulcd-early-detection:aoi'),
       require('users/OWNER/bulcd-early-detection:controls'));
}
