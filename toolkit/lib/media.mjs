// Media references and the calibration guard, shared by validate-plan.mjs,
// storyboard.mjs and build-composition.mjs so the gate, the board and the
// render read the same files.
//
// A move prop is a media reference when its key is one of MEDIA_KEYS (src,
// plate, bg, fg, image and friends) or when it is any string ending in a media
// extension, at any depth of the props object. A style asset is a media url()
// in fonts.css, tokens.css or an inlined element file, or a string value in
// tokens.json ending in a media extension. Relative paths resolve beside the
// plan first and then in the style folder (an element file's own folder comes
// first for its url()s). Each resolved file is copied under assets/plates/ as
// <folder>-<stem>-<sha256 of the content, 8 hex><ext>, so the name is the same
// on every run for the same bytes and two bg.png from two mattes never collide,
// and the reference is rewritten to that relative path.

import { readFileSync, existsSync, statSync, realpathSync, mkdirSync, copyFileSync, readdirSync, rmSync } from "node:fs";
import { resolve, dirname, basename, extname, isAbsolute, join, sep } from "node:path";
import { createHash } from "node:crypto";

export const MEDIA_EXT = /\.(png|jpe?g|webp|svg|avif|gif|mp4|webm|mov)$/i;
export const MEDIA_KEYS = new Set(["src", "plate", "bg", "fg", "image", "bgClean", "poster", "video", "still", "mask"]);
export const PLATES_DIR = "assets/plates";
export const CALIBRATION_PREFIX = "calibration-only-";
export const CALIBRATION_MARKER = "CALIBRATION-ONLY.json";

