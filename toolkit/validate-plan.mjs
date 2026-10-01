#!/usr/bin/env node
// The plan gate. Checks a scene plan against schema/scene-plan.schema.json and
// against what a shape cannot say: every move resolves to a library element or
// is marked novel with a grammar note, every time lands inside its scene, every
// word reference exists, the scenes tile the piece, and grammar-composed tweens
// stay inside the style's primitive envelopes.
//
//   node toolkit/validate-plan.mjs <plan.json> [--style-dir <dir>] [--beats <json>]
//        [--sfx <sfx-plan.json>] [--json]
//
// The voice-over is optional: a music-only piece times its moves in seconds or
// on the music's beat grid (beat:<n>, downbeat:<n>) from --beats or
// plan.music.beats. Media in move props and style assets must resolve, and a
// plan that is not "mode": "replica" may not reference a calibration-only file.
//
// Adapted from ~/motion-ui/pipeline/validate-plan.mjs. Exits non-zero on any
// error. Warnings never fail the run; they are what the planning agent reads
// before the board goes up.

import { readFileSync, existsSync, readdirSync } from "node:fs";
import { resolve, dirname, isAbsolute, basename } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { mediaRefs, calibrationHits, planMode } from "./lib/media.mjs";
import { loadSfx } from "./lib/sfx.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
export const TOOLKIT = HERE;
export const REPO = resolve(HERE, "..");
export const SCHEMA_DIR = resolve(HERE, "schema");

const EPS = 0.001;
// Layouts the toolkit ships CSS for. A style adds its own as .me-stage.layout-<name> in tokens.css.
export const BUILTIN_LAYOUTS = ["center", "stack", "split", "free", "full"];

// ---------------------------------------------------------------------------
// A very small JSON Schema reader covering exactly the keywords the toolkit's
// schemas use. It fails loudly on a keyword it does not know rather than
// passing something it never looked at.
// ---------------------------------------------------------------------------

const KNOWN_KEYWORDS = new Set([
  "$schema", "$id", "$ref", "$defs", "title", "description", "type", "required",
  "properties", "additionalProperties", "items", "enum", "const", "pattern",
  "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
  "minLength", "maxLength", "minItems", "maxItems",
]);

function typeOf(value) {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  if (Number.isInteger(value)) return "integer";
  return typeof value;
}

function typeMatches(value, want) {
  const actual = typeOf(value);
  if (want === "number") return actual === "number" || actual === "integer";
  return actual === want;
}

function deref(schema, root) {
  if (!schema || !schema.$ref) return schema;
  if (!schema.$ref.startsWith("#/")) throw new Error(`unsupported $ref: ${schema.$ref}`);
  let node = root;
  for (const part of schema.$ref.slice(2).split("/")) node = node?.[part];
  if (!node) throw new Error(`unresolvable $ref: ${schema.$ref}`);
  return node;
}

