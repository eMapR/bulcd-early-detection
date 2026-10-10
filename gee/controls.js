// Settings panel: the interactive notebook's controls (app.py
// _build_settings_step()) as Code Editor widgets. Defaults and limits come from
// config.js NOTEBOOK_DEFAULTS / RANGES; read() returns a controls object for
// config.js buildConfig(). Needs the Code Editor's `ui`. Plain ES5.

var LABEL = {fontSize: '12px', margin: '6px 8px 0 8px'};
var HINT = {fontSize: '11px', color: '#666', margin: '0 8px 4px 16px'};

function range(a, b) {
  var out = [];
  for (var i = a; i <= b; i++) out.push(i);
  return out;
}

function pad(n) {
  return (n < 10 ? '0' : '') + n;
}

function row(widgets) {
  return ui.Panel(widgets, ui.Panel.Layout.flow('horizontal'));
}

function yearSelect(years, value, onChange) {
  return ui.Select({items: years.map(String), value: String(value), onChange: onChange, style: {width: '90px'}});
}

// Month + day selects; the day list follows the month (Feb 29 left out, as in app.py).
function monthDay(appConfig, value, onChange) {
  var p = value.split('-');
  var month = ui.Select({items: appConfig.MONTH_NAMES.map(function (m, i) { return {label: m, value: String(i + 1)}; }),
                         value: String(Number(p[0])), style: {width: '80px'}});
  var day = ui.Select({items: range(1, appConfig.DAYS_IN_MONTH[Number(p[0]) - 1]).map(String),
                       value: String(Number(p[1])), style: {width: '70px'}});
  month.onChange(function (m) {
    var keep = Math.min(Number(day.getValue()), appConfig.DAYS_IN_MONTH[Number(m) - 1]);
    day.items().reset(range(1, appConfig.DAYS_IN_MONTH[Number(m) - 1]).map(String));
    day.setValue(String(keep));
    onChange();
  });
  day.onChange(onChange);
  return {
    widgets: [month, day],
    get: function () { return pad(Number(month.getValue())) + '-' + pad(Number(day.getValue())); }
  };
}

function slider(r, value, onChange) {
  return ui.Slider({min: r.min, max: r.max, step: r.step, value: value, onChange: onChange,
                    style: {stretch: 'horizontal'}});
}

// Builds the panel. onChange() is called after any setting changes.
function makeControls(appConfig, onChange) {
  var d = appConfig.NOTEBOOK_DEFAULTS, r = appConfig.RANGES;
  var changed = function () { describe(); if (onChange) onChange(); };
  var expYears = range(r.expectation_years[0], r.expectation_years[1]);

  var expFirst = yearSelect(expYears, d.expectation_first, changed);
  var expLast = yearSelect(expYears, d.expectation_last, changed);
  var monitoring = yearSelect(r.monitoring_years, d.monitoring_year, changed);
  var start = monthDay(appConfig, d.season_start, changed);
  var end = monthDay(appConfig, d.season_end, changed);
  var sensitivity = slider(r.sensitivity, d.sensitivity, changed);
  var threshold = slider(r.decision_threshold, d.decision_threshold, changed);
  var timing = ui.Checkbox({label: 'Also map the first-detected season', value: d.timing, onChange: changed});
  var expectationNote = ui.Label('', HINT);
  var relationship = ui.Label('', {fontSize: '12px', whiteSpace: 'pre-wrap', margin: '6px 8px',
                                   padding: '4px 6px', border: '1px solid #2a78d6'});

  var dampening = slider(r.dampening, d.dampening, changed);
  var posterior = slider(r.posterior_leveler, d.posterior_leveler, changed);
  var sensors = {};
  appConfig.MONITORING_SENSORS.forEach(function (s) {
    sensors[s] = ui.Checkbox({label: appConfig.SENSOR_LABELS[s], value: d.sensors[s], onChange: changed});
  });
  var maskForest = ui.Checkbox({label: 'Analyze forest only (Hansen tree cover >= 10%)', value: d.mask_forest,
                                onChange: changed});
  var maskWater = ui.Checkbox({label: 'Leave out water', value: d.mask_water, onChange: changed});
  var allowLarge = ui.Checkbox({label: 'Allow areas over 1,000 km2 (slow; may time out)', value: d.allow_large,
                                onChange: changed});

  var advanced = ui.Panel([
    ui.Label('Normally left alone. Defaults match the demonstration notebooks.', HINT),
    ui.Label('Dampening', LABEL), dampening,
    ui.Label('how much weight each single observation carries (1 = full)', HINT),
    ui.Label('Posterior leveler', LABEL), posterior,
    ui.Label('pull toward even odds after each update (1 = off)', HINT),
    ui.Label('Monitoring sensors (the expectation always uses Landsat 8)', LABEL),
    row(appConfig.MONITORING_SENSORS.map(function (s) { return sensors[s]; })),
    maskForest, maskWater, allowLarge
  ], null, {shown: false, margin: '0 0 0 8px'});
  var showAdvanced = ui.Checkbox({label: 'Advanced settings', value: false,
                                  onChange: function (on) { advanced.style().set('shown', on); }});

  var panel = ui.Panel([
    ui.Label('Expectation years', LABEL), row([expFirst, ui.Label('to'), expLast]),
    expectationNote,
    ui.Label('Monitoring year', LABEL), monitoring,
    ui.Label('Season (each expectation year and the monitoring year)', LABEL),
    row(start.widgets.concat([ui.Label('to')]).concat(end.widgets)),
    relationship,
    ui.Label('Sensitivity', LABEL), sensitivity,
    ui.Label('Higher sensitivity makes the model more responsive to smaller departures from expected ' +
             'conditions.', HINT),
    ui.Label('Decision threshold', LABEL), threshold,
    ui.Label('How confident BULC-D must be before identifying a change.', HINT),
    timing, showAdvanced, advanced
  ]);

  function read() {
    var s = {};
    appConfig.MONITORING_SENSORS.forEach(function (k) { s[k] = sensors[k].getValue(); });
    return {
      expectation_first: Number(expFirst.getValue()), expectation_last: Number(expLast.getValue()),
      monitoring_year: Number(monitoring.getValue()),
      season_start: start.get(), season_end: end.get(),
      sensitivity: sensitivity.getValue(), decision_threshold: threshold.getValue(), timing: timing.getValue(),
      dampening: dampening.getValue(), posterior_leveler: posterior.getValue(), sensors: s,
      mask_forest: maskForest.getValue(), mask_water: maskWater.getValue(), allow_large: allowLarge.getValue()
    };
  }

  function describe() {
    var c = read(), problem = appConfig.validateControls(c);
    expectationNote.setValue(appConfig.expectationSummary(c));
    if (problem) {
      relationship.setValue(problem + ' Run is blocked until this is fixed.');
      relationship.style().set({color: '#b00', border: '1px solid #b00'});
    } else {
      relationship.setValue(appConfig.describeControls(c).join('\n'));
      relationship.style().set({color: '#222', border: '1px solid #2a78d6'});
    }
  }

  describe();
  return {panel: panel, read: read};
}

exports.makeControls = makeControls;
