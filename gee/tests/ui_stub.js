// Minimal stand-in for the Code Editor's `ui` so app.js can run under Node:
// widgets record what the app does to them (values, children, click handlers,
// charts) and every other method is a chainable no-op.

function widget(kind, args) {
  const state = { kind, args, value: '', children: [], handlers: {}, layers: [] };
  const target = {
    state,
    setValue(v) { state.value = v; return proxy; },
    getValue() { return state.value; },
    add(child) { state.children.push(child); return proxy; },
    clear() { state.children = []; return proxy; },
    widgets() { return { add: (c) => state.children.push(c), reset: () => { state.children = []; } }; },
    onClick(fn) { state.handlers.click = fn; return proxy; },
    layers() {
      return { add: (l) => state.layers.push(l), remove: (l) => { state.layers = state.layers.filter((x) => x !== l); } };
    },
    addLayer(image, vis, name) { state.layers.push({ image, vis, name }); return proxy; },
  };
  const proxy = new Proxy(target, {
    get(t, prop) {
      if (prop in t) return t[prop];
      if (prop === 'then') return undefined;
      return () => proxy;  // style(), set(), setOptions(), setCenter(), ...
    },
  });
  if (kind === 'Textbox' && args[0] && args[0].value) state.value = args[0].value;
  if (kind === 'Button' && args[0] && args[0].onClick) state.handlers.click = args[0].onClick;
  if (kind === 'Panel' && Array.isArray(args[0])) state.children = args[0].slice();
  return proxy;
}

function makeUi() {
  const created = { charts: [], maps: [], labels: [] };
  const make = (kind) => (...args) => {
    const w = widget(kind, args);
    if (kind === 'Chart') created.charts.push({ table: args[0], type: args[1], options: args[2] });
    if (kind === 'Map') created.maps.push(w);
    if (kind === 'Label') { w.state.value = args[0]; created.labels.push(w); }
    return w;
  };
  const ui = {};
  for (const kind of ['Label', 'Button', 'Textbox', 'Select', 'Chart', 'Map', 'SplitPanel']) ui[kind] = make(kind);
  ui.Panel = make('Panel');
  ui.Panel.Layout = { flow: (d) => d };
  ui.Map.Layer = (geometry, vis, name) => ({ geometry, vis, name });
  ui.root = widget('root', []);
  return { ui, created };
}

module.exports = { makeUi };