export function checkSchema(value, schema, root = schema, path = "$", out = []) {
  const s = deref(schema, root);
  for (const key of Object.keys(s)) {
    if (!KNOWN_KEYWORDS.has(key)) out.push(`${path}: schema uses unsupported keyword "${key}"`);
  }
  if (s.type !== undefined) {
    const wants = Array.isArray(s.type) ? s.type : [s.type];
    if (!wants.some((w) => typeMatches(value, w))) {
      out.push(`${path}: expected ${wants.join(" or ")}, got ${typeOf(value)}`);
      return out;
    }
  }
  if (s.enum !== undefined && !s.enum.some((e) => e === value)) {
    out.push(`${path}: ${JSON.stringify(value)} is not one of ${s.enum.map((e) => JSON.stringify(e)).join(", ")}`);
  }
  if (s.const !== undefined && value !== s.const) out.push(`${path}: expected ${JSON.stringify(s.const)}`);
  if (typeof value === "string") {
    if (s.pattern !== undefined && !new RegExp(s.pattern).test(value)) out.push(`${path}: ${JSON.stringify(value)} does not match ${s.pattern}`);
    if (s.minLength !== undefined && value.length < s.minLength) out.push(`${path}: shorter than ${s.minLength} characters`);
    if (s.maxLength !== undefined && value.length > s.maxLength) out.push(`${path}: longer than ${s.maxLength} characters`);
  }
  if (typeof value === "number") {
    if (s.minimum !== undefined && value < s.minimum) out.push(`${path}: ${value} is below ${s.minimum}`);
    if (s.maximum !== undefined && value > s.maximum) out.push(`${path}: ${value} is above ${s.maximum}`);
    if (s.exclusiveMinimum !== undefined && value <= s.exclusiveMinimum) out.push(`${path}: ${value} must be greater than ${s.exclusiveMinimum}`);
    if (s.exclusiveMaximum !== undefined && value >= s.exclusiveMaximum) out.push(`${path}: ${value} must be less than ${s.exclusiveMaximum}`);
  }
  if (Array.isArray(value)) {
    if (s.minItems !== undefined && value.length < s.minItems) out.push(`${path}: needs at least ${s.minItems} item(s)`);
    if (s.maxItems !== undefined && value.length > s.maxItems) out.push(`${path}: allows at most ${s.maxItems} item(s)`);
    if (s.items) value.forEach((v, i) => checkSchema(v, s.items, root, `${path}[${i}]`, out));
  }
  if (value && typeof value === "object" && !Array.isArray(value)) {
    for (const key of s.required ?? []) if (!(key in value)) out.push(`${path}: missing required property "${key}"`);
    const props = s.properties ?? {};
    for (const [key, sub] of Object.entries(value)) {
      if (props[key]) checkSchema(sub, props[key], root, `${path}.${key}`, out);
      else if (s.additionalProperties === false) out.push(`${path}: unexpected property "${key}"`);
      else if (s.additionalProperties && typeof s.additionalProperties === "object") checkSchema(sub, s.additionalProperties, root, `${path}.${key}`, out);
    }
  }
  return out;
}

export function loadSchema(name) {
  return JSON.parse(readFileSync(resolve(SCHEMA_DIR, name), "utf8"));
}

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

export function loadPlan(planPath) {
  const abs = isAbsolute(planPath) ? planPath : resolve(process.cwd(), planPath);
  if (!existsSync(abs)) throw new Error(`plan not found: ${abs}`);
  try {
    return { plan: JSON.parse(readFileSync(abs, "utf8")), path: abs, dir: dirname(abs) };
  } catch (err) {
    throw new Error(`plan is not valid JSON: ${err.message}`);
  }
}

// --style-dir wins; otherwise the style skill under skills/.
export function resolveStyleDir(plan, styleDirFlag = null) {
  if (styleDirFlag) return isAbsolute(styleDirFlag) ? styleDirFlag : resolve(process.cwd(), styleDirFlag);
  const slug = String(plan?.style ?? "");
  const candidates = [resolve(REPO, "skills", `${slug}-motion`)];
  if (slug.endsWith("-motion")) candidates.push(resolve(REPO, "skills", slug));
  return candidates.find((c) => existsSync(c)) ?? candidates[0];
}

