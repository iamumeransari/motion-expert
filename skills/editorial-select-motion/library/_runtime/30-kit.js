  /* kit: fitted curves, the picture cadence as an ease (shown, stepped, snap),
     glyph-metric measure in font units, the img slot and frame sequences,
     measured per-frame keys (keyed, shift) and steps placed LEAD before their
     time, and the marquee selection drawing. Was es-kit v1 (cursor, marquee,
     type-behind, card-wipe, giant-word-rise, type-fill-echo). */
  R.kit = (function () {
    var EPS = 0.0001, LEAD = 0.002, FPS = 24;
    /* ES Serif metrics (units per 1000 em): advance, ink x range, kern pairs. */
    var FM = core.unitMetrics();
    var bez = core.bez4;
    /* The style's fitted curves (tokens.css), as control points. */
    var CURVE = core.CURVE;
    function curve(c) { var e = typeof c === "string" ? (CURVE[c] || CURVE.snap) : (c || CURVE.snap); return bez(e[0], e[1], e[2], e[3]); }
    /* The film updates its picture 16 times a second inside 24 fps: frame f with
       f mod 3 == 2 repeats f - 1. "twos" holds every second frame, "none" runs
       on ones. phase shifts which frame repeats. Returns the time whose state
       the frame at time t shows. */
    function shown(t, cad, phase) {
      if (!cad || cad === "none") return t;
      var f = Math.floor(t * FPS + 1e-3), p = phase || 0, g = f;
      if (cad === "16" || cad === 16) { if (((f - p) % 3 + 3) % 3 === 2) g = f - 1; }
      else if (cad === "twos" || cad === 12) { if (((f - p) % 2 + 2) % 2 === 1) g = f - 1; }
      return g / FPS;
    }
    /* A seek-safe ease that follows a fitted curve but only changes on the
       cadence's picture updates, aligned to absolute timeline frames. */
    function stepped(c, t0, dur, cad, phase) {
      var f = curve(c);
      if (!cad || cad === "none" || !(dur > 0)) return f;
      return function (p) {
        if (p >= 1) return 1;
        var t = shown(t0 + p * dur + 1e-6, cad, phase), q = (t - t0) / dur;
        return f(q < 0 ? 0 : q > 1 ? 1 : q);
      };
    }
    /* Snap a time to the nearest frame on which the cadence shows a new picture. */
    function snap(t, cad, phase) {
      var f = Math.round(t * FPS);
      if (cad === "16" || cad === 16) { while (((f - (phase || 0)) % 3 + 3) % 3 === 2) f++; }
      else if (cad === "twos" || cad === 12) { if (((f - (phase || 0)) % 2 + 2) % 2 === 1) f++; }
      return f / FPS;
    }
    /* Pure text measure from the font's own metrics: no layout read, so any word
       at any size is known before paint. Returns advance, ink left and right
       (px from the pen start) and cap height. */
    function measure(text, size, track) {
      var s = size / 1000, x = 0, inkL = null, inkR = 0, tr = (track || 0) * 1000, ch, i, a, k;
      for (i = 0; i < text.length; i++) {
        ch = text.charAt(i); a = FM.adv[ch]; if (a == null) a = FM.adv["n"];
        k = i > 0 ? (FM.kern[text.charAt(i - 1) + ch] || 0) : 0; x += k;
        var ink = FM.ink[ch];
        if (ink) { if (inkL == null) inkL = x + ink[0]; inkR = x + ink[1]; }
        x += a + (i < text.length - 1 ? tr : 0);
      }
      return { adv: x * s, inkL: (inkL || 0) * s, inkR: inkR * s, inkW: (inkR - (inkL || 0)) * s, cap: 0.69 * size };
    }
    /* Font size whose ink spans w px, or whose cap height is c px. */
    function sizeForInk(text, w, track) { var m = measure(text, 1000, track); return 1000 * w / Math.max(1, m.inkW); }
    function sizeForCap(c) { return c / 0.69; }
    function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
    /* A token colour, falling back to a literal. */
    function col(v, fb) { if (!v) return fb; return v.charAt(0) === "-" ? "var(" + v + ", " + (fb || "#000") + ")" : v; }
    var uid = 0;
    function id(p) { uid += 1; return (p || "es") + uid; }
    /* An image slot: { src | frames: [src], fit: cover|contain|fill, focal: [x, y] in 0..1,
       box: [x, y, w, h] in frame px (default the frame) }. Returns a div holding one
       img per picture, positioned by object-fit and object-position. */
    function slot(sp, W, H, cls) {
      sp = sp || {};
      var b = sp.box || [0, 0, W, H], el = document.createElement("div");
      el.className = (cls || "") + " es-slot";
      el.style.cssText = "position:absolute;left:" + b[0] + "px;top:" + b[1] + "px;width:" + b[2] + "px;height:" + b[3] + "px;overflow:hidden;";
      var list = sp.frames || (sp.src ? [sp.src] : []), fo = sp.focal || [0.5, 0.5];
      if (!list.length) { el.style.background = sp.color || "repeating-linear-gradient(45deg,#cfcfcf 0 22px,#d9d9d9 22px 44px)"; el.setAttribute("data-slot-empty", sp.name || "image"); }
      for (var i = 0; i < list.length; i++) {
        var im = document.createElement("img");
        im.src = typeof list[i] === "string" ? list[i] : list[i].src; im.alt = "";
        im.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;display:block;max-width:none;object-fit:" + (sp.fit || "cover") +
          ";object-position:" + (fo[0] * 100) + "% " + (fo[1] * 100) + "%;" + (list.length > 1 ? "opacity:0;" : "");
        el.appendChild(im);
      }
      return el;
    }
    /* Play a frame-sequence slot from t0, one picture per frame at fps; hold the last. */
    function playSlot(tl, el, t0, fps, hold) {
      var ims = el.querySelectorAll("img"), n = ims.length, fr = 1 / (fps || FPS), i;
      if (n < 2) return t0;
      for (i = 0; i < n; i++) {
        step(tl, ims[i], { opacity: 0 }, { opacity: 1 }, t0 + i * fr);
        if (i < n - 1 || hold === false) step(tl, ims[i], { opacity: 1 }, { opacity: 0 }, t0 + (i + 1) * fr);
      }
      return t0 + n * fr;
    }
    /* Hold-per-key state changes (measured per-frame keys): each key's values
       hold until the next. map(key) returns the tween vars for that key. */
    function keyed(tl, node, keys, t0, map, first) {
      var prev = null;
      for (var i = 0; i < keys.length; i++) {
        var to = map(keys[i]), from = prev || to, v = {};
        for (var k in to) v[k] = to[k];
        v.duration = EPS; v.ease = "none"; v.immediateRender = !!(first && i === 0);
        var at = t0 + keys[i].t - LEAD;
        if (at < 0) { from = to; at = 0; v.immediateRender = true; }
        tl.fromTo(node, from, v, at);
        prev = to;
      }
      return prev;
    }
    /* A one-frame change (show, hide, swap) on the cadence. */
    function step(tl, node, from, to, at) {
      var v = {}; for (var k in to) v[k] = to[k];
      v.duration = EPS; v.ease = "none"; v.immediateRender = false;
      if (at - LEAD < 0) { tl.fromTo(node, to, v, 0); return; }
      tl.fromTo(node, from, v, at - LEAD);
    }
    /* Beats: props.beats (seconds from t0) or n even beats over span. */
    function beats(props, n, span) {
      if (props.beats && props.beats.length) return props.beats.slice();
      var out = []; for (var i = 0; i < n; i++) out.push(span * (i + 1) / (n + 1)); return out;
    }
    /* A marquee selection state as SVG markup: { x0, y0, x1, y1, op } is the
       translucent fill, chips [[ax, ay, bx, by, o]] are square handles chip px
       wide, each streaked as the hull of its square at a (where the last
       picture left it) and at b (where it is now). */
    function hull2(ax, ay, bx, by, h) {
      var P = [[ax - h, ay - h], [ax + h, ay - h], [ax + h, ay + h], [ax - h, ay + h], [bx - h, by - h], [bx + h, by - h], [bx + h, by + h], [bx - h, by + h]];
      P.sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
      function cr(o, a, b) { return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]); }
      var lo = [], up = [], i;
      for (i = 0; i < P.length; i++) { while (lo.length >= 2 && cr(lo[lo.length - 2], lo[lo.length - 1], P[i]) <= 0) lo.pop(); lo.push(P[i]); }
      for (i = P.length - 1; i >= 0; i--) { while (up.length >= 2 && cr(up[up.length - 2], up[up.length - 1], P[i]) <= 0) up.pop(); up.push(P[i]); }
      return lo.slice(0, -1).concat(up.slice(0, -1)).map(function (q) { return q[0].toFixed(1) + "," + q[1].toFixed(1); }).join(" ");
    }
    function sel(st, chip, color) {
      var c = color || "#fff", h = (chip || 24) / 2, s = "";
      if (st.op) s += '<rect x="' + Math.min(st.x0, st.x1) + '" y="' + Math.min(st.y0, st.y1) + '" width="' + Math.abs(st.x1 - st.x0) + '" height="' + Math.abs(st.y1 - st.y0) + '" style="fill:' + c + '" fill-opacity="' + st.op + '"/>';
      var C = st.chips || [];
      for (var i = 0; i < C.length; i++) s += '<polygon points="' + hull2(C[i][0], C[i][1], C[i][2], C[i][3], h) + '" style="fill:' + c + '" fill-opacity="' + (C[i][4] == null ? 1 : C[i][4]) + '"/>';
      return s;
    }
    /* Start a measured key list part way in: times shift by -skip, and every key
       at or before the new zero collapses into one starting key (the last wins). */
    function shift(keys, skip) {
      if (!skip) return keys;
      var out = [], pre = null;
      for (var i = 0; i < keys.length; i++) {
        var k = {}, q; for (q in keys[i]) k[q] = keys[i][q]; k.t = keys[i].t - skip;
        if (k.t <= 1e-6) { pre = k; pre.t = 0; } else { if (pre) { out.push(pre); pre = null; } out.push(k); }
      }
      if (pre) out.push(pre);
      return out;
    }
    return { EPS: EPS, LEAD: LEAD, FPS: FPS, FM: FM, bez: bez, curve: curve, CURVE: CURVE, shown: shown, stepped: stepped, snap: snap,
      measure: measure, sizeForInk: sizeForInk, sizeForCap: sizeForCap, esc: esc, col: col, id: id, slot: slot, playSlot: playSlot,
      keyed: keyed, step: step, beats: beats, sel: sel, shift: shift };
  })();
