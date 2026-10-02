  /* cursor: the film's pointer for any block that draws one (cursor,
     marquee-select, type-behind-subject). Was es-cursor v1. Geometry is the s4 fit (cursor-shape.json):
     a kite with its tip at the origin and its bisector along +x, corners
     rounded (r1 at tip and wings, r2 at the notch), a white keyline sw wide
     outside a translucent grey body that darkens what is under it. */
  R.cursor = (function () {
    var SHAPE = { L: 178.908, half: 22.722, k: 0.70863, r1: 14.093, r2: 11.633, sw: 3.482 };
    var FILL = "rgba(60,62,58,0.31)", STROKE = "rgb(235,235,235)";
    function rounded(P, R, n) {
      var out = [], N = P.length, i, k;
      for (i = 0; i < N; i++) {
        var p0 = P[(i + N - 1) % N], p1 = P[i], p2 = P[(i + 1) % N], r = R[i];
        var ux = p0[0] - p1[0], uy = p0[1] - p1[1], ul = Math.hypot(ux, uy); ux /= ul; uy /= ul;
        var vx = p2[0] - p1[0], vy = p2[1] - p1[1], vl = Math.hypot(vx, vy); vx /= vl; vy /= vl;
        var ang = Math.acos(Math.max(-1, Math.min(1, ux * vx + uy * vy))), t = r / Math.tan(ang / 2);
        var ax = p1[0] + ux * t, ay = p1[1] + uy * t, bx = p1[0] + vx * t, by = p1[1] + vy * t;
        var sx = ux + vx, sy = uy + vy, sl = Math.hypot(sx, sy); sx /= sl; sy /= sl;
        var cx = p1[0] + sx * r / Math.sin(ang / 2), cy = p1[1] + sy * r / Math.sin(ang / 2);
        var a0 = Math.atan2(ay - cy, ax - cx), a1 = Math.atan2(by - cy, bx - cx), d = a1 - a0;
        while (d > Math.PI) d -= 2 * Math.PI; while (d < -Math.PI) d += 2 * Math.PI;
        for (k = 0; k <= n; k++) { var th = a0 + d * k / n; out.push([cx + r * Math.cos(th), cy + r * Math.sin(th)]); }
      }
      return out;
    }
    function offset(P, d) {
      var N = P.length, area = 0, i, L = [], out = [];
      for (i = 0; i < N; i++) { var q = P[(i + N - 1) % N]; area += 0.5 * (q[0] * P[i][1] - P[i][0] * q[1]); }
      var sg = area > 0 ? 1 : -1;
      for (i = 0; i < N; i++) {
        var a = P[i], b = P[(i + 1) % N], tx = b[0] - a[0], ty = b[1] - a[1], tl = Math.hypot(tx, ty); tx /= tl; ty /= tl;
        L.push([a[0] + ty * sg * d, a[1] - tx * sg * d, tx, ty]);
      }
      for (i = 0; i < N; i++) {
        var l1 = L[(i + N - 1) % N], l2 = L[i], det = l1[2] * (-l2[3]) - (-l2[2]) * l1[3];
        var rx = l2[0] - l1[0], ry = l2[1] - l1[1], s = (rx * (-l2[3]) - (-l2[2]) * ry) / det;
        out.push([l1[0] + l1[2] * s, l1[1] + l1[3] * s]);
      }
      return out;
    }
    function polyArea(P) { var a = 0, N = P.length; for (var i = 0; i < N; i++) { var q = P[(i + N - 1) % N]; a += 0.5 * (q[0] * P[i][1] - P[i][0] * q[1]); } return Math.abs(a); }
    function paths(sh) {
      sh = sh || SHAPE;
      var h = sh.half * Math.PI / 180, L = sh.L;
      var P = [[0, 0], [L * Math.cos(h), -L * Math.sin(h)], [sh.k * L, 0], [L * Math.cos(h), L * Math.sin(h)]];
      var inner = rounded(P, [sh.r1, sh.r1, sh.r2, sh.r1], 12);
      var op = offset(P, sh.sw); if (polyArea(op) < polyArea(P)) op = offset(P, -sh.sw);
      var outer = rounded(op, [sh.r1 + sh.sw, sh.r1 + sh.sw, Math.max(0.5, sh.r2 - sh.sw), sh.r1 + sh.sw], 12);
      return { inner: inner, outer: outer };
    }
    function d(P) { var s = "M"; for (var i = 0; i < P.length; i++) s += (i ? " L" : "") + P[i][0].toFixed(2) + " " + P[i][1].toFixed(2); return s + "Z"; }
    /* The pointer node: a zero-size div whose origin is the tip. */
    function node(opts) {
      opts = opts || {};
      var p = paths(opts.shape), el = document.createElement("div");
      el.className = "es-cursor";
      el.style.cssText = "position:absolute;left:0;top:0;width:1px;height:1px;opacity:0;transform-origin:0 0;pointer-events:none;";
      el.innerHTML = '<svg width="1" height="1" style="position:absolute;left:0;top:0;overflow:visible;display:block">' +
        '<path fill="' + (opts.stroke || STROKE) + '" fill-rule="evenodd" d="' + d(p.outer) + " " + d(p.inner.slice().reverse()) + '"/>' +
        '<path fill="' + (opts.fill || FILL) + '" d="' + d(p.inner) + '"/></svg>';
      return el;
    }
    /* Measured per-frame keys [{ t, x, y, th, s, o }]: tip position, rotation in
       degrees, scale (a click squash is s 0.85 on one picture), opacity. */
    function keys(tl, el, K, t0, size) {
      var z = size || 1, kit = R.kit;
      kit.keyed(tl, el, K, t0, function (k) {
        return { x: k.x, y: k.y, rotation: k.th == null ? 36 : k.th, scale: (k.s == null ? 1 : k.s) * z, opacity: k.o == null ? 1 : k.o, transformOrigin: "0px 0px" };
      }, true);
    }
    /* General mode: stops [{ x, y, at, click, th, hop }] in px, at = arrival in
       seconds from t0. Each hop leaves the last stop hop seconds before arrival
       (default 4 frames plus 6 per frame height travelled, as the film's hops
       run 4 to 10 frames) on the snap curve, stepped on the cadence. Rotation
       rests at 36 degrees and leans up to +24 travelling left and -20 right; a
       click squashes to 0.85 for clickFrames (2) frames on arrival. Returns the
       last time anything changes. */
    function travel(tl, el, stops, t0, o) {
      o = o || {};
      var kit = R.kit, cad = o.cadence || "16", z = o.size || 1, H = o.H || 1080, rest = o.rest == null ? 36 : o.rest;
      var prev = null, end = t0;
      for (var i = 0; i < stops.length; i++) {
        var s = stops[i], at = t0 + (s.at || 0), th = s.th == null ? rest : s.th;
        if (!prev) {
          kit.keyed(tl, el, [{ t: 0 }], at, function () { return { x: s.x, y: s.y, rotation: th, scale: z, opacity: 1, transformOrigin: "0px 0px" }; }, true);
        } else {
          var dx = s.x - prev.x, dist = Math.hypot(dx, s.y - prev.y);
          var hop = s.hop || (4 + 6 * dist / H) / 24, dep = Math.max(prev.at, at - hop), dur = Math.max(1 / 24, at - dep);
          if (s.th == null) th = rest + Math.max(-20, Math.min(24, -40 * dx / H));
          tl.fromTo(el, { x: prev.x, y: prev.y, rotation: prev.th }, { x: s.x, y: s.y, rotation: th, duration: dur, ease: kit.stepped(s.curve || o.curve || "snap", dep, dur, cad), immediateRender: false }, dep);
          end = Math.max(end, dep + dur);
        }
        if (s.click) {
          var c = kit.snap(at, cad), hold = (s.clickFrames || 2) / 24;
          kit.step(tl, el, { scale: z }, { scale: 0.85 * z }, c);
          kit.step(tl, el, { scale: 0.85 * z }, { scale: z }, c + hold);
          end = Math.max(end, c + hold);
        }
        prev = { x: s.x, y: s.y, th: th, at: at };
      }
      if (o.exitAt != null) kit.step(tl, el, { opacity: 1 }, { opacity: 0 }, t0 + o.exitAt);
      return end;
    }
    return { SHAPE: SHAPE, FILL: FILL, STROKE: STROKE, paths: paths, node: node, keys: keys, travel: travel };
  })();