export function loadStyle(styleDir) {
  const style = { dir: styleDir, problems: [], warnings: [], tokens: null, tokensCss: "", fontsCss: "", library: new Map(), grammar: null };
  if (!existsSync(styleDir)) {
    style.problems.push(`style directory ${styleDir} does not exist`);
    return style;
  }
  const cssPath = resolve(styleDir, "tokens.css");
  if (existsSync(cssPath)) style.tokensCss = readFileSync(cssPath, "utf8");
  else style.problems.push(`${cssPath} is missing`);
  const fontsPath = resolve(styleDir, "fonts.css");
  if (existsSync(fontsPath)) style.fontsCss = readFileSync(fontsPath, "utf8");

  const tokPath = resolve(styleDir, "tokens.json");
  if (existsSync(tokPath)) {
    try {
      style.tokens = JSON.parse(readFileSync(tokPath, "utf8"));
      const schema = loadSchema("tokens.schema.json");
      for (const p of checkSchema(style.tokens, schema)) style.problems.push(`tokens.json ${p}`);
    } catch (err) {
      style.problems.push(`tokens.json is not valid JSON: ${err.message}`);
    }
  } else {
    style.problems.push(`${tokPath} is missing; named easings and the timing unit come from it`);
  }

  const libDir = resolve(styleDir, "library");
  if (existsSync(libDir)) {
    for (const f of readdirSync(libDir)) if (f.endsWith(".html")) style.library.set(basename(f, ".html"), resolve(libDir, f));
  } else {
    style.problems.push(`${libDir} is missing`);
  }

  const gPath = resolve(styleDir, "grammar.json");
  if (existsSync(gPath)) {
    try {
      style.grammar = JSON.parse(readFileSync(gPath, "utf8"));
      const schema = loadSchema("move.schema.json");
      (style.grammar.primitives ?? []).forEach((p, i) => {
        for (const e of checkSchema(p, schema)) style.problems.push(`grammar.json primitives[${i}] ${e}`);
      });
    } catch (err) {
      style.problems.push(`grammar.json is not valid JSON: ${err.message}`);
    }
  }
  return style;
}

// ---------------------------------------------------------------------------
// Resolution, shared by storyboard.mjs and build-composition.mjs so the board
// and the render read the plan the same way.
// ---------------------------------------------------------------------------

const TIME_REF = /^(word|beat|downbeat):(\d+)([+-]\d*\.?\d+)?$/;

// The music's beat grid, {"beats": [t...], "downbeats": [t...]} in seconds from
// the start of the piece. src is a path (absolute, or relative to base) or the
// object itself. Returns { beats, downbeats, source } or { error }.
export function loadBeats(src, base = process.cwd()) {
  if (src === null || src === undefined) return null;
  let grid = src;
  let source = "plan.music.beats (inline)";
  if (typeof src === "string") {
    const p = isAbsolute(src) ? src : resolve(base, src);
    if (!existsSync(p)) return { error: `beat grid ${p} is not on disk`, source: p };
    try { grid = JSON.parse(readFileSync(p, "utf8")); } catch (e) { return { error: `beat grid ${p} is not valid JSON: ${e.message}`, source: p }; }
    source = p;
  }
  if (!grid || typeof grid !== "object" || !Array.isArray(grid.beats)) return { error: `beat grid ${source} needs a "beats" array of seconds`, source };
  const downbeats = Array.isArray(grid.downbeats) ? grid.downbeats : [];
  for (const [name, list] of [["beats", grid.beats], ["downbeats", downbeats]]) {
    for (let i = 0; i < list.length; i++) {
      if (typeof list[i] !== "number" || !isFinite(list[i]) || list[i] < 0) return { error: `beat grid ${source} ${name}[${i}] is not a time in seconds`, source };
      if (i && list[i] < list[i - 1]) return { error: `beat grid ${source} ${name}[${i}] comes before ${name}[${i - 1}]`, source };
    }
  }
  return { beats: grid.beats, downbeats, source };
}

// t is seconds, word:<i> (a voice-over word's onset), beat:<i> or
// downbeat:<i> (the music's grid), each with an optional offset in seconds.
export function resolveTime(t, words, beats = null) {
  if (typeof t === "number") return { at: t };
  const m = TIME_REF.exec(String(t));
  if (!m) return { error: `t "${t}" is neither seconds, word:<index> nor beat:<index>` };
  const index = Number(m[2]);
  const off = m[3] ? Number(m[3]) : 0;
  if (m[1] === "word") {
    if (!words?.length) return { error: `t "${t}" needs voice-over words and this plan has none; time it in seconds or as beat:<n> on the music` };
    const word = words[index];
    if (!word) return { error: `t "${t}" references word ${index}, but vo.words has ${words.length}` };
    return { at: word.start + off, word: { index, w: word.w } };
  }
  if (!beats || beats.error) return { error: `t "${t}" needs a beat grid; pass --beats <json> or set plan.music.beats${beats?.error ? ` (${beats.error})` : ""}` };
  const list = m[1] === "beat" ? beats.beats : beats.downbeats;
  if (index >= list.length) return { error: `t "${t}" references ${m[1]} ${index}, but the grid has ${list.length}` };
  return { at: list[index] + off, beat: { index, kind: m[1] } };
}