const REMOTE = /^(?:[a-z][a-z0-9+.-]*:|\/\/|#)/i; // http:, https:, data:, blob:, protocol-relative, fragment

const isFile = (p) => {
  try { return statSync(p).isFile(); } catch { return false; }
};

// The first base the path exists under, or null.
export function resolveMedia(value, bases) {
  if (typeof value !== "string" || !value.trim() || REMOTE.test(value.trim())) return null;
  const v = value.trim();
  if (isAbsolute(v)) return isFile(v) ? v : null;
  for (const b of bases) {
    if (!b) continue;
    const p = resolve(b, v);
    if (isFile(p)) return p;
  }
  return null;
}

// Every string in a props object that names media: [{ path: ["bg"], value, keyed }].
// props.tweens is skipped because it holds GSAP vars, never files.
export function propMediaStrings(props, path = [], out = []) {
  if (Array.isArray(props)) {
    props.forEach((v, i) => {
      // a plain string inside an array (a frame list, say) is media when its extension says so
      if (typeof v === "string") {
        if (MEDIA_EXT.test(v.trim()) && !REMOTE.test(v.trim())) out.push({ path: [...path, i], value: v, keyed: false });
      } else propMediaStrings(v, [...path, i], out);
    });
  } else if (props && typeof props === "object") {
    for (const [k, v] of Object.entries(props)) {
      if (path.length === 0 && k === "tweens") continue;
      if (typeof v === "string") {
        const keyed = MEDIA_KEYS.has(k);
        if ((keyed || MEDIA_EXT.test(v.trim())) && !REMOTE.test(v.trim()) && v.trim()) out.push({ path: [...path, k], value: v, keyed });
      } else propMediaStrings(v, [...path, k], out);
    }
  }
  return out;
}

const CSS_URL = /url\(\s*(["']?)([^"')]+?)\1\s*\)/g;

function cssMediaUrls(css) {
  const out = [];
  for (const m of String(css ?? "").matchAll(CSS_URL)) if (MEDIA_EXT.test(m[2]) && !REMOTE.test(m[2])) out.push(m[2]);
  return out;
}

function tokenMediaStrings(tokens, path = [], out = []) {
  if (Array.isArray(tokens)) tokens.forEach((v, i) => tokenMediaStrings(v, [...path, i], out));
  else if (tokens && typeof tokens === "object") for (const [k, v] of Object.entries(tokens)) {
    if (typeof v === "string") { if (MEDIA_EXT.test(v.trim()) && !REMOTE.test(v.trim())) out.push({ path: [...path, k], value: v }); }
    else tokenMediaStrings(v, [...path, k], out);
  }
  return out;
}

// Every media reference a set of resolved scenes and a style make:
// [{ where, value, abs, kind: "prop" | "css" | "token", keyed }]. abs is null
// when the reference resolves nowhere.
export function mediaRefs({ scenes, style, planDir }) {
  const refs = [];
  const styleDir = style?.dir ?? null;
  for (const s of scenes ?? []) for (const m of s.moves ?? []) {
    for (const r of propMediaStrings(m.props ?? {})) {
      const abs = resolveMedia(r.value, [planDir, styleDir]);
      // A keyed prop with no media extension that resolves nowhere is a
      // label, not a file (a "src" naming a register, say), and is ignored.
      if (!abs && r.keyed && !MEDIA_EXT.test(r.value.trim())) continue;
      refs.push({ kind: "prop", where: `${s.id}: ${m.name} -> ${m.target} props.${r.path.join(".")}`, value: r.value, abs, keyed: r.keyed, scene: s.id });
    }
  }
  if (style) {
    for (const [name, css] of [["fonts.css", style.fontsCss], ["tokens.css", style.tokensCss]]) {
      for (const u of cssMediaUrls(css)) refs.push({ kind: "css", where: `${name} url(${u})`, value: u, abs: resolveMedia(u, [styleDir, planDir]) });
    }
    for (const t of tokenMediaStrings(style.tokens ?? {})) refs.push({ kind: "token", where: `tokens.json ${t.path.join(".")}`, value: t.value, abs: resolveMedia(t.value, [styleDir, planDir]) });
  }
  const seen = new Set();
  for (const s of scenes ?? []) for (const m of s.moves ?? []) {
    if (!m.file || seen.has(m.file)) continue;
    seen.add(m.file);
    let src = "";
    try { src = readFileSync(m.file, "utf8"); } catch { continue; }
    for (const u of cssMediaUrls(src)) refs.push({ kind: "css", where: `${basename(m.file)} url(${u})`, value: u, abs: resolveMedia(u, [dirname(m.file), styleDir, planDir]), file: m.file });
  }
  return refs;
}

// ---------------------------------------------------------------------------
// Calibration guard. A file is calibration-only when its name, or any folder on
// its path, starts with calibration-only-, or when any folder above it holds a
// CALIBRATION-ONLY.json marker (imagery.py plates-from-source writes the
// marker beside calibration-only-shot-NN.png and its matte folder, so the
// matte's bg.png and fg.png are caught through their parent). Symlinks are
// followed so a link cannot launder a source frame. Only a plan in
// "mode": "replica" may use one.
// ---------------------------------------------------------------------------

export function calibrationMark(file) {
  if (!file) return null;
  const paths = [resolve(file)];
  try { const real = realpathSync(file); if (real !== paths[0]) paths.push(real); } catch { /* not on disk */ }
  for (const p of paths) {
    const seg = p.split(sep).find((s) => s.toLowerCase().startsWith(CALIBRATION_PREFIX));
    if (seg) return `"${seg}" starts with ${CALIBRATION_PREFIX}`;
    let d = dirname(p);
    for (;;) {
      if (existsSync(join(d, CALIBRATION_MARKER))) return `${d} holds ${CALIBRATION_MARKER}`;
      const up = dirname(d);
      if (up === d) break;
      d = up;
    }
  }
  return null;
}

// [{ file, what, why }] for every calibration-only file in the list.
export function calibrationHits(files) {
  const out = [];
  const seen = new Set();
  for (const f of files) {
    if (!f?.file || seen.has(f.file)) continue;
    seen.add(f.file);
    const why = calibrationMark(f.file);
    if (why) out.push({ ...f, why });
  }
  return out;
}

export const planMode = (plan) => (plan?.mode === "replica" ? "replica" : "piece");

// ---------------------------------------------------------------------------
// Staging: copy every resolved reference under <dest>/assets/plates and return
// the scenes, tokens and a CSS rewriter that point at the copies.
// ---------------------------------------------------------------------------

const clean = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "x";

export function plateName(abs) {
  const hash = createHash("sha256").update(readFileSync(abs)).digest("hex").slice(0, 8);
  const ext = extname(abs).toLowerCase();
  return `${clean(basename(dirname(abs)))}-${clean(basename(abs, extname(abs)))}-${hash}${ext}`;
}

function setPath(obj, path, value) {
  let o = obj;
  for (let i = 0; i < path.length - 1; i++) o = o[path[i]];
  o[path[path.length - 1]] = value;
}

export function stageMedia({ scenes, style, planDir }) {
  const refs = mediaRefs({ scenes, style, planDir });
  const files = new Map(); // abs -> name
  const nameOf = (abs) => {
    if (!files.has(abs)) files.set(abs, plateName(abs));
    return `${PLATES_DIR}/${files.get(abs)}`;
  };
  const unresolved = refs.filter((r) => !r.abs);

  const out = (scenes ?? []).map((s) => ({
    ...s,
    moves: s.moves.map((m) => {
      const props = JSON.parse(JSON.stringify(m.props ?? {}));
      for (const r of propMediaStrings(m.props ?? {})) {
        const abs = resolveMedia(r.value, [planDir, style?.dir]);
        if (abs) setPath(props, r.path, nameOf(abs));
      }
      return { ...m, props };
    }),
  }));

  let tokens = style?.tokens ?? null;
  if (tokens) {
    tokens = JSON.parse(JSON.stringify(tokens));
    for (const t of tokenMediaStrings(style.tokens)) {
      const abs = resolveMedia(t.value, [style.dir, planDir]);
      if (abs) setPath(tokens, t.path, nameOf(abs));
    }
  }

  // Rewrites media url()s in a CSS or element source; bases in priority order.
  const rewriteCss = (css, bases) => String(css ?? "").replace(CSS_URL, (whole, q, u) => {
    if (!MEDIA_EXT.test(u) || REMOTE.test(u)) return whole;
    const abs = resolveMedia(u, bases);
    return abs ? `url(${q}${nameOf(abs)}${q})` : whole;
  });
  const styleBases = [style?.dir, planDir];
  const elementBases = (file) => [dirname(file), style?.dir, planDir];

  // Touch every css ref now so files holds the full set before copying.
  for (const r of refs) if (r.abs) nameOf(r.abs);

  return {
    refs,
    unresolved,
    files,
    scenes: out,
    style: style ? { ...style, tokens } : style,
    rewriteStyleCss: (css) => rewriteCss(css, styleBases),
    rewriteElement: (src, file) => rewriteCss(src, elementBases(file)),
  };
}

// Copy into <dest>/assets/plates. With prune, files there that the plan no
// longer references are removed (the folder belongs to the builder). A file
// already present under its content-hashed name is left alone, so a re-run
// does not touch it and the canvas does not reload frames for nothing.
export function copyMedia(files, dest, { prune = true } = {}) {
  const dir = resolve(dest, PLATES_DIR);
  if (!files.size && !existsSync(dir)) return { dir, copied: 0, removed: [] };
  mkdirSync(dir, { recursive: true });
  const wanted = new Set(files.values());
  let copied = 0;
  for (const [abs, name] of files) {
    const to = resolve(dir, name);
    if (existsSync(to) && statSync(to).size === statSync(abs).size) continue;
    copyFileSync(abs, to);
    copied++;
  }
  const removed = [];
  if (prune) for (const f of readdirSync(dir)) {
    if (!wanted.has(f)) { rmSync(resolve(dir, f), { recursive: true, force: true }); removed.push(f); }
  }
  return { dir, copied, removed };
}
