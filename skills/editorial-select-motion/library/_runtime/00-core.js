  /* core: what every module shares. The fitted curves as control points (the
     union of tokens.css and the camera's fits from the source footage), one
     cubic-bezier solver, and EditorialSelect Serif's glyph metrics in the two
     shapes the text helpers read (em fractions for shared.layout, font units for
     kit.measure), both derived from the one table es-serif-metrics.json. */
  var core = R.core = (function () {
    var FPS = 24, EPS = 0.0001;
    var CURVE = { snap: [0.33, 1, 0.68, 1], drift: [0.15, 0.11, 0.614, 0.796], "drift-linear": [0.385, 0.326, 0.732, 0.781],
      push: [0.336, -0.065, 0, 0.821], "push-hard": [0.772, 0.446, 0.15, 0.453], pull: [0.924, 0.668, 0.604, 0.958],
      glide: [0.034, 0.665, 0.702, 1.023], reveal: [0.081, -0.525, 0, 0.951], rise: [0.15, 0.85, 0.3, 1],
      pass: [0.45, 0.05, 0.55, 0.95], settle: [0.42, 0.543, 1, 1.076], zoom: [0.213, 0.313, 0.759, 0.883], linear: [0, 0, 1, 1],
      "film-push": [0.587, -0.033, 0.263, 1.135], "film-pull": [0.473, 0.464, 0.332, 0.974], "film-tilt": [1.0, 0.937, 0.874, 0.965] };
    function bez4(x1, y1, x2, y2) {
      var cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx, cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
      return function (p) {
        if (p <= 0) return 0; if (p >= 1) return 1;
        var lo = 0, hi = 1, t = p, x, i;
        for (i = 0; i < 40; i++) { x = ((ax * t + bx) * t + cx) * t; if (Math.abs(x - p) < 1e-7) break; if (x < p) lo = t; else hi = t; t = (lo + hi) / 2; }
        return ((ay * t + by) * t + cy) * t;
      };
    }
    var M = __ES_SERIF_METRICS__;
    function emMetrics() {
      var u = M.upm, o = { cap: M.cap / u, x: M.x / u, asc: M.asc / u, desc: M.desc / u, adv: {}, kern: {}, ink: {} }, c;
      for (c in M.adv) o.adv[c] = M.adv[c] / u;
      for (c in M.kern) o.kern[c] = M.kern[c] / u;
      for (c in M.ink) o.ink[c] = [M.ink[c][0] / u, M.ink[c][1] / u, M.ink[c][2] / u, M.ink[c][3] / u];
      return o;
    }
    function unitMetrics() {
      var o = { adv: {}, ink: {}, kern: {} }, c;
      for (c in M.adv) o.adv[c] = M.adv[c];
      for (c in M.ink) o.ink[c] = [M.ink[c][0], M.ink[c][2]];
      for (c in M.kern) o.kern[c] = M.kern[c];
      return o;
    }
    return { FPS: FPS, EPS: EPS, CURVE: CURVE, bez4: bez4, METRICS: M, emMetrics: emMetrics, unitMetrics: unitMetrics };
  })();