// kind: signature (style library), novel (element written beside the plan),
// composed (grammar tweens run by the toolkit composer), placeholder (novel and
// not built yet; boards show it, compositions refuse it).
export function resolveMove(move, style, planDir) {
  const styleFile = style.library.get(move.name) ?? null;
  const localPath = resolve(planDir, "library", `${move.name}.html`);
  const localFile = existsSync(localPath) ? localPath : null;
  const novel = move.novel === true;
  if (styleFile) return { kind: novel ? "novel" : "signature", file: styleFile, key: move.name };
  if (localFile) return { kind: novel ? "novel" : "unlisted", file: localFile, key: move.name };
  if (!novel) return { kind: "missing", file: null, key: null };
  if (Array.isArray(move.props?.tweens) && move.props.tweens.length) return { kind: "composed", file: null, key: "__grammar" };
  return { kind: "placeholder", file: null, key: "__placeholder" };
}

export function resolvePlan(plan, style, planDir, beats = null) {
  const words = plan.vo?.words ?? [];
  return (plan.scenes ?? []).map((scene, index) => {
    const moves = (scene.moves ?? []).map((move) => {
      const time = resolveTime(move.t, words, beats);
      const res = resolveMove(move, style, planDir);
      const at = time.at ?? scene.start;
      return {
        name: move.name,
        target: move.target,
        key: res.key,
        kind: res.kind,
        file: res.file,
        novel: move.novel === true,
        grammar_note: move.grammar_note ?? "",
        tRef: move.t,
        tAbs: Number(at.toFixed(4)),
        t: Number((at - scene.start).toFixed(4)),
        word: time.word ?? null,
        beat: time.beat ?? null,
        timeError: time.error ?? null,
        props: move.props ?? {},
        sfx: move.sfx ?? null,
      };
    });
    const sceneWords = words
      .map((w, i) => ({ ...w, i }))
      .filter((w) => w.end > scene.start + EPS && w.start < scene.start + scene.duration - EPS)
      .map((w) => ({ i: w.i, w: w.w, start: Number((w.start - scene.start).toFixed(4)), end: Number((w.end - scene.start).toFixed(4)) }));
    const down = new Set(beats?.downbeats ?? []);
    const sceneBeats = (beats?.beats ?? [])
      .map((t, i) => ({ i, t }))
      .filter((b) => b.t >= scene.start - EPS && b.t < scene.start + scene.duration - EPS)
      .map((b) => ({ i: b.i, t: Number((b.t - scene.start).toFixed(4)), down: down.has(b.t) }));
    return { index, id: scene.id, title: scene.title, start: scene.start, duration: scene.duration, feeling: scene.feeling, vo_line: scene.vo_line, layout: scene.layout, background: scene.background ?? null, notes: scene.notes ?? "", moves, words: sceneWords, beats: sceneBeats };
  });
}

// ---------------------------------------------------------------------------
// Envelopes. A grammar-composed tween is legal when every property it drives
// has a primitive, is not marked absent, and its duration, stagger, curve and
// travel sit inside the measured ranges.
// ---------------------------------------------------------------------------

const inRange = (v, r) => !Array.isArray(r) || (v >= r[0] - 1e-9 && v <= r[1] + 1e-9);
const TRANSFORM_ALIASES = { scale: ["scale", "scaleX", "scaleY"], autoAlpha: ["opacity"] };

