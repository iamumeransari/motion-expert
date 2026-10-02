  /* camera: the film's camera moves as presets for any image slot or
     container (camera-rig, billboard, crop-select and any block that moves a
     picture). Was es-camera v1.

     A move is a scale about an origin plus a travel and a roll, run on one of
     the film's cadences. Scale interpolates in log space, which is how every
     preset below was fitted, so a pull from 1 to 0.4 reads as an even camera
     move rather than a slowing one. Every preset is measured from the source:
       push         film 822 to 834 (shots 34 and 35, the lying model), the push
                    with its cut punch removed: x1.100 over 12 frames, fitted
                    bezier 0.587 -0.033 0.263 1.135 (rms 0.026), 16 fps cadence
       punch        the punch-in on the cut at film 828: x1.097 in one frame
       push-soft    fingerprint move 52 (film 600 on): x1.34 over 13 frames, push curve
       push-hard    fingerprint move 48 (film 522 on): x1.47 over 13 frames, push-hard curve
       pull-back    s7 shot I (film 958 to 992), tracked board plane: x0.407 over
                    35 frames, log-scale bezier 0.473 0.464 0.332 0.974 (rms 0.003),
                    centre travel -33, +26 px, on ones (real footage)
       pull-steady  s7 shots B to H, the median steady pull: -1.99 percent per
                    frame (range -0.92 to -2.39), linear, on ones
       pull-settle  fingerprint move 67 (shot 38): x0.82 over 13 frames, settle curve
       drift        fingerprint move 29 (shot 14 studio drift): 0.035 W by 0.025 H
                    over 20 frames, drift curve, on ones
       tilt         fingerprint move 66 (shot 37): -0.06 H over 13 frames,
                    bezier 1.0 0.937 0.874 0.965, on ones
       hold         no motion
     cam = { preset, at (s after t0), dur (s) or frames, scale (duration
             multiplier), from, to (scale), dx, dy (px at 1920, or "0.05W",
             "-0.03H"), r (deg), origin [fx, fy] (0..1 of the node box),
             ease (token name or bezier), cadence "16" | "twos" | "ones",
             phase (which frame of three repeats, default 2),
             keys: [[frame, s, x, y, r], ...] exact per-frame states, or
             mats: [[frame, m0..m8], ...] exact per-frame homographies (row
             major, frame px), both stepped on their frames }
     or an array of such moves, each starting from where the last one ended. */
  R.camera = (function () {
    var FPS = 24, EPS = 0.0001;
    var CURVE = core.CURVE;
    var PRESETS = {
      push: { to: 1.100, frames: 12, ease: "film-push", cadence: "16" },
      punch: { to: 1.097, frames: 0, cadence: "16" },
      "push-soft": { to: 1.34, frames: 13, ease: "push", cadence: "16" },
      "push-hard": { to: 1.47, frames: 13, ease: "push-hard", cadence: "16" },
      "pull-back": { to: 0.407, frames: 35, ease: "film-pull", cadence: "ones", dx: -33, dy: 26 },
      "pull-steady": { rate: -0.0199, frames: 16, ease: "linear", cadence: "ones" },
      "pull-settle": { to: 0.82, frames: 13, ease: "settle", cadence: "ones" },
      drift: { dx: "0.035W", dy: "0.025H", frames: 20, ease: "drift", cadence: "ones" },
      tilt: { dy: "-0.06H", frames: 13, ease: "film-tilt", cadence: "ones" },
      hold: { frames: 0 }
    };
    function bez(e) { return core.bez4(e[0], e[1], e[2], e[3]); }
    function curve(c) { return bez(typeof c === "string" ? (CURVE[c] || CURVE.linear) : (c || CURVE.linear)); }
    function fsz(props) { var f = (props && props.frame) || {}; return { w: f.w || 1920, h: f.h || 1080 }; }
    function len(v, props, axis) {
      if (v == null) return 0;
      var F = fsz(props);
      if (typeof v === "string") { var m = /^(-?\d*\.?\d+)([HW])$/.exec(v.trim()); if (m) return Number(m[1]) * (m[2] === "H" ? F.h : F.w); return Number(v) || 0; }
      return v * F.w / 1920;
    }
    /* The time of the picture a frame shows: on the 16 fps cadence frame f with
       (f - phase + 2) mod 3 == 2 repeats f - 1 (phase 2 is the film's own). */
    function shown(t, cad, phase) {
      if (!cad || cad === "ones") return t;
      var f = Math.floor(t * FPS + 1e-4), g = f, p = phase == null ? 2 : phase;
      if (cad === "16" || cad === 16) { if ((((f - p) % 3) + 3) % 3 === 0) g = f - 1; }
      else if (cad === "twos" || cad === 12) { if ((((f - (p % 2)) % 2) + 2) % 2 === 1) g = f - 1; }
      return g / FPS;
    }
    /* Resolve one move into numbers: start time, duration, the scale ratio,
       travel and roll, the curve, cadence and origin. */
    function resolve(c, props) {
      var P = PRESETS[c.preset || "hold"] || PRESETS.hold, k = c.scale || 1;
      var frames = c.frames != null ? c.frames : (c.dur != null ? c.dur * FPS : P.frames * k);
      var dur = Math.max(0, frames / FPS);
      var ratio;
      if (c.to != null && c.from != null) ratio = c.to / c.from;
      else if (c.to != null) ratio = c.to;
      else if (P.rate != null) ratio = Math.exp(P.rate * frames);
      else ratio = P.to != null ? P.to : 1;
      return { at: c.at || 0, dur: dur, from: c.from != null ? c.from : 1, ratio: ratio,
        dx: len(c.dx != null ? c.dx : P.dx, props), dy: len(c.dy != null ? c.dy : P.dy, props),
        r: c.r != null ? c.r : (P.r || 0), ease: curve(c.ease || P.ease || "linear"),
        cadence: c.cadence || P.cadence || "16", phase: c.phase, origin: c.origin || [0.5, 0.5] };
    }
    function list(cam) { return !cam ? [] : (Array.isArray(cam) ? cam : [cam]); }
    /* The state at t seconds after t0, pure, for anything that must follow the
       camera (an overlay, a label) without being inside the moved node. */
    function sample(cam, t, props) {
      var st = { s: 1, x: 0, y: 0, r: 0 }, L = list(cam);
      for (var i = 0; i < L.length; i++) {
        var c = L[i];
        if (c.keys) { var kk = null; for (var j = 0; j < c.keys.length; j++) if (c.keys[j][0] / FPS <= t + 1e-6) kk = c.keys[j]; if (kk) st = { s: kk[1], x: kk[2], y: kk[3], r: kk[4] || 0 }; continue; }
        var m = resolve(c, props); if (i === 0 && c.from != null) st.s = m.from;
        var q = m.dur > 0 ? (shown(t, m.cadence, m.phase) - m.at) / m.dur : (t >= m.at ? 1 : 0);
        var e = m.ease(q < 0 ? 0 : q > 1 ? 1 : q);
        if (t < m.at) break;
        st = { s: st.s * Math.pow(m.ratio, e), x: st.x + m.dx * e, y: st.y + m.dy * e, r: st.r + m.r * e };
        if (q < 1) break;
      }
      return st;
    }
    /* A GSAP ease that holds pictures on the cadence and maps progress so a
       linear tween from a to b lands on the curve (log space for scale). */
    function stepper(m, t0, map) {
      return function (p) {
        if (p >= 1) return 1; if (p <= 0) return 0;
        var t = t0 + m.at + p * m.dur, q = (shown(t + 1e-6, m.cadence, m.phase) - t0 - m.at) / m.dur;
        return map(m.ease(q < 0 ? 0 : q > 1 ? 1 : q));
      };
    }
    /* Tween node (a picture or a container) through the move(s). Returns the
       time the camera settles. box = { w, h } of the node, for the origin. */
    function apply(tl, node, t0, cam, props) {
      var L = list(cam), st = { s: 1, x: 0, y: 0, r: 0 }, end = t0, first = true;
      if (!L.length) return t0;
      if (L[0].origin) node.style.transformOrigin = (L[0].origin[0] * 100) + "% " + (L[0].origin[1] * 100) + "%";
      for (var i = 0; i < L.length; i++) {
        var c = L[i];
        if (c.mats) { applyMats(tl, node, t0, c.mats); end = Math.max(end, t0 + c.mats[c.mats.length - 1][0] / FPS); first = false; continue; }
        if (c.keys) {
          for (var j = 0; j < c.keys.length; j++) {
            var kk = c.keys[j], f = kk[0], to = { s: kk[1], x: kk[2], y: kk[3], r: kk[4] || 0 };
            var t = f <= 0 ? t0 : t0 + (f - 0.25) / FPS;
            var v = { scale: to.s, x: to.x, y: to.y, rotation: to.r, duration: EPS, ease: "none" };
            if (!first) v.immediateRender = false;
            tl.fromTo(node, { scale: st.s, x: st.x, y: st.y, rotation: st.r }, v, t);
            st = to; first = false; end = Math.max(end, t);
          }
          continue;
        }
        var m = resolve(c, props);
        if (i === 0 && c.from != null) st.s = m.from;
        var nx = { s: st.s * m.ratio, x: st.x + m.dx, y: st.y + m.dy, r: st.r + m.r };
        var a = st.s, b = nx.s, lr = Math.log(m.ratio);
        var scaleMap = function (a, b, lr) { return function (e) { return Math.abs(b - a) < 1e-9 ? e : (a * Math.exp(lr * e) - a) / (b - a); }; }(a, b, lr);
        var lin = function (e) { return e; };
        var t1 = t0 + m.at;
        if (m.dur <= 0) {
          var v0 = { scale: nx.s, x: nx.x, y: nx.y, rotation: nx.r, duration: EPS, ease: "none" };
          if (!first) v0.immediateRender = false;
          tl.fromTo(node, { scale: st.s, x: st.x, y: st.y, rotation: st.r }, v0, t1);
        } else {
          var vs = { scale: nx.s, duration: m.dur, ease: stepper(m, t0, scaleMap) };
          var vt = { x: nx.x, y: nx.y, rotation: nx.r, duration: m.dur, ease: stepper(m, t0, lin) };
          if (!first) { vs.immediateRender = false; vt.immediateRender = false; }
          tl.fromTo(node, { scale: st.s }, vs, t1);
          tl.fromTo(node, { x: st.x, y: st.y, rotation: st.r }, vt, t1);
        }
        st = nx; first = false; end = Math.max(end, t1 + m.dur);
      }
      return end;
    }
    /* Exact per-frame homographies (row-major 3x3 in frame px), written as CSS
       variables under a matrix3d so GSAP never decomposes them. */
    function matVars(m) {
      return { "--c0": m[0], "--c1": m[3], "--c3": m[6] * 1e6, "--c4": m[1], "--c5": m[4], "--c7": m[7] * 1e6, "--c12": m[2], "--c13": m[5], "--c15": m[8] };
    }
    function matStyle(node, m) {
      node.style.transformOrigin = "0 0";
      node.style.transform = "matrix3d(var(--c0), var(--c1), 0, calc(var(--c3) / 1000000), var(--c4), var(--c5), 0, calc(var(--c7) / 1000000), 0, 0, 1, 0, var(--c12), var(--c13), 0, var(--c15))";
      var v = matVars(m); for (var k in v) node.style.setProperty(k, v[k]);
    }
    function applyMats(tl, node, t0, mats) {
      matStyle(node, mats[0][1]);
      for (var j = 1; j < mats.length; j++) {
        var f = mats[j][0], v = matVars(mats[j][1]); v.duration = EPS; v.ease = "none";
        if (j > 1) v.immediateRender = false;
        tl.fromTo(node, matVars(mats[j - 1][1]), v, t0 + (f - 0.25) / FPS);
      }
    }
    return { PRESETS: PRESETS, CURVE: CURVE, curve: curve, sample: sample, apply: apply, shown: shown, resolve: resolve, matStyle: matStyle, FPS: FPS };
  })();
