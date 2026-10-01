/* Motion expert scene runtime. Inlined (minified) into every board frame and
   every composition, so the board Umer approves and the render run the same
   code over the same plan.

   It never touches the clock and adds no callbacks: it builds tweens onto the
   paused timeline the page registers, and the canvas or the HyperFrames
   renderer seeks it. Element files register on window.__elements following
   ~/motion-ui/library/CONTRACT.md and read curves and the timing unit from
   here through window.__motionExpert at animate time. */
(function () {
  if (window.__motionExpert) return;

  /* Solve a CSS cubic-bezier so tokens.json curves run as written, without
     GSAP's CustomEase plugin. Pure and stateless. */
  function cubicBezier(x1, y1, x2, y2) {
    var cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
    var cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    return function (p) {
      if (p <= 0) return 0;
      if (p >= 1) return 1;
      var lo = 0, hi = 1, t = p, x, i;
      for (i = 0; i < 30; i++) {
        x = ((ax * t + bx) * t + cx) * t;
        if (Math.abs(x - p) < 1e-7) break;
        if (x < p) lo = t; else hi = t;
        t = (lo + hi) / 2;
      }
      return ((ay * t + by) * t + cy) * t;
    };
  }

  var M = {
    tokens: { timing: { unit_ms: 100 }, easings: {} },
    unit: 0.1,
    frame: { w: 1920, h: 1080 },
    reports: {},
    _ease: {}
  };

  M.init = function (tokens, frame) {
    if (tokens) M.tokens = tokens;
    M.unit = ((M.tokens.timing && M.tokens.timing.unit_ms) || 100) / 1000;
    if (frame) M.frame = frame;
  };

  /* A named easing from tokens.json as a GSAP ease function. A name the style
     does not define falls through to GSAP's own string eases. */
  M.ease = function (name) {
    if (typeof name !== "string") return name;
    if (M._ease[name]) return M._ease[name];
    var e = M.tokens.easings && M.tokens.easings[name];
    if (!e) return name;
    return (M._ease[name] = cubicBezier(e[0], e[1], e[2], e[3]));
  };

  /* Durations, staggers and holds are counted in the style's timing unit. */
  M.u = function (n) { return n * M.unit; };

  /* Travel written as a share of the frame: "0.2H" is 20% of the height,
     "-0.1W" a tenth of the width. Plain numbers are px. */
  M.len = function (v) {
    if (typeof v !== "string") return v;
    var m = /^(-?\d*\.?\d+)([HW])$/.exec(v.trim());
    if (!m) return v;
    return Number(m[1]) * (m[2] === "H" ? M.frame.h : M.frame.w);
  };
  function lenVars(obj) {
    var out = {}, k;
    for (k in obj) if (Object.prototype.hasOwnProperty.call(obj, k)) out[k] = (k === "x" || k === "y") ? M.len(obj[k]) : obj[k];
    return out;
  }
  function assign(a, b) { for (var k in b) if (Object.prototype.hasOwnProperty.call(b, k)) a[k] = b[k]; return a; }

  /* Build one scene onto the timeline. stage is the scene's .me-stage node,
     offset the scene's start on this timeline (0 on a board frame, the scene's
     start in the composition). Returns, and records for the review overlay,
     the span each move actually occupies on the timeline. */
  M.buildScene = function (stage, tl, offset, scene) {
    var registry = window.__elements || {};
    var nodes = {};
    var report = [];
    for (var i = 0; i < scene.moves.length; i++) {
      var m = scene.moves[i];
      var mod = registry[m.key];
      if (!mod) throw new Error("move '" + m.name + "' has no element registered as '" + m.key + "'");
      var props = assign({}, m.props || {});
      props.sceneStart = offset;
      props.sceneEnd = offset + scene.duration;
      props.sceneDuration = scene.duration;
      props.frame = M.frame;
      props.target = m.target;
      props.__move = { name: m.name, novel: m.novel, note: m.grammar_note || "" };

      var el = nodes[m.target];
      if (!el) {
        if (typeof mod.render !== "function") throw new Error("move '" + m.name + "' cannot create target '" + m.target + "': its element has no render()");
        el = mod.render(props);
        if (!el || el.nodeType !== 1) throw new Error("move '" + m.name + "' render() returned no node");
        el.id = scene.id + "-" + m.target;
        el.setAttribute("data-target", m.target);
        el.setAttribute("data-move", m.name);
        if (props.x !== undefined || props.y !== undefined) {
          el.style.position = "absolute";
          if (props.x !== undefined) el.style.left = (props.x * M.frame.w) + "px";
          if (props.y !== undefined) el.style.top = (props.y * M.frame.h) + "px";
        }
        stage.appendChild(el);
        nodes[m.target] = el;
      } else {
        el.setAttribute("data-move", el.getAttribute("data-move") + " " + m.name);
      }
      if (m.novel) el.setAttribute("data-novel", "true");

      var before = tl.getChildren(false, true, true);
      var t0 = offset + m.t;
      var settle = typeof mod.animate === "function" ? Number(mod.animate(tl, el, t0, props)) : t0;
      var after = tl.getChildren(false, true, true);
      var start = Infinity, end = -Infinity;
      for (var c = 0; c < after.length; c++) {
        if (before.indexOf(after[c]) >= 0) continue;
        start = Math.min(start, after[c].startTime());
        end = Math.max(end, after[c].endTime());
      }
      if (start === Infinity) { start = t0; end = isFinite(settle) ? settle : t0; }
      report.push({
        name: m.name, target: m.target, kind: m.kind, novel: !!m.novel,
        t: m.t, start: start - offset, end: end - offset,
        settle: isFinite(settle) ? settle - offset : null
      });
    }
    M.reports[scene.id] = report;
    return report;
  };

  /* Close the timeline. CONTRACT.md: a node rests in the state its first tween
     starts from, because HyperFrames renders across workers and a fromTo met
     on a rewind restores the node's recorded resting state rather than its
     from-values. So the earliest fromTo on each target and property writes its
     from-values inline here, for every element, without each file knowing.
     Then the timeline is held open to the full length so the canvas scrubber
     and the renderer both see the whole scene. */
  M.finish = function (tl, total) {
    var all = tl.getChildren(true, true, false);
    var ordered = all.slice().sort(function (a, b) { return a.startTime() - b.startTime(); });
    var seen = [];
    for (var r = 0; r < ordered.length; r++) {
      var tk = ordered[r];
      if (typeof tk.targets !== "function") continue;
      var from = tk.vars && tk.vars.startAt;
      if (!from) continue;
      var tg = tk.targets();
      for (var u = 0; u < tg.length; u++) {
        if (!tg[u] || tg[u].nodeType !== 1) continue;
        var init = {}, any = false;
        for (var key in from) {
          if (!Object.prototype.hasOwnProperty.call(from, key)) continue;
          if (key === "immediateRender" || key === "overwrite" || key === "lazy" || key === "data") continue;
          var alias = (key === "autoAlpha" || key === "visibility") ? "opacity" : key;
          var hit = false;
          for (var s = 0; s < seen.length; s++) if (seen[s][0] === tg[u] && seen[s][1] === alias) { hit = true; break; }
          if (hit) continue;
          seen.push([tg[u], alias]);
          init[key] = from[key];
          any = true;
        }
        if (any) gsap.set(tg[u], init);
      }
    }
    tl.to({ hold: 0 }, { hold: 1, duration: 0.0001 }, Math.max(0, total - 0.0001));
    return tl;
  };

  window.__elements = window.__elements || {};

  /* The grammar composer runs a novel move written as primitives rather than
     as an element file: props.tweens is a list of
       { from, to, ease, units, at, stagger, each }
     where ease names a tokens.json curve, units and at and stagger count in
     the timing unit, each is "self" or "words", and x and y accept frame
     shares ("0.2H"). validate-plan.mjs checks every tween against the style's
     envelopes. Text comes from props.text, split into words when
     props.split is "words"; props.className and props.style dress it. */
  window.__elements.__grammar = {
    render: function (props) {
      var el = document.createElement("div");
      el.className = "el-grammar" + (props.className ? " " + props.className : "");
      if (props.style) for (var k in props.style) if (Object.prototype.hasOwnProperty.call(props.style, k)) el.style[k] = props.style[k];
      var text = props.text == null ? "" : String(props.text);
      if (props.split === "words") {
        var parts = text.split(/\s+/);
        for (var i = 0; i < parts.length; i++) {
          if (!parts[i]) continue;
          var w = document.createElement("span");
          w.className = "w";
          w.textContent = parts[i];
          el.appendChild(w);
        }
      } else if (text) {
        el.textContent = text;
      }
      return el;
    },
    animate: function (tl, el, t0, props) {
      var tweens = props.tweens || [];
      var end = t0;
      for (var i = 0; i < tweens.length; i++) {
        var tw = tweens[i];
        var targets = tw.each === "words" ? el.querySelectorAll(".w") : el;
        var vars = assign(lenVars(tw.to || {}), {
          duration: M.u(tw.units || 1),
          ease: M.ease(tw.ease || "none")
        });
        if (tw.stagger) vars.stagger = M.u(tw.stagger);
        if (i > 0) vars.immediateRender = false;
        var at = t0 + M.u(tw.at || 0);
        tl.fromTo(targets, lenVars(tw.from || {}), vars, at);
        var n = tw.each === "words" ? Math.max(0, targets.length - 1) : 0;
        end = Math.max(end, at + vars.duration + n * (vars.stagger || 0));
      }
      return end;
    }
  };

  /* A novel move that has not been built. The board shows it honestly as a
     labelled box at its time; build-composition refuses a plan that has one. */
  window.__elements.__placeholder = {
    render: function (props) {
      var el = document.createElement("div");
      el.className = "el-placeholder";
      var a = document.createElement("div");
      a.className = "ph-name";
      a.textContent = "novel move, not built: " + props.__move.name;
      var b = document.createElement("div");
      b.className = "ph-note";
      b.textContent = props.__move.note;
      el.appendChild(a);
      el.appendChild(b);
      return el;
    },
    animate: function (tl, el, t0) {
      tl.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.2, ease: "none" }, t0);
      return t0 + 0.2;
    }
  };

  window.__motionExpert = M;
})();
