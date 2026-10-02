  /* shared: frame scale, the picture cadence as quantised times, zero-duration
     steps placed at their time, a seeded PRNG, glyph-metric text layout in em
     fractions, and the background-image slot. Was es-shared v1 (camera, select,
     crop, billboard, ghost, lockup, tile-scatter, genre-word-card). */
  R.shared = (function () {
    var METRICS = { serif: core.emMetrics() };

    /* Scale from the 1920x1080 source to this frame. The short side carries
       it, so a portrait or square frame keeps the source's type size. */
    function k(props) { var f = (props && props.frame) || { w: 1920, h: 1080 }; return Math.min(f.w, f.h) / 1080; }
    function fw(props) { return ((props && props.frame) || { w: 1920 }).w; }
    function fh(props) { return ((props && props.frame) || { h: 1080 }).h; }

    /* The film updates its picture 16 times a second inside 24 fps (frame f
       with f mod 3 = 2 repeats f - 1), and parts of it run on twos. quant(t)
       moves a time to the start of the picture it falls in, so any tween or
       step placed through it lands on a picture the film could show.
       cadence: "16" (default), "twos", "ones". */
    function quant(t, cadence, fps) {
      fps = fps || 24; var f = Math.round(t * fps * 1000) / 1000, fl = Math.floor(f + 1e-6);
      if (cadence === "ones") return fl / fps;
      if (cadence === "twos") return (fl - (fl % 2)) / fps;
      return (fl % 3 === 2 ? fl - 1 : fl) / fps;
    }
    /* Sample a tween as held pictures: returns the list of times at which the
       picture changes between t0 and t1 on the cadence. */
    function pictures(t0, t1, cadence, fps) {
      fps = fps || 24; var out = [], f0 = Math.ceil(t0 * fps - 1e-6), f1 = Math.floor(t1 * fps + 1e-6), last = null;
      for (var f = f0; f <= f1; f++) { var q = quant(f / fps, cadence, fps); if (q !== last && q >= t0 - 1e-6) { out.push(q); last = q; } }
      if (!out.length || out[out.length - 1] < t1 - 1e-6) out.push(t1);
      return out;
    }

    /* A zero-duration step, the film's way of changing a picture. Steps after
       the first on a node carry immediateRender false (CONTRACT.md). */
    function step(tl, node, from, to, t, first) {
      var v = {}; for (var p in to) v[p] = to[p];
      v.duration = 0.0001; v.ease = "none"; if (!first) v.immediateRender = false;
      tl.fromTo(node, from, v, Math.max(0, t));
    }

    function rng(seed) {
      var s = (seed >>> 0) || 1;
      return function () { s = (s + 0x6D2B79F5) >>> 0; var t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
    }

    /* Lay out a string in ES Serif from its glyph metrics: returns pen x per
       character (from the run's left edge, px), the advance width and the ink
       box, at a font size in px and tracking in em. Pure arithmetic, so it is
       right before the webfont arrives and render() never reads layout. */
    function layout(text, size, tracking, face) {
      var m = METRICS[face || "serif"], pens = [], x = 0, tr = (tracking || 0) * size;
      var inkL = Infinity, inkR = -Infinity;
      for (var i = 0; i < text.length; i++) {
        var ch = text[i], a = m.adv[ch] != null ? m.adv[ch] : 0.5;
        pens.push(x);
        var b = m.ink[ch];
        if (b) { inkL = Math.min(inkL, x + b[0] * size); inkR = Math.max(inkR, x + b[2] * size); }
        x += a * size;
        if (i + 1 < text.length) { x += tr; var kp = m.kern[ch + text[i + 1]]; if (kp) x += kp * size; }
      }
      if (inkL === Infinity) { inkL = 0; inkR = x; }
      return { pens: pens, width: x, inkL: inkL, inkR: inkR, ink: inkR - inkL, cap: m.cap * size, xh: m.x * size, size: size };
    }
    /* The font size whose cap height is cap px. */
    function sizeForCap(cap, face) { return cap / METRICS[face || "serif"].cap; }
    /* Where the baseline sits below the top of a line-height:1 box, as a
       share of the font size, so a glyph node can be placed by its baseline. */
    function baseFrac(face) { var m = METRICS[face || "serif"]; return (1 - (m.asc - m.desc)) / 2 + m.asc; }

    /* An image slot: a box that crops its picture by code. spec is
         { src, fit: "cover" | "contain", focal: [x, y] (0..1), zoom (1),
           cutout: src of the subject on transparency, label }
       or a string src. Without a src it draws a labelled placeholder, which is
       the code-and-slots view of the block. Returns the slot node; the picture
       is its first child (class es-pic) so a block can move it inside the box. */
    function slot(spec, w, h, name) {
      if (typeof spec === "string") spec = { src: spec };
      spec = spec || {};
      var box = document.createElement("div");
      box.className = "es-slot"; box.setAttribute("data-slot", name || "image");
      box.style.cssText = "position:absolute;overflow:hidden;width:" + w + "px;height:" + h + "px;";
      var fx = spec.focal ? spec.focal[0] : 0.5, fy = spec.focal ? spec.focal[1] : 0.5;
      if (spec.src) {
        var pic = document.createElement("div");
        pic.className = "es-pic";
        var z = spec.zoom || 1;
        pic.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;background-image:url(\"" + spec.src + "\");background-repeat:no-repeat;background-size:" +
          (spec.fit === "contain" ? "contain" : (z === 1 ? "cover" : (z * 100) + "% auto")) + ";background-position:" + (fx * 100) + "% " + (fy * 100) + "%;transform-origin:" + (fx * 100) + "% " + (fy * 100) + "%;";
        box.appendChild(pic);
      } else {
        box.style.background = "repeating-linear-gradient(45deg, var(--color-mist) 0 2px, var(--color-ghost) 2px 14px)";
        box.style.outline = "2px solid var(--color-ink-grey)"; box.style.outlineOffset = "-2px";
        var lab = document.createElement("div");
        lab.className = "es-slot-label"; lab.textContent = spec.label || name || "image";
        lab.style.cssText = "position:absolute;left:8px;top:6px;font:500 " + Math.max(10, Math.min(18, h / 8)) + "px/1 var(--font-mono);color:var(--color-ink-grey);white-space:nowrap;";
        box.appendChild(lab);
      }
      return box;
    }
    /* The cut-out layer for type-behind-subject: the same crop as slot(spec)
       but showing spec.cutout, to sit above the type. Null when there is none. */
    function cutout(spec, w, h, name) {
      if (!spec || typeof spec === "string" || !spec.cutout) return null;
      var c = {}; for (var p in spec) c[p] = spec[p]; c.src = spec.cutout;
      var n = slot(c, w, h, (name || "image") + "-cutout"); n.classList.add("es-cutout"); return n;
    }

    /* A token colour by name ("violet" -> var(--color-violet)); any other
       CSS colour passes through. */
    function color(c, dflt) { c = c || dflt; return /^[a-z-]+$/.test(c) && c !== "white" && c !== "black" && c !== "transparent" ? "var(--color-" + c + ")" : c; }

    return { METRICS: METRICS, k: k, fw: fw, fh: fh, quant: quant, pictures: pictures, step: step, rng: rng,
             layout: layout, sizeForCap: sizeForCap, baseFrac: baseFrac, slot: slot, cutout: cutout, color: color, FR: 1 / 24 };
  })();
