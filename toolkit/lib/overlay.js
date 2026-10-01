/* Review overlay for a storyboard frame. Board only: build-composition never
   includes it, so it cannot reach a render. It reads window.__review (written
   by storyboard.mjs) and the spans the runtime measured for each move, and
   draws the feeling, the voice-over line, a timing ruler with the words, a bar
   per move marked signature or novel, and the sound markers. A playhead follows
   the timeline as the canvas scrubs it. Toggle with the pill or the O key;
   ?clean in the URL hides it for stills. */
(function () {
  var R = window.__review;
  var M = window.__motionExpert;
  if (!R || !M) return;
  var frame = document.getElementById("frame");
  var clean = /[?&]clean\b/.test(location.search);
  if (clean) return;

  var KEY = "me-review-overlay";
  var shown = true;
  try { shown = localStorage.getItem(KEY) !== "off"; } catch (e) {}

  function h(tag, cls, text) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text != null) el.textContent = text;
    return el;
  }
  function pct(t) { return Math.max(0, Math.min(100, (t / R.duration) * 100)) + "%"; }

  var panel = h("aside", "me-review");
  panel.setAttribute("data-review-overlay", "panel");
  var head = h("div", "mr-head");
  head.appendChild(h("span", "mr-title", R.label));
  var feel = h("span", "mr-feel");
  feel.appendChild(h("span", "mr-k", "feeling"));
  feel.appendChild(document.createTextNode(R.feeling));
  head.appendChild(feel);
  panel.appendChild(head);
  if (R.vo_line) panel.appendChild(h("div", "mr-vo", "“" + R.vo_line + "”"));

  var grid = h("div", "mr-grid");
  function lane(label, badge, badgeKind) {
    var l = h("div", "mr-label");
    l.appendChild(h("span", "mr-name", label));
    if (badge) l.appendChild(h("span", "mr-badge mr-b-" + badgeKind, badge));
    var track = h("div", "mr-track");
    grid.appendChild(l);
    grid.appendChild(track);
    return track;
  }

  // time axis
  var axis = lane("time", null);
  axis.classList.add("mr-axis");
  var step = R.duration > 6 ? 1 : 0.5;
  for (var t = 0; t <= R.duration + 1e-6; t += step) {
    var tick = h("span", "mr-tick", (Math.round(t * 10) / 10) + "s");
    tick.style.left = pct(t);
    axis.appendChild(tick);
  }

  // voice-over words
  var vo = lane("vo", null);
  for (var i = 0; i < R.words.length; i++) {
    var w = R.words[i];
    var chip = h("span", "mr-word", w.w);
    chip.setAttribute("data-word-index", w.i);
    chip.style.left = pct(w.start);
    chip.style.width = "calc(" + pct(w.end - w.start) + " - 2px)";
    vo.appendChild(chip);
  }

  // moves, from the spans the runtime actually put on the timeline
  var report = (M.reports && M.reports[R.id]) || [];
  var kinds = { signature: "signature", novel: "novel", composed: "novel, composed", placeholder: "novel, not built" };
  for (var j = 0; j < report.length; j++) {
    var m = report[j];
    var kind = m.kind === "signature" ? "sig" : "novel";
    var tr = lane(m.name + " → " + m.target, kinds[m.kind] || m.kind, kind);
    var bar = h("span", "mr-bar mr-" + kind);
    bar.style.left = pct(m.start);
    bar.style.width = pct(Math.max(0.04, m.end - m.start));
    bar.title = m.start.toFixed(2) + "s to " + m.end.toFixed(2) + "s";
    tr.appendChild(bar);
    var at = h("span", "mr-at");
    at.style.left = pct(m.t);
    tr.appendChild(at);
  }

  // sound
  if (R.sfx.length) {
    var sx = lane("sfx", R.sfx.length + "", "sfx");
    for (var k = 0; k < R.sfx.length; k++) {
      var s = R.sfx[k];
      var mk = h("span", "mr-sfx");
      mk.style.left = pct(s.local);
      mk.appendChild(h("span", "mr-dot"));
      mk.appendChild(h("span", "mr-sfx-t", s["class"] + " · " + s.clipName + (s.gain_db ? " " + s.gain_db + "dB" : "")));
      mk.style.top = (k % 2) * 50 + "%";
      sx.appendChild(mk);
    }
  }
  panel.appendChild(grid);

  var head2 = h("div", "mr-playhead");
  grid.appendChild(head2);
  frame.appendChild(panel);

  var pill = h("button", "me-review-pill", "review");
  pill.setAttribute("data-review-overlay", "toggle");
  pill.type = "button";
  frame.appendChild(pill);

  function apply() {
    panel.style.display = shown ? "" : "none";
    pill.classList.toggle("is-off", !shown);
    try { localStorage.setItem(KEY, shown ? "on" : "off"); } catch (e) {}
  }
  pill.addEventListener("click", function (e) { e.stopPropagation(); shown = !shown; apply(); });
  window.addEventListener("keydown", function (e) {
    if ((e.key === "o" || e.key === "O") && !e.metaKey && !e.ctrlKey) { shown = !shown; apply(); }
  });
  apply();

  // Playhead and the current word follow whatever is seeking the timeline.
  var words = vo.querySelectorAll(".mr-word");
  function tickFn() {
    var tl = window.__timelines && window.__timelines.main;
    if (tl && shown) {
      var now = tl.time();
      var first = grid.querySelector(".mr-track");
      var left = first ? first.offsetLeft : 0;
      var width = first ? first.offsetWidth : grid.offsetWidth;
      head2.style.left = (left + width * Math.max(0, Math.min(1, now / R.duration))) + "px";
      for (var q = 0; q < words.length; q++) {
        var ww = R.words[q];
        words[q].classList.toggle("is-now", now >= ww.start && now < ww.end);
      }
    }
    requestAnimationFrame(tickFn);
  }
  requestAnimationFrame(tickFn);
})();
