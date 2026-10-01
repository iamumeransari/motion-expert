// Sound placement, shared by storyboard.mjs and build-composition.mjs so the
// board shows exactly the sounds the render will play.
//
// sfx-plan.json comes from toolkit/sound-plan.py:
//   { "events": [{ "clip", "t", "gain_db", "pan", "class", "move": "<scene id>/<move name>" }],
//     "music": { "clip", "gain_db", "duck_db_under_vo" } }
// A move reference may also name its target, "<scene>/<move>@<target>", when a
// scene uses the same move twice. The plan's per-move "sfx" field is applied
// over the sound plan: false silences the move's events, an object overrides
// their fields, and an object with a clip adds an event where none exists.

import { readFileSync, existsSync } from "node:fs";
import { resolve, isAbsolute, dirname, basename } from "node:path";

const abs = (p, base) => (isAbsolute(p) ? p : resolve(base, p));

export function loadSfx(sfxPath, plan, scenes, planDir) {
  const out = { events: [], music: null, silenced: [], warnings: [], errors: [], source: sfxPath ?? null };
  let sp = { events: [], music: null };
  let base = planDir;
  if (sfxPath) {
    if (!existsSync(sfxPath)) {
      out.errors.push(`sfx plan ${sfxPath} not found`);
      return out;
    }
    try {
      sp = JSON.parse(readFileSync(sfxPath, "utf8"));
    } catch (e) {
      out.errors.push(`sfx plan is not valid JSON: ${e.message}`);
      return out;
    }
    base = dirname(sfxPath);
  }

  // Every move in the piece, addressable by scene/name and scene/name@target.
  const moves = [];
  for (const s of scenes) for (const m of s.moves) moves.push({ ...m, sceneId: s.id, sceneStart: s.start });
  const findMove = (ref) => {
    const m = /^([^/]+)\/([^@]+)(?:@(.+))?$/.exec(String(ref ?? ""));
    if (!m) return null;
    return moves.find((mv) => mv.sceneId === m[1] && mv.name === m[2] && (!m[3] || mv.target === m[3])) ?? null;
  };
  const sceneAt = (t) => scenes.find((s) => t >= s.start - 1e-6 && t < s.start + s.duration - 1e-6) ?? scenes[scenes.length - 1];

  const covered = new Set();
  for (const [i, e] of (sp.events ?? []).entries()) {
    if (typeof e?.clip !== "string" || typeof e?.t !== "number") {
      out.errors.push(`events[${i}] needs a clip and a numeric t`);
      continue;
    }
    const move = e.move ? findMove(e.move) : null;
    if (e.move && !move) out.warnings.push(`events[${i}] is tied to "${e.move}", which is not a move in the plan; kept at ${e.t}s`);
    const ev = {
      clip: abs(e.clip, base),
      t: e.t,
      gain_db: typeof e.gain_db === "number" ? e.gain_db : 0,
      pan: typeof e.pan === "number" ? e.pan : 0,
      class: e.class ?? "sfx",
      move: e.move ?? null,
      origin: "sound-plan",
      moveRef: move,
    };
    if (move) {
      covered.add(move);
      if (move.sfx === false) {
        out.silenced.push({ ...ev, reason: "plan sets sfx: false on the move" });
        continue;
      }
      if (move.sfx && typeof move.sfx === "object") {
        const o = move.sfx;
        if (o.class) ev.class = o.class;
        if (o.clip) ev.clip = abs(o.clip, planDir);
        if (typeof o.gain_db === "number") ev.gain_db = o.gain_db;
        if (typeof o.offset_s === "number") ev.t = move.tAbs + o.offset_s;
        ev.origin = "plan override";
      }
    }
    out.events.push(ev);
  }

  // Plan overrides that bring their own clip and have no event to modify.
  for (const move of moves) {
    if (covered.has(move) || !move.sfx || typeof move.sfx !== "object") continue;
    if (!move.sfx.clip) {
      out.warnings.push(`${move.sceneId}/${move.name}@${move.target} overrides its sound but names no clip and the sound plan has no event for it`);
      continue;
    }
    out.events.push({
      clip: abs(move.sfx.clip, planDir),
      t: move.tAbs + (move.sfx.offset_s ?? 0),
      gain_db: move.sfx.gain_db ?? 0,
      pan: 0,
      class: move.sfx.class ?? "sfx",
      move: `${move.sceneId}/${move.name}@${move.target}`,
      origin: "plan override",
      moveRef: move,
    });
  }

  out.events.sort((a, b) => a.t - b.t);
  out.events.forEach((ev, i) => {
    ev.id = `sfx-${String(i + 1).padStart(2, "0")}`;
    ev.clipName = basename(ev.clip);
    ev.t = Number(ev.t.toFixed(4));
    const s = ev.moveRef ? scenes.find((x) => x.id === ev.moveRef.sceneId) : sceneAt(ev.t);
    ev.sceneId = s?.id ?? null;
    ev.local = s ? Number((ev.t - s.start).toFixed(4)) : ev.t;
    ev.moveName = ev.moveRef?.name ?? null;
    ev.target = ev.moveRef?.target ?? null;
    delete ev.moveRef;
    if (!existsSync(ev.clip)) out.errors.push(`${ev.id} (${ev.class}) clip ${ev.clip} is not on disk`);
    if (ev.t < 0 || ev.t >= plan.duration) out.errors.push(`${ev.id} (${ev.class}) at ${ev.t}s is outside the piece`);
    if (ev.gain_db > 12) out.warnings.push(`${ev.id} gain ${ev.gain_db} dB is past the +12 dB HyperFrames allows; clamped`);
    if (Math.abs(ev.pan) > 1) out.errors.push(`${ev.id} pan ${ev.pan} is outside -1..1`);
  });

  if (sp.music && typeof sp.music === "object") {
    if (typeof sp.music.clip !== "string") out.errors.push("music needs a clip");
    else {
      out.music = {
        clip: abs(sp.music.clip, base),
        gain_db: typeof sp.music.gain_db === "number" ? sp.music.gain_db : -18,
        duck_db_under_vo: typeof sp.music.duck_db_under_vo === "number" ? sp.music.duck_db_under_vo : 0,
      };
      out.music.clipName = basename(out.music.clip);
      if (!existsSync(out.music.clip)) out.errors.push(`music clip ${out.music.clip} is not on disk`);
    }
  }
  return out;
}

