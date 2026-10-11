// Chart tables equal up to floating-point noise: Earth Engine can return a
// computed value differing in the last bit between evaluations of the same
// expression (seen in the fitted curve: 0.3100212213701912 vs ...19117).
const TOL = 1e-6;

function close(a, b) {
  if (typeof a === 'number' && typeof b === 'number') return Math.abs(a - b) <= TOL;
  if (Array.isArray(a) || (a && typeof a === 'object')) {
    if (!b || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return false;
    const ka = Object.keys(a), kb = Object.keys(b);
    return ka.length === kb.length && ka.every((k) => close(a[k], b[k]));
  }
  return a === b;
}

module.exports = { tablesClose: close, TOL };
