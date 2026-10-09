// Study area (AOI) helpers: the size check for live runs.
//
// JS mirror of src/bulcd_early_detection/outputs.py aoi_size_report() and its
// limits, as the interactive notebook applies them (app.py _use_area()). Pure
// apart from building the Earth Engine request. Plain ES5.

// outputs.py: TESTED_LIVE_KM2 is the largest area run live so far (Milestone 1
// spatial validation, ~78 km2 buffers); over LARGE_AOI_KM2 a live run is blocked
// unless the user allows it.
var TESTED_LIVE_KM2 = 100;
var LARGE_AOI_KM2 = 1000;

// One request: boundary area, bounding-box area and ring, and the centroid
// (for the UTM zone, as outputs.utm_crs()).
function sizeQuery(geometry) {
  var bounds = geometry.bounds(1);
  return ee.Dictionary({
    area_km2: geometry.area(10).divide(1e6),
    bbox_km2: bounds.area(10).divide(1e6),
    bbox: bounds.coordinates().get(0),
    centroid: geometry.centroid(100).coordinates()
  });
}

function verdict(km2) {
  return km2 <= TESTED_LIVE_KM2 ? 'ok' : km2 <= LARGE_AOI_KM2 ? 'slow' : 'large';
}

// Evaluated sizeQuery() -> the report aoi_size_report() returns, plus centroid.
function sizeReport(stats) {
  var xs = stats.bbox.map(function (p) { return p[0]; }), ys = stats.bbox.map(function (p) { return p[1]; });
  return {
    area_km2: stats.area_km2, bbox_km2: stats.bbox_km2,
    bbox_degrees: [Math.min.apply(null, xs), Math.min.apply(null, ys), Math.max.apply(null, xs),
                   Math.max.apply(null, ys)],
    centroid: stats.centroid,
    verdict: verdict(stats.area_km2)
  };
}

function fmtKm2(km2) {
  return km2 >= 100 ? Math.round(km2).toLocaleString('en-US') : km2.toFixed(1);
}

// The notebook's message for an AOI, and whether a run may use it.
function assess(report, allowLarge) {
  var km2 = fmtKm2(report.area_km2);
  if (report.verdict === 'large' && !allowLarge) {
    return {ok: false, message: km2 + ' km2 is over the ' + LARGE_AOI_KM2.toLocaleString('en-US') + ' km2 limit. ' +
                                "Use a smaller area, or tick 'Allow areas over 1,000 km2' under Advanced settings."};
  }
  var note = {ok: 'size is fine for a live run.',
              slow: 'larger than anything run live so far (~' + TESTED_LIVE_KM2 + ' km2); maps may be slow.',
              large: 'very large; live maps will very likely time out.'}[report.verdict];
  return {ok: true, message: km2 + ' km2, ' + note};
}

// UTM zone EPSG code for a coordinate (outputs.utm_crs()).
function utmCrs(lon, lat) {
  var zone = Math.floor((lon + 180) / 6) + 1;
  return 'EPSG:' + ((lat >= 0 ? 32600 : 32700) + zone);
}

exports.TESTED_LIVE_KM2 = TESTED_LIVE_KM2;
exports.LARGE_AOI_KM2 = LARGE_AOI_KM2;
exports.sizeQuery = sizeQuery;
exports.verdict = verdict;
exports.sizeReport = sizeReport;
exports.assess = assess;
exports.utmCrs = utmCrs;