// Phrases the music ducks under: words merged across gaps shorter than `bridge`.
export function voPhrases(words, bridge = 0.35) {
  const out = [];
  for (const w of words ?? []) {
    const last = out[out.length - 1];
    if (last && w.start - last.end < bridge) last.end = Math.max(last.end, w.end);
    else out.push({ start: w.start, end: w.end });
  }
  return out;
}

// A gain lane for the music bed in dB, clip-local seconds (the bed starts at 0):
// down `duck` dB across each phrase with a short attack and a slow release, so
// the bed breathes back between phrases rather than snapping, and a fade at
// the tail so the piece does not end on a cut-off chord.
export function duckLane(words, total, baseDb, duckDb, { attack = 0.12, release = 0.4, fadeOut = 0.6 } = {}) {
  const lo = baseDb - Math.abs(duckDb);
  const points = [{ t: 0, v: baseDb }];
  const push = (t, v) => {
    t = Math.max(0, Math.min(total, Number(t.toFixed(3))));
    const prev = points[points.length - 1];
    if (t < prev.t) return;
    if (t === prev.t) prev.v = v;
    else points.push({ t, v });
  };
  if (Math.abs(duckDb) > 0) {
    // A gap shorter than attack plus release stays ducked rather than pumping.
    for (const p of voPhrases(words, attack + release)) {
      push(p.start - attack, baseDb);
      push(p.start, lo);
      push(p.end, lo);
      push(p.end + release, baseDb);
    }
  }
  const last = points[points.length - 1].v;
  push(total - fadeOut, last);
  push(total, -60);
  return points.map((p) => ({ t: p.t, v: Number(Math.max(-60, Math.min(12, p.v)).toFixed(2)) }));
}