function travelFrac(value, axis, format) {
  if (typeof value === "string") {
    const m = /^(-?\d*\.?\d+)([HW])$/.exec(value.trim());
    if (m) return Math.abs(Number(m[1]));
    if (/^-?\d*\.?\d+(px)?$/.test(value.trim())) value = parseFloat(value);
    else return null;
  }
  if (typeof value !== "number") return null;
  return Math.abs(value) / (axis === "x" ? format.width : format.height);
}

export function checkEnvelopes(move, style, format) {
  const out = [];
  const prims = style.grammar?.primitives;
  if (!prims?.length) return out;
  const find = (prop) => prims.find((p) => p.property === prop) ?? prims.find((p) => (TRANSFORM_ALIASES[prop] ?? []).includes(p.property));
  (move.props?.tweens ?? []).forEach((tw, i) => {
    const props = new Set([...Object.keys(tw.to ?? {}), ...Object.keys(tw.from ?? {})]);
    for (const prop of props) {
      if (["transformOrigin", "immediateRender"].includes(prop)) continue;
      const p = find(prop);
      const where = `tweens[${i}].${prop}`;
      if (!p) { out.push(`${where}: the style's grammar has no primitive for "${prop}"`); continue; }
      if (p.absent) { out.push(`${where}: the source never animates "${prop}" (marked absent in grammar.json)`); continue; }
      if (typeof tw.units === "number" && !inRange(tw.units, p.duration_units)) out.push(`${where}: ${tw.units}u is outside the duration envelope ${JSON.stringify(p.duration_units)}`);
      if (typeof tw.stagger === "number" && tw.stagger > 0 && p.stagger_units && !inRange(tw.stagger, p.stagger_units)) out.push(`${where}: stagger ${tw.stagger}u is outside ${JSON.stringify(p.stagger_units)}`);
      if (tw.ease && Array.isArray(p.curves) && p.curves.length && !p.curves.includes(tw.ease)) out.push(`${where}: ease "${tw.ease}" is not one this property is seen on (${p.curves.join(", ")})`);
      if ((prop === "x" || prop === "y") && p.travel_frac) {
        const a = travelFrac(tw.from?.[prop] ?? 0, prop, format);
        const b = travelFrac(tw.to?.[prop] ?? 0, prop, format);
        if (a !== null && b !== null) {
          const travel = Math.abs(a - b);
          if (!inRange(travel, p.travel_frac)) out.push(`${where}: travel ${travel.toFixed(3)} of the frame is outside ${JSON.stringify(p.travel_frac)}`);
        }
      }
    }
  });
  return out;
}

// ---------------------------------------------------------------------------

