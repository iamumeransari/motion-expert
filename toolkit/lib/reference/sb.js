/* Reference-board frame runtime, copied into every board by
   toolkit/reference-board.py. Reads window.__beat, drives the beat's source clip
   from window.__storyboard so the canvas scrubber seeks it frame-accurately, and
   draws the review overlay in the toolkit/lib/overlay.css style: side panel
   (shots, moves, energy, feeling) and a timing ruler (source timecode, shots,
   hard cuts, soft transitions, the music beat grid, energy, moves, sound).
   Toggle with the pill or the O key; ?clean hides it. B shows the region boxes of
   moves whose box was verified against the picture (off by default), U shows the
   moves and sound markers that failed verification, hatched and labelled.
   While playing, the overlay follows the frame actually presented
   (requestVideoFrameCallback mediaTime), not currentTime, which runs ahead. */
(function () {
  var B = window.__beat;
  var FPS = B.fps, DUR = B.b - B.a;
  var clean = /[?&]clean\b/.test(location.search);
  var showBoxes = false, showUnverified = false;
  try { showBoxes = localStorage.getItem("me-review-boxes") === "on"; showUnverified = localStorage.getItem("me-review-unverified") === "on"; } catch (e) {}
  // unverified detections are not drawn unless asked for (U), and then hatched
  var MOVES = B.moves.filter(function (m) { return m.ok || showUnverified; });
  var SFX = B.sfx.filter(function (s) { return s.ok || showUnverified; });
  var video = document.getElementById("src");
  var frame = document.getElementById("frame");

  function h(tag, cls, text) { var el = document.createElement(tag); if (cls) el.className = cls; if (text != null) el.textContent = text; return el; }
  function pct(tSrc) { return Math.max(0, Math.min(100, ((tSrc - B.a) / DUR) * 100)) + "%"; }
  function tc(t) { var f = Math.round(t * FPS); var s = Math.floor(f / FPS); var ff = f - s * FPS; return s + ":" + (ff < 10 ? "0" : "") + ff; }
  function frames(d) { return Math.round(d * FPS) + "f"; }

  // ---- time source -------------------------------------------------------
  var last = 0, playing = false, shown = null;
  // the presented frame's own timestamp, so the overlay never leads the picture
  if (video.requestVideoFrameCallback) {
    var onFrame = function (now, meta) { shown = meta.mediaTime; video.requestVideoFrameCallback(onFrame); };
    video.requestVideoFrameCallback(onFrame);
  }
  function seek(s) {
    s = Math.max(0, Math.min(DUR, s));
    var f = Math.min(Math.round(DUR * FPS) - 1, Math.floor(s * FPS + 1e-6));
    last = s;
    try { video.currentTime = (f + 0.5) / FPS; } catch (e) {}
  }
  window.__storyboard = {
    duration: DUR,
    time: function () { return playing ? (shown != null ? shown : video.currentTime) : last; },
    seek: function (s) { seek(s); },
    play: function () { playing = true; var p = video.play(); if (p && p.catch) p.catch(function () {}); },
    pause: function () { playing = false; video.pause(); last = shown != null ? shown : video.currentTime; }
  };
  video.addEventListener("ended", function () { playing = false; last = DUR; });
  video.addEventListener("loadedmetadata", function () { seek(last); });
  var q = location.search.match(/[?&]t=([\d.]+)/);
  if (q) seek(parseFloat(q[1]));

  // ---- region boxes on the picture ---------------------------------------
  var regions = h("div", "sb-regions");
  document.querySelector(".sb-stage").appendChild(regions);
  var boxes = [];
  B.moves.forEach(function (m) {
    if (!m.box) return;  // a box is only drawn when the motion was found inside it
    var r = m.region, bx = h("div", "sb-box c-" + m.conf);
    bx.setAttribute("data-move", m.label);
    bx.style.left = (r.x * 100) + "%"; bx.style.top = (r.y * 100) + "%";
    bx.style.width = (r.w * 100) + "%"; bx.style.height = (r.h * 100) + "%";
    var lab = h("span", null, m.id + " " + m.prop + " · " + m.name);
    var k = 0; B.moves.forEach(function (o) { if (o.box && o !== m && B.moves.indexOf(o) < B.moves.indexOf(m) && o.t0 < m.t1 && m.t0 < o.t1) k++; });
    lab.style.top = (4 + k * 28) + "px"; lab.style.left = "4px";
    bx.appendChild(lab);
    regions.appendChild(bx);
    boxes.push([bx, m]);
  });

  if (clean) { document.body.classList.add("sb-clean"); regions.style.display = "none"; }

  // ---- side panel ---------------------------------------------------------
  var side = h("aside", "me-review sb-side");
  side.setAttribute("data-review-overlay", "panel");
  var top = h("div");
  top.appendChild(h("div", "sb-num", "BEAT " + B.n + " / " + B.total));
  top.appendChild(h("div", "sb-h1", B.title));
  side.appendChild(top);
  side.appendChild(h("div", "sb-meta", "src " + tc(B.a) + " to " + tc(B.b) + "  ·  " + frames(DUR) + "  ·  " + DUR.toFixed(2) + "s  ·  " +
    B.shots.length + " shots  ·  " + B.cuts.length + " cuts"));
  var en = h("div", "sb-energy");
  var chip = h("span", "sb-chip", B.energyLabel); chip.style.background = B.energyColor;
  en.appendChild(h("span", "mr-k", "energy")); en.appendChild(chip);
  en.appendChild(h("span", null, "mean " + B.energyMean.toFixed(3) + " of peak, " + B.energyRank));
  side.appendChild(en);
  var fl = h("div", "sb-feel"); fl.appendChild(h("span", "mr-k", "feeling"));
  fl.appendChild(document.createTextNode(B.feeling || "not written yet: this beat is one cluster of shots, and work/<slug>/beats.json names it"));
  if (!B.feeling) fl.style.opacity = "0.6";
  side.appendChild(fl);

  side.appendChild(h("div", "sb-sec", "shots (from a cut) and + phases inside a shot"));
  var shotList = h("ol");
  var shotEls = [];
  B.shots.forEach(function (s, i) {
    var li = h("li", s.cut ? "is-shot" : "is-phase"); li.setAttribute("data-shot", tc(s.a) + " " + s.tag);
    li.appendChild(h("span", "tc", (s.cut ? "" : "+ ") + tc(s.a) + " " + frames(s.b - s.a)));
    li.appendChild(document.createTextNode(s.text));
    shotList.appendChild(li); shotEls.push(li);
  });
  side.appendChild(shotList);

  var nOk = B.moves.filter(function (m) { return m.ok; }).length, nBad = B.moves.length - nOk;
  side.appendChild(h("div", "sb-sec", B.moves.length ? "moves checked against the picture: " + nOk + " verified" + (nBad ? ", " + nBad + (showUnverified ? " unverified shown hatched (U hides)" : " unverified hidden (U shows)") : "") : "moves: none tracked in this beat"));
  var moveList = h("ol");
  var moveEls = [];
  MOVES.forEach(function (m) {
    var li = h("li", m.ok ? null : "is-unverified"); li.setAttribute("data-move", m.label);
    if (!m.ok) li.title = "unverified: " + m.why;
    li.appendChild(h("span", "cf c-" + m.conf));
    li.appendChild(h("span", "tc", tc(m.t0) + " " + frames(m.t1 - m.t0)));
    li.appendChild(h("span", "mv", m.name + " "));
    li.appendChild(h("span", "cv", "(" + m.id + " " + m.prop + ", " + m.curve + (m.ok ? "" : ", unverified: " + m.why) + ")"));
    moveList.appendChild(li); moveEls.push(li);
  });
  side.appendChild(moveList);
  frame.appendChild(side);

  // fit the panel's text to its box
  function fit() {
    var fs = 18;
    side.style.fontSize = fs + "px";
    while (side.scrollHeight > side.clientHeight + 1 && fs > 10) { fs -= 0.5; side.style.fontSize = fs + "px"; }
  }

  // ---- ruler --------------------------------------------------------------
  var ruler = h("aside", "me-review sb-ruler");
  ruler.setAttribute("data-review-overlay", "ruler");
  var grid = h("div", "mr-grid");
  var rows = [];
  function lane(label, px) {
    var l = h("div", "mr-label"); l.appendChild(h("span", "mr-name", label));
    var t = h("div", "mr-track"); t.setAttribute("data-time-axis", "");
    grid.appendChild(l); grid.appendChild(t); rows.push(px + "px");
    return t;
  }

  var axis = lane("source tc", 22); axis.classList.add("mr-axis");
  var f0 = Math.ceil(B.a * FPS - 1e-6), f1 = Math.floor(B.b * FPS + 1e-6);
  var minorStep = DUR > 4 ? 6 : DUR > 1.6 ? 3 : 2;
  var majorStep = DUR > 4 ? 24 : 12;
  for (var f = f0; f <= f1; f++) {
    if (f % majorStep === 0) { var tk = h("span", "mr-tick major", tc(f / FPS)); tk.style.left = pct(f / FPS); axis.appendChild(tk); }
    else if (f % minorStep === 0) { var mn = h("span", "mr-tick minor"); mn.style.left = pct(f / FPS); axis.appendChild(mn); }
  }

  var shotLane = lane("shots · phases", 26);
  var shotBlocks = [];
  B.shots.forEach(function (s) {
    var el = h("span", "sb-shot" + (s.cut ? "" : " is-phase"), tc(s.a) + " " + s.tag);
    el.setAttribute("data-shot", tc(s.a) + " " + s.tag);
    el.style.left = pct(s.a); el.style.width = "calc(" + (((s.b - s.a) / DUR) * 100) + "% - 1px)";
    el.title = s.text;
    shotLane.appendChild(el); shotBlocks.push([el, s]);
  });

  var cutLane = lane("cuts · transitions", 24);
  B.holds.forEach(function (o) { var el = h("span", "sb-hold"); el.style.left = pct(o.t0); el.style.width = (((Math.min(o.t1, B.b) - Math.max(o.t0, B.a)) / DUR) * 100) + "%"; el.title = "hold"; cutLane.appendChild(el); });
  B.soft.forEach(function (o) {
    var el = h("span", "sb-soft", (o.note || o.kind) + " " + frames(o.t1 - o.t0) + (o.joins_cut != null ? " into the " + tc(o.joins_cut) + " cut" : ""));
    el.setAttribute("data-move", "transition " + o.kind + " " + tc(o.t0));
    el.style.left = pct(o.t0); el.style.width = (((Math.min(o.t1, B.b) - Math.max(o.t0, B.a)) / DUR) * 100) + "%";
    cutLane.appendChild(el);
  });
  B.cuts.forEach(function (t) { var el = h("span", "sb-cut"); el.setAttribute("data-move", "cut " + tc(t)); el.title = "hard cut " + tc(t); el.style.left = pct(t); cutLane.appendChild(el); });
  B.missed.forEach(function (o) { var el = h("span", "sb-cut missed"); el.setAttribute("data-move", "missed cut " + tc(o.t)); el.title = "cut not in fingerprint: " + o.why; el.style.left = pct(o.t); cutLane.appendChild(el); });

  var beatLane = lane(B.bpm ? Math.round(B.bpm) + " bpm" : "beats (no grid)", 20);
  B.beats.forEach(function (o) { var el = h("span", "mr-beat" + (o.down ? " is-down" : "")); el.style.left = pct(o.t); el.title = (o.down ? "downbeat " : "beat ") + tc(o.t); beatLane.appendChild(el); });

  var enLane = lane("energy", 30);
  var NS = "http://www.w3.org/2000/svg";
  var svg = document.createElementNS(NS, "svg"); svg.setAttribute("class", "sb-energy-svg"); svg.setAttribute("viewBox", "0 0 1000 100"); svg.setAttribute("preserveAspectRatio", "none");
  var d = "", pts = B.energy;
  pts.forEach(function (p, i) { var x = ((p.t - B.a) / DUR) * 1000, y = 100 - Math.min(1, p.v / B.energyScale) * 96; d += (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1); });
  if (pts.length) {
    var area = document.createElementNS(NS, "path"); area.setAttribute("d", d + "L" + (((pts[pts.length - 1].t - B.a) / DUR) * 1000).toFixed(1) + " 100L" + (((pts[0].t - B.a) / DUR) * 1000).toFixed(1) + " 100Z");
    area.setAttribute("fill", "rgba(255,209,102,0.25)"); svg.appendChild(area);
    var line = document.createElementNS(NS, "path"); line.setAttribute("d", d); line.setAttribute("fill", "none"); line.setAttribute("stroke", "#ffd166"); line.setAttribute("stroke-width", "2"); line.setAttribute("vector-effect", "non-scaling-stroke");
    svg.appendChild(line);
  }
  enLane.appendChild(svg);

  // pack moves into lanes
  var packed = [];
  MOVES.slice().sort(function (x, y) { return x.t0 - y.t0; }).forEach(function (m) {
    for (var i = 0; i < packed.length; i++) { if (packed[i].end <= m.t0 + 1e-3) { packed[i].items.push(m); packed[i].end = m.t1; return; } }
    packed.push({ end: m.t1, items: [m] });
  });
  var fixed = 22 + 26 + 24 + 20 + 30 + 34 + 6 * 3;
  var avail = 360 - 26 - 18 - fixed;
  var mh = packed.length ? Math.max(14, Math.min(24, Math.floor(avail / packed.length) - 3)) : 0;
  packed.forEach(function (p, i) {
    var tr = lane(i === 0 ? "moves" : "", mh);
    p.items.forEach(function (m) {
      var bar = h("span", "mr-bar c-" + m.conf + (m.ok ? "" : " is-unverified"));
      bar.setAttribute("data-move", m.label);
      bar.style.left = pct(m.t0); bar.style.width = (((Math.min(m.t1, B.b) - m.t0) / DUR) * 100) + "%";
      if (m.t1 > B.b + 1e-3) { bar.style.borderRight = "0"; bar.title += " (runs past the beat end)"; }
      bar.title = m.name + " · " + tc(m.t0) + " to " + tc(m.t1) + " · " + m.curve + (m.ok ? (m.trimmed ? " · span trimmed to the frames where it moves" : "") : " · unverified: " + m.why);
      // keyframes are absolute source seconds
      ["peak", "land"].forEach(function (k) { var kt = m.keys[k]; if (kt == null || kt > B.b) return; var kk = h("span", "k"); kk.style.left = (((kt - m.t0) / (Math.min(m.t1, B.b) - m.t0)) * 100) + "%"; bar.appendChild(kk); });
      bar.appendChild(h("span", "lbl", m.id + " " + m.prop + " " + frames(m.t1 - m.t0)));
      tr.appendChild(bar);
    });
  });
  if (!packed.length) { var none = lane("moves", 18); none.appendChild(h("span", "mr-tick", "no tracked moves; change happens across the cut")); none.lastChild.style.left = "50%"; }

  var sfxLane = lane("sound fx " + SFX.length, 34);
  var colors = B.sfxColors;
  SFX.forEach(function (s, k) {
    var mk = h("span", "mr-sfx" + (s.ok ? "" : " is-unverified")); mk.style.left = pct(s.t); mk.style.top = (k % 2) * 50 + "%";
    if ((s.t - B.a) / DUR > 0.94) { mk.style.flexDirection = "row-reverse"; mk.style.transform = "translateX(calc(-100% + 0.3em))"; }
    mk.setAttribute("data-move", "sfx " + s.cls + " " + tc(s.t));
    var dot = h("span", "mr-dot"); dot.style.background = colors[s.cls] || "#fff"; mk.appendChild(dot);
    mk.appendChild(h("span", "mr-sfx-t", s.cls));
    mk.title = s.cls + " at " + tc(s.t) + ", level " + s.level + " dB" + (s.bound ? ", bound to " + s.bound : "") + (s.ok ? (s.moved ? ", snapped to the audible onset" : "") : ", no audible onset within 80 ms");
    sfxLane.appendChild(mk);
  });

  grid.style.gridTemplateRows = rows.join(" ");
  var headRow = h("div"); headRow.style.position = "relative"; headRow.style.height = "18px";
  var readout = h("span", "sb-readout", ""); headRow.appendChild(readout);
  var legend = h("div", "sb-legend");
  legend.innerHTML = '<span><i style="background:#fff;width:3px"></i>hard cut</span>' + (B.missed.length ? '<span><i style="background:repeating-linear-gradient(180deg,#ff9f1c 0 3px,transparent 3px 5px);width:3px"></i>cut missing from fingerprint</span>' : '') +
    '<span><i style="background:rgba(200,120,255,.45);border:1px solid #c878ff"></i>soft transition</span><span><i style="background:#ffd166;width:3px"></i>downbeat</span>' +
    '<span><i style="background:#2b6cff"></i>high</span><span><i style="background:rgba(43,108,255,.55)"></i>medium</span><span><i style="background:repeating-linear-gradient(45deg,rgba(143,176,255,.75) 0 3px,transparent 3px 6px)"></i>low confidence</span>' +
    '<span>B boxes · U unverified</span>';
  headRow.appendChild(legend);
  ruler.appendChild(headRow);
  ruler.appendChild(grid);
  var playhead = h("div", "mr-playhead"); grid.appendChild(playhead);
  frame.appendChild(ruler);

  // ---- toggle -------------------------------------------------------------
  var KEY = "me-review-overlay", shownOv = true;
  try { shownOv = localStorage.getItem(KEY) !== "off"; } catch (e) {}
  var pill = h("button", "me-review-pill", "review"); pill.type = "button"; pill.setAttribute("data-review-overlay", "toggle");
  frame.appendChild(pill);
  function apply() {
    document.body.classList.toggle("sb-off", !shownOv || clean);
    pill.classList.toggle("is-off", !shownOv);
    pill.style.display = clean ? "none" : "";
    try { localStorage.setItem(KEY, shownOv ? "on" : "off"); } catch (e) {}
  }
  function layers() {
    regions.style.display = clean || !showBoxes ? "none" : "block";
    try { localStorage.setItem("me-review-boxes", showBoxes ? "on" : "off"); localStorage.setItem("me-review-unverified", showUnverified ? "on" : "off"); } catch (e) {}
  }
  pill.addEventListener("click", function (e) { e.stopPropagation(); shownOv = !shownOv; apply(); });
  window.addEventListener("keydown", function (e) {
    if (e.metaKey || e.ctrlKey) return;
    var k = (e.key || "").toLowerCase();
    if (k === "o") { shownOv = !shownOv; apply(); }
    else if (k === "b") { showBoxes = !showBoxes; layers(); }
    else if (k === "u") { showUnverified = !showUnverified; layers(); location.reload(); }
  });
  apply(); layers();
  fit();

  // ---- follow the time ---------------------------------------------------
  function tick() {
    var now = window.__storyboard.time();
    var src = B.a + now;
    var first = grid.querySelector(".mr-track");
    if (first) playhead.style.left = (first.offsetLeft + first.offsetWidth * Math.max(0, Math.min(1, now / DUR))) + "px";
    readout.textContent = "src " + tc(src) + "   beat f" + Math.floor(now * FPS + 1e-6) + " / " + Math.round(DUR * FPS);
    boxes.forEach(function (p) { p[0].classList.toggle("is-on", src >= p[1].t0 - 0.02 && src <= p[1].t1 + 0.02); });
    MOVES.forEach(function (m, i) { moveEls[i].classList.toggle("is-now", src >= m.t0 && src <= m.t1); });
    B.shots.forEach(function (s, i) { var on = src >= s.a && src < s.b; shotEls[i].classList.toggle("is-now", on); shotBlocks[i][0].classList.toggle("is-now", on); });
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();
