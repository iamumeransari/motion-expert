#!/usr/bin/env node
// The plan gate. Checks a scene plan against schema/scene-plan.schema.json and
// against what a shape cannot say: every move resolves to a library element or
// is marked novel with a grammar note, every time lands inside its scene, every
// word reference exists, the scenes tile the piece, and grammar-composed tweens
// stay inside the style's primitive envelopes.
//
//   node toolkit/validate-plan.mjs <plan.json> [--style-dir <dir>] [--json]
//
// Adapted from ~/motion-ui/pipeline/validate-plan.mjs. Exits non-zero on any
// error. Warnings never fail the run; they are what the planning agent reads
// before the board goes up.

import { readFileSync, existsSync, readdirSync } from "node:fs";
import { resolve, dirname, isAbsolute, basename } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

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

const WORD_REF = /^word:(\d+)([+-]\d*\.?\d+)?$/;

export function resolveTime(t, words) {
  if (typeof t === "number") return { at: t };
  const m = WORD_REF.exec(String(t));
  if (!m) return { error: `t "${t}" is neither seconds nor word:<index>` };
  const index = Number(m[1]);
  const word = words?.[index];
  if (!word) return { error: `t "${t}" references word ${index}, but vo.words has ${words?.length ?? 0}` };
  return { at: word.start + (m[2] ? Number(m[2]) : 0), word: { index, w: word.w } };
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

export function resolvePlan(plan, style, planDir) {
  const words = plan.vo?.words ?? [];
  return (plan.scenes ?? []).map((scene, index) => {
    const moves = (scene.moves ?? []).map((move) => {
      const time = resolveTime(move.t, words);
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
        timeError: time.error ?? null,
        props: move.props ?? {},
        sfx: move.sfx ?? null,
      };
    });
    const sceneWords = words
      .map((w, i) => ({ ...w, i }))
      .filter((w) => w.end > scene.start + EPS && w.start < scene.start + scene.duration - EPS)
      .map((w) => ({ i: w.i, w: w.w, start: Number((w.start - scene.start).toFixed(4)), end: Number((w.end - scene.start).toFixed(4)) }));
    return { index, id: scene.id, title: scene.title, start: scene.start, duration: scene.duration, feeling: scene.feeling, vo_line: scene.vo_line, layout: scene.layout, background: scene.background ?? null, notes: scene.notes ?? "", moves, words: sceneWords };
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

export function validatePlan(plan, { planDir = process.cwd(), styleDir = null } = {}) {
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
  if (plan?.vo && (plan.vo.audio === null || plan.vo.audio === undefined)) {
    warn("vo", "vo.audio is not set: the board works, but build-composition will refuse the plan");
  } else if (typeof plan?.vo?.audio === "string") {
    const a = isAbsolute(plan.vo.audio) ? plan.vo.audio : resolve(planDir, plan.vo.audio);
    if (!existsSync(a)) err("vo", `vo.audio ${a} is not on disk`);
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
  const resolved = resolvePlan(plan, style, planDir);
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

  const stats = {
    scenes: scenes.length,
    moves: signature + novel,
    signature,
    novel,
    words: words.length,
    styleDir: dir,
  };
  return { ok: errors.length === 0, errors, warnings, stats, style, resolved };
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
  log(`  ${result.stats.scenes} scene(s), ${result.stats.moves} move(s): ${result.stats.signature} signature, ${result.stats.novel} novel`);
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
  const args = parseArgs(argv, ["style-dir"]);
  const planPath = args._[0];
  if (!planPath) {
    console.error("usage: node toolkit/validate-plan.mjs <plan.json> [--style-dir <dir>] [--json]");
    process.exit(2);
  }
  let loaded;
  try {
    loaded = loadPlan(planPath);
  } catch (e) {
    console.error(e.message);
    process.exit(2);
  }
  const result = validatePlan(loaded.plan, { planDir: loaded.dir, styleDir: args["style-dir"] ?? null });
  if (args.json) {
    const { style, resolved, ...rest } = result;
    console.log(JSON.stringify({ plan: loaded.path, ...rest }, null, 2));
  } else {
    printReport(result, loaded.path);
  }
  process.exit(result.ok ? 0 : 1);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main(process.argv);