// beats: a beat grid path (relative to the working directory) or object that
// overrides plan.music.beats. sfxPath: an sfx plan whose clips the
// calibration guard also checks.
export function validatePlan(plan, { planDir = process.cwd(), styleDir = null, beats: beatsFlag = null, sfxPath = null } = {}) {
  const errors = [];
  const warnings = [];
  const err = (rule, message, scene) => errors.push({ rule, scene, message });
  const warn = (rule, message, scene) => warnings.push({ rule, scene, message });

  const schema = loadSchema("scene-plan.schema.json");
  for (const p of checkSchema(plan, schema)) err("schema", p);

  const dir = resolveStyleDir(plan, styleDir);
  const style = loadStyle(dir);
  for (const p of style.problems) err("style", p);

  const scenes = Array.isArray(plan?.scenes) ? plan.scenes : [];
  const words = Array.isArray(plan?.vo?.words) ? plan.vo.words : [];
  const format = plan?.format ?? { width: 1920, height: 1080 };

  // words are ordered and sane
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    if (w.end < w.start) err("vo", `word ${i} "${w.w}" ends before it starts`);
    if (i && w.start < words[i - 1].start - EPS) err("vo", `word ${i} "${w.w}" starts before word ${i - 1}`);
    if (typeof plan.duration === "number" && w.end > plan.duration + EPS) err("vo", `word ${i} "${w.w}" ends at ${w.end}s, past the piece's ${plan.duration}s`);
  }
  const hasVoAudio = typeof plan?.vo?.audio === "string" && plan.vo.audio.trim() !== "";
  const musicClip = typeof plan?.music?.clip === "string" ? (isAbsolute(plan.music.clip) ? plan.music.clip : resolve(planDir, plan.music.clip)) : null;
  if (hasVoAudio) {
    const a = isAbsolute(plan.vo.audio) ? plan.vo.audio : resolve(planDir, plan.vo.audio);
    if (!existsSync(a)) err("vo", `vo.audio ${a} is not on disk`);
  } else if (words.length) {
    warn("vo", "vo.words are set but vo.audio is not, so the render carries no voice while moves still follow the words");
  } else if (!musicClip) {
    warn("vo", "no voice-over and no plan.music.clip: a music-only piece needs its bed from plan.music or the sfx plan's music, or it renders without a timing spine");
  }
  if (musicClip && !existsSync(musicClip)) err("music", `music.clip ${musicClip} is not on disk`);

  // the beat grid: --beats wins over plan.music.beats
  const beats = beatsFlag !== null && beatsFlag !== undefined
    ? loadBeats(beatsFlag, process.cwd())
    : loadBeats(plan?.music?.beats ?? null, planDir);
  if (beats?.error) err("beats", beats.error);
  else if (beats && typeof plan?.duration === "number") {
    const past = beats.beats.filter((t) => t > plan.duration + EPS).length;
    if (past) warn("beats", `${past} beat(s) in the grid fall after the piece's ${plan.duration}s`);
  }

  // scenes tile the piece: unique ids, no overlap, no gap, nothing past the end
  const ids = new Set();
  for (const s of scenes) {
    if (ids.has(s.id)) err("id", `duplicate scene id "${s.id}"`, s.id);
    ids.add(s.id);
  }
  const timed = scenes.filter((s) => typeof s.start === "number" && typeof s.duration === "number");
  for (let i = 0; i < timed.length; i++) {
    const s = timed[i];
    if (i === 0 && s.start > EPS) warn("tiling", `the first scene starts at ${s.start}s, leaving ${s.start}s of nothing at the head`, s.id);
    if (i > 0) {
      const prevEnd = timed[i - 1].start + timed[i - 1].duration;
      if (s.start < prevEnd - EPS) err("tiling", `starts at ${s.start}s, inside ${timed[i - 1].id} which runs to ${prevEnd.toFixed(3)}s`, s.id);
      else if (s.start > prevEnd + EPS) warn("tiling", `starts ${(s.start - prevEnd).toFixed(3)}s after ${timed[i - 1].id} ends; the gap renders as an empty frame`, s.id);
    }
    if (typeof plan.duration === "number" && s.start + s.duration > plan.duration + EPS) err("tiling", `ends at ${(s.start + s.duration).toFixed(3)}s, past the piece's ${plan.duration}s`, s.id);
  }
  if (timed.length && typeof plan.duration === "number") {
    const last = timed[timed.length - 1];
    const end = last.start + last.duration;
    if (end < plan.duration - EPS) warn("tiling", `the last scene ends at ${end.toFixed(3)}s and the piece runs to ${plan.duration}s; the tail renders empty`, last.id);
  }

  // layouts
  for (const s of scenes) {
    if (typeof s.layout !== "string") continue;
    if (!BUILTIN_LAYOUTS.includes(s.layout) && !style.tokensCss.includes(`.layout-${s.layout}`)) {
      warn("layout", `layout "${s.layout}" is not a toolkit layout (${BUILTIN_LAYOUTS.join(", ")}) and tokens.css has no .layout-${s.layout} rule`, s.id);
    }
  }

  // moves
  const resolved = resolvePlan(plan, style, planDir, beats && !beats.error ? beats : null);
  let signature = 0, novel = 0;
  for (const scene of resolved) {
    const raw = scenes[scene.index] ?? {};
    const rawMoves = Array.isArray(raw.moves) ? raw.moves : [];
    if (!scene.moves.length) warn("moves", "the scene has no moves, so it is a held still", scene.id);
    scene.moves.forEach((m, i) => {
      const where = `${m.name} -> ${m.target}`;
      if (m.timeError) err("time", `${where}: ${m.timeError}`, scene.id);
      else if (m.t < -EPS || m.t >= scene.duration - EPS) {
        err("time", `${where}: starts at ${m.tAbs}s, outside the scene's ${scene.start}s to ${(scene.start + scene.duration).toFixed(3)}s`, scene.id);
      }
      const sfx = rawMoves[i]?.sfx;
      if (sfx === true) err("sfx", `${where}: sfx: true means nothing; use false to silence the move or an object to override its sound`, scene.id);
      if (sfx && typeof sfx === "object" && typeof sfx.clip === "string") {
        const clip = isAbsolute(sfx.clip) ? sfx.clip : resolve(planDir, sfx.clip);
        if (!existsSync(clip)) err("sfx", `${where}: sfx clip ${clip} is not on disk`, scene.id);
      }
      if (m.kind === "missing") err("move", `${where}: "${m.name}" is not in ${dir}/library and is not marked novel. Use a library move, or mark it novel with a grammar_note.`, scene.id);
      if (m.kind === "unlisted") err("move", `${where}: "${m.name}" exists only beside the plan in library/, which is where novel moves live. Mark it novel with a grammar_note, or promote it into the style's library.`, scene.id);
      if (m.novel) {
        novel++;
        if (!String(rawMoves[i]?.grammar_note ?? "").trim()) err("novel", `${where}: novel moves need a grammar_note naming the primitives they are built from`, scene.id);
        if (m.kind === "placeholder") warn("novel", `${where}: novel and not built yet. The board shows a labelled placeholder; build-composition refuses it until library/${m.name}.html exists beside the plan or props.tweens composes it.`, scene.id);
        if (m.kind === "composed") for (const e of checkEnvelopes(rawMoves[i], style, format)) err("envelope", `${where}: ${e}`, scene.id);
        if (m.kind === "composed" && style.tokens) {
          for (const tw of m.props.tweens) {
            if (tw.ease && !(tw.ease in (style.tokens.easings ?? {}))) warn("ease", `${where}: ease "${tw.ease}" is not a named easing in tokens.json and falls through to GSAP`, scene.id);
          }
        }
      } else if (m.kind === "signature") {
        signature++;
      }
    });
  }

  // media in move props and style assets
  const media = mediaRefs({ scenes: resolved, style, planDir });
  for (const r of media) {
    if (!r.abs) warn("media", `${r.where}: "${r.value}" is not beside the plan or in the style folder, so it is left as written and only resolves if the file sits at that path beside the board or project`, r.scene);
  }

  // The calibration guard. Source frames rebuild a replica and never enter a
  // piece, so a piece refuses any referenced file marked calibration-only.
  const mode = planMode(plan);
  const referenced = [];
  if (hasVoAudio) referenced.push({ file: isAbsolute(plan.vo.audio) ? plan.vo.audio : resolve(planDir, plan.vo.audio), what: "vo.audio" });
  if (musicClip) referenced.push({ file: musicClip, what: "music.clip" });
  if (beats?.source && !beats.source.includes("(inline)")) referenced.push({ file: beats.source, what: "beat grid" });
  for (const r of media) if (r.abs) referenced.push({ file: r.abs, what: r.where, scene: r.scene });
  for (const scene of resolved) for (const m of scene.moves) {
    if (m.file) referenced.push({ file: m.file, what: `${m.name} element`, scene: scene.id });
    const sfx = m.sfx;
    if (sfx && typeof sfx === "object" && typeof sfx.clip === "string") referenced.push({ file: isAbsolute(sfx.clip) ? sfx.clip : resolve(planDir, sfx.clip), what: `${m.name} -> ${m.target} sfx clip`, scene: scene.id });
  }
  if (sfxPath) {
    const sp = loadSfx(sfxPath, plan, resolved, planDir);
    for (const e of sp.events) referenced.push({ file: e.clip, what: `sfx ${e.id} (${e.class})` });
    if (sp.music) referenced.push({ file: sp.music.clip, what: "sfx plan music" });
  }
  const calibration = calibrationHits(referenced);
  for (const h of calibration) {
    if (mode === "replica") warn("calibration", `${h.what}: ${h.file} is calibration-only (${h.why}); allowed because the plan is a replica`, h.scene);
    else err("calibration", `${h.what}: ${h.file} is calibration-only (${h.why}). Source frames rebuild a replica and never enter a piece; build this piece's plates with imagery.py generate, score, grade and matte, or set "mode": "replica" if this plan is the replica.`, h.scene);
  }

  const stats = {
    scenes: scenes.length,
    moves: signature + novel,
    signature,
    novel,
    words: words.length,
    beats: beats && !beats.error ? beats.beats.length : 0,
    media: media.filter((r) => r.abs).length,
    mode,
    styleDir: dir,
  };
  return { ok: errors.length === 0, errors, warnings, stats, style, resolved, beats: beats && !beats.error ? beats : null, media, calibration, mode };
}

