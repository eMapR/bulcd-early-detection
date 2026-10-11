// Minimal stand-in for the Code Editor's `ui` so app.js can run under Node:
// widgets record what the app does to them (values, children, handlers,
// layers, charts) and every other method is a chainable no-op.

function activeList(initial) {
  const items = (initial || []).slice();
  return {
    items,
    add(x) { items.push(x); return this; },
    remove(x) { const i = items.indexOf(x); if (i >= 0) items.splice(i, 1); return this; },
    insert(i, x) { items.splice(i, 0, x); return this; },
    get(i) { return items[i]; },
    length() { return items.length; },
    reset(xs) { items.splice(0, items.length, ...(xs || [])); return this; },
  };
}

function widget(kind, args) {
  // Only a plain object literal is an options argument (not an array of widgets, not a widget).
  const opts = args[0] && Object.getPrototypeOf(args[0]) === Object.prototype && !('state' in args[0]) ? args[0] : {};
  const state = { kind, args, value: undefined, children: [], handlers: {}, layers: activeList(), views: [] };
  if ('value' in opts) state.value = opts.value;
  if (opts.onChange) state.handlers.change = opts.onChange;
  if (opts.onClick) state.handlers.click = opts.onClick;
  if (kind === 'Panel' && Array.isArray(args[0])) state.children = args[0].slice();
  if (kind === 'Label' || kind === 'Button') state.value = typeof args[0] === 'string' ? args[0] : opts.label;
  const items = activeList(opts.items || []);
  const tools = {
    layers: activeList(),
    shape: null,
    setShown() {}, setLinked() {}, setDrawModes() {},
    onDraw(fn) { this.handlers = { draw: fn }; },
    setShape(s) { this.shape = s; }, getShape() { return this.shape; },
    addLayer() { const l = { geometries: () => activeList() }; this.layers.add(l); return l; },
  };
  tools.layers.length = function () { return this.items.length; };
  const target = {
    state,
    setValue(v) { state.value = v; if (state.handlers.change) state.handlers.change(v); return proxy; },
    getValue() { return state.value; },
    add(child) { state.children.push(child); return proxy; },
    clear() { state.children = []; return proxy; },
    items() { return items; },
    onClick(fn) { state.handlers.click = fn; return proxy; },
    onChange(fn) { state.handlers.change = fn; return proxy; },
    layers() { return state.layers; },
    drawingTools() { return tools; },
    // Map view changes, recorded so tests can see when the app moves the map.
    centerObject(...a) { state.views.push(['centerObject', ...a]); return proxy; },
    setCenter(...a) { state.views.push(['setCenter', ...a]); return proxy; },
  };
  const proxy = new Proxy(target, {
    get(t, prop) {
      if (prop in t) return t[prop];
      if (prop === 'then') return undefined;
      return () => proxy;  // style(), set(), setOptions(), setCenter(), centerObject(), ...
    },
  });
  return proxy;
}

function makeUi() {
  const created = { charts: [], maps: [], labels: [], buttons: [], selects: [], sliders: [] };
  const make = (kind) => (...args) => {
    const w = widget(kind, args);
    if (kind === 'Chart') created.charts.push({ table: args[0], type: args[1], options: args[2] });
    if (kind === 'Map') created.maps.push(w);
    if (kind === 'Label') created.labels.push(w);
    if (kind === 'Button') created.buttons.push(w);
    if (kind === 'Select') created.selects.push(w);
    if (kind === 'Slider') created.sliders.push(w);
    return w;
  };
  const ui = {};
  for (const kind of ['Label', 'Button', 'Textbox', 'Select', 'Checkbox', 'Slider', 'Chart', 'Map', 'SplitPanel']) {
    ui[kind] = make(kind);
  }
  ui.Panel = make('Panel');
  ui.Panel.Layout = { flow: (d) => d };
  ui.Map.Layer = (image, vis, name, shown, opacity) => ({
    image, vis, name, shown, opacity,
    setEeObject(x) { this.image = x; }, setVisParams(v) { this.vis = v; }, setName(n) { this.name = n; },
  });
  ui.root = widget('root', []);
  return { ui, created };
}

module.exports = { makeUi };
