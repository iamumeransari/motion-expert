  /* select: the selection engine behind select-handles, used by every
     block that draws a selection (select-handles, genre-word-card and any
     block that wraps a target in handles). Needs R.shared and the toolkit's
     window.__motionExpert.

     Two ways to drive it.
     keys (general): a list of targets over time; each key's chips sit on the
       corners of its box and arrive from the previous box by a mode:
         pop      appear at once (optionally landing large and settling)
         glide    travel from the previous box on the snap ease, starting
                  lead seconds before t, drawn as a segmented streak
         jump     appear at once on the new box while the previous chips
                  linger (the grow-with-target nest)
         collapse travel inward to the box centre and vanish
       Every glide is sampled on the film's picture cadence, so it steps the
       way the source steps.
     frames (preset): measured rectangles per source frame,
       { "<f>": [[x0, y0, x1, y1, top, bottom], ...] }, f counted from t0,
       each frame stepped at t0 + (f - 0.5) / 24 as the replica does. */
  R.select = (function () {
    var SH = R.shared;
    function corners(b) { return [[b[0], b[1]], [b[2], b[1]], [b[0], b[3]], [b[2], b[3]]]; }
    function colorOf(key, spec, i) {
      var c = key.colors || key.color || spec.colors || spec.color || "type-light";
      c = Array.isArray(c) ? c[i % c.length] : c;
      return /gradient\(/.test(c) ? c : SH.color(c);
    }
    /* The streak: while a chip travels it is drawn as two pieces, each the
       sweep of the chip between two earlier sample times (in frames), with a
       gap between them, like a multi-sample shutter. Measured on frames 10
       and 12: a leading piece at the chip's position and a trailing smear
       reaching back about a frame. streak: false draws a plain square. */
    function piecesOf(spec) {
      if (spec.streak === false) return [[0, 0]];
      return (spec.streak && spec.streak.pieces) || [[0, 0.5], [0.75, 1.5]];
    }
    function chipPx(key, spec, props) { return (key.chip || spec.chip || 24 * SH.k(props)); }

    /* General: one node per key x corner x streak copy. */
    function buildKeys(layer, spec, props) {
      var keys = spec.keys || [], pieces = piecesOf(spec);
      for (var k = 0; k < keys.length; k++) {
        var mode = k === 0 ? (keys[k].mode === "glide" ? "pop" : (keys[k].mode || "pop")) : (keys[k].mode || "glide");
        var copies = (mode === "glide" || mode === "collapse") ? pieces.length : 1;
        var w = chipPx(keys[k], spec, props);
        for (var i = 0; i < 4; i++) for (var j = 0; j < copies; j++) {
          var c = document.createElement("div");
          c.className = "es-chip";
          c.setAttribute("data-key", k); c.setAttribute("data-corner", i); c.setAttribute("data-copy", j);
          var bg = colorOf(keys[k], spec, i);
          c.style.cssText = "position:absolute;left:0;top:0;opacity:0;width:" + w + "px;height:" + w + "px;background:" + bg + ";";
          layer.appendChild(c);
        }
      }
    }
    function animateKeys(tl, layer, t0, spec, props) {
      var M = window.__motionExpert, keys = spec.keys || [], pieces = piecesOf(spec), FR = SH.FR;
      var cad = spec.cadence || "16", ease = M.ease(spec.ease || "snap"), end = t0;
      var exitAt = props.exitAt != null ? t0 + props.exitAt : (spec.exitAt != null ? t0 + spec.exitAt : null);
      for (var k = 0; k < keys.length; k++) {
        var key = keys[k];
        var mode = k === 0 ? (key.mode === "glide" ? "pop" : (key.mode || "pop")) : (key.mode || "glide");
        var w = chipPx(key, spec, props), half = w / 2;
        var at = t0 + key.t;
        var dur = key.dur != null ? key.dur : 6 * FR;
        var lead = key.lead != null ? key.lead : FR;
        var nxt = keys[k + 1];
        var hide = nxt ? t0 + nxt.t - ((nxt.mode || "glide") === "glide" || nxt.mode === "collapse" ? (nxt.lead != null ? nxt.lead : FR) : 0) : exitAt;
        if (nxt && nxt.mode === "jump") hide = t0 + nxt.t + (nxt.linger != null ? nxt.linger : 3 * FR);
        var box = mode === "collapse" ? [(key.box[0] + key.box[2]) / 2, (key.box[1] + key.box[3]) / 2, (key.box[0] + key.box[2]) / 2, (key.box[1] + key.box[3]) / 2] : key.box;
        var tc = corners(box), pc = k > 0 ? corners(keys[k - 1].box) : tc;
        var chips = layer.querySelectorAll('.es-chip[data-key="' + k + '"]');
        var from = key.chip_from ? key.chip_from / w : 1;
        for (var n = 0; n < chips.length; n++) {
          var ch = chips[n], i = Number(ch.getAttribute("data-corner")), j = Number(ch.getAttribute("data-copy"));
          if (mode === "glide" || mode === "collapse") {
            var start = at - lead, pc0 = pc[i], tc0 = tc[i], pz = pieces[j];
            var tail = pieces[pieces.length - 1][1] * FR;
            var pos = function (u) { var e = ease(Math.max(0, Math.min(1, (u - start) / dur))); return [pc0[0] + (tc0[0] - pc0[0]) * e, pc0[1] + (tc0[1] - pc0[1]) * e]; };
            var pics = SH.pictures(start, start + dur + tail, cad);
            var prev = { opacity: 0, x: pc0[0] - half, y: pc0[1] - half, width: w, height: w, rotation: 0 };
            if (j === 0) { var on = { opacity: 1, x: prev.x, y: prev.y, width: w, height: w, rotation: 0 }; SH.step(tl, ch, prev, on, start, false); prev = on; }
            for (var q = 0; q < pics.length; q++) {
              /* each piece is the chip swept between two sample times: a
                 rectangle as long as the sweep plus a chip, one chip wide,
                 turned along the path, so a diagonal glide reads as a streak */
              var a = pos(pics[q] - pz[0] * FR), b = pos(pics[q] - pz[1] * FR);
              var dx = a[0] - b[0], dy = a[1] - b[1], len = Math.sqrt(dx * dx + dy * dy);
              var ux = len ? dx / len : 1, uy = len ? dy / len : 0, mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2, L = len + w;
              if (j > 0 && len >= 1) { mx -= ux; my -= uy; L -= 2; }
              var rot = len >= 1 ? Math.round(Math.atan2(uy, ux) * 180 / Math.PI * 100) / 100 : 0;
              if (Math.abs(Math.abs(rot) - 180) < 0.01) rot = 0;
              var cur = { opacity: (j === 0 || len >= 1) ? 1 : 0, x: mx - L / 2, y: my - w / 2, width: L, height: w, rotation: rot };
              if (q === pics.length - 1 && j > 0) cur.opacity = 0;
              var same = cur.opacity === prev.opacity && Math.abs(cur.x - prev.x) < 0.01 && Math.abs(cur.y - prev.y) < 0.01 && Math.abs(cur.width - prev.width) < 0.01 && Math.abs(cur.height - prev.height) < 0.01 && cur.rotation === prev.rotation;
              if (same) continue;
              SH.step(tl, ch, prev, cur, pics[q], false); prev = cur;
            }
            var gone = mode === "collapse" ? start + dur + (key.hold != null ? key.hold : 2 * FR) : hide;
            if (j === 0 && gone != null) SH.step(tl, ch, { opacity: 1 }, { opacity: 0 }, gone, false);
            end = Math.max(end, start + dur);
          } else {
            var tx = tc[i][0] - half, ty = tc[i][1] - half;
            SH.step(tl, ch, { opacity: 0, x: tx, y: ty, scale: from }, { opacity: 1, x: tx, y: ty, scale: from }, at, false);
            if (from !== 1) {
              var sp = SH.pictures(at, at + (key.settle != null ? key.settle : 3 * FR), cad), ps = from;
              for (var r = 1; r < sp.length; r++) {
                var s = from + (1 - from) * ease((sp[r] - at) / (sp[sp.length - 1] - at));
                SH.step(tl, ch, { scale: ps }, { scale: s }, sp[r], false); ps = s;
              }
            }
            if (hide != null) SH.step(tl, ch, { opacity: 1 }, { opacity: 0 }, hide, false);
            end = Math.max(end, at + FR);
          }
        }
      }
      return end;
    }

    /* Preset: measured rectangles per frame, pooled nodes. */
    function rectState(r) {
      if (!r) return { opacity: 0 };
      return { opacity: 1, left: r[0], top: r[1], width: r[2] - r[0], height: r[3] - r[1],
               backgroundImage: "linear-gradient(" + r[4] + "," + (r[5] || r[4]) + ")" };
    }
    function buildFrames(layer, spec) {
      var fr = spec.frames || {}, n = 0;
      for (var f in fr) n = Math.max(n, fr[f].length);
      var first = fr["0"] || [];
      for (var i = 0; i < n; i++) {
        var d = document.createElement("div"); d.className = "es-chip es-chip-r";
        var st = rectState(first[i]);
        d.style.cssText = "position:absolute;left:" + (st.left || 0) + "px;top:" + (st.top || 0) + "px;width:" + (st.width || 24) + "px;height:" + (st.height || 24) + "px;opacity:" + st.opacity + ";" + (st.backgroundImage ? "background-image:" + st.backgroundImage + ";" : "");
        layer.appendChild(d);
      }
    }
    function animateFrames(tl, layer, t0, spec, sc) {
      var fr = spec.frames || {}, nodes = layer.querySelectorAll(".es-chip-r"), last = 0, FR = SH.FR;
      sc = sc || 1;
      for (var f in fr) last = Math.max(last, Number(f));
      var endF = spec.f1 != null ? spec.f1 : last + 1;
      for (var i = 0; i < nodes.length; i++) {
        var prev = rectState((fr["0"] || [])[i]);
        for (var f2 = 1; f2 <= endF; f2++) {
          var cur = rectState((fr[String(f2)] || [])[i]);
          if (JSON.stringify(cur) === JSON.stringify(prev)) continue;
          var a = {}, b = {};
          if (cur.opacity) { for (var p in cur) { b[p] = cur[p]; a[p] = prev.opacity ? prev[p] : cur[p]; } a.opacity = prev.opacity; }
          else { a.opacity = prev.opacity; b.opacity = 0; }
          SH.step(tl, nodes[i], a, b, t0 + (f2 - 0.5) * FR, false);
          prev = cur;
        }
      }
      return t0 + endF * FR;
    }

    /* Box helpers so any block can wrap a target: chip centres sit pad px
       outside a target rectangle [x, y, w, h]. pad is a number or [px, py]. */
    function around(rect, pad) {
      var px = Array.isArray(pad) ? pad[0] : (pad || 0), py = Array.isArray(pad) ? pad[1] : (pad || 0);
      return [rect[0] - px, rect[1] - py, rect[0] + rect[2] + px, rect[1] + rect[3] + py];
    }

    return {
      build: function (layer, spec, props) { if (spec.frames) buildFrames(layer, spec); else buildKeys(layer, spec, props); },
      animate: function (tl, layer, t0, spec, props) { return spec.frames ? animateFrames(tl, layer, t0, spec) : animateKeys(tl, layer, t0, spec, props); },
      around: around
    };
  })();