// ---------------------------------------------------------------------------

export function parseArgs(argv, flags = []) {
  const args = argv.slice(2);
  const out = { _: [] };
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a.startsWith("--")) {
      const name = a.slice(2);
      if (flags.includes(name)) out[name] = args[++i];
      else out[name] = true;
    } else out._.push(a);
  }
  return out;
}

export function printReport(result, planPath, log = console.log) {
  const line = (mark, e) => `  ${mark} ${e.scene ? `[${e.scene}] ` : ""}${e.message}`;
  log(`Scene plan  ${planPath}`);
  log(`  style ${result.stats.styleDir}`);
  log(`  ${result.stats.scenes} scene(s), ${result.stats.moves} move(s): ${result.stats.signature} signature, ${result.stats.novel} novel; mode ${result.stats.mode ?? "piece"}`);
  if (result.stats.words || result.stats.beats || result.stats.media) log(`  ${result.stats.words ?? 0} VO word(s), ${result.stats.beats ?? 0} beat(s), ${result.stats.media ?? 0} media reference(s)`);
  if (result.errors.length) {
    log(`Errors (${result.errors.length})`);
    for (const e of result.errors) log(line("x", e));
  }
  if (result.warnings.length) {
    log(`Warnings (${result.warnings.length})`);
    for (const e of result.warnings) log(line("!", e));
  }
  log(result.ok ? "plan gate open" : "plan gate closed");
}

function main(argv) {
  const args = parseArgs(argv, ["style-dir", "beats", "sfx"]);
  const planPath = args._[0];
  if (!planPath) {
    console.error("usage: node toolkit/validate-plan.mjs <plan.json> [--style-dir <dir>] [--beats <json>] [--sfx <sfx-plan.json>] [--json]");
    process.exit(2);
  }
  let loaded;
  try {
    loaded = loadPlan(planPath);
  } catch (e) {
    console.error(e.message);
    process.exit(2);
  }
  const result = validatePlan(loaded.plan, {
    planDir: loaded.dir,
    styleDir: args["style-dir"] ?? null,
    beats: args.beats ?? null,
    sfxPath: args.sfx ? resolve(process.cwd(), args.sfx) : null,
  });
  if (args.json) {
    const { style, resolved, ...rest } = result;
    console.log(JSON.stringify({ plan: loaded.path, ...rest }, null, 2));
  } else {
    printReport(result, loaded.path);
  }
  process.exit(result.ok ? 0 : 1);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main(process.argv);
