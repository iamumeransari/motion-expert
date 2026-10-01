// Scene HTML generation shared by storyboard.mjs (one frame per scene) and
// build-composition.mjs (every scene as a clip in one composition). Both call
// the same functions for CSS, element inlining, scene markup and the timeline
// build, so the board Umer approves runs the same code as the render.

import { readFileSync, existsSync, writeFileSync, mkdirSync, copyFileSync } from "node:fs";
import { resolve, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
export const GSAP_FILE = resolve(HERE, "..", "vendor", "gsap.min.js");

// Layouts the toolkit ships. The scene root is also its stage, so a clip holds
// no static children (HyperFrames lint asks a timed element with nested markup
// to become a sub-composition). A style overrides or adds layouts in tokens.css
// with .me-stage.layout-<name> rules, which come later in the cascade.
export const BASE_CSS = `
.me-scene.me-stage { position: absolute; inset: 0; overflow: hidden; box-sizing: border-box; padding: var(--space-margin, 96px); display: flex; flex-direction: column; gap: var(--space-gap, 32px); background: var(--scene-bg, var(--color-bg, #000)); color: var(--color-fg, #fff); }
.me-stage.layout-center { align-items: center; justify-content: center; text-align: center; }
.me-stage.layout-stack { align-items: flex-start; justify-content: center; }
.me-stage.layout-split { display: grid; grid-template-columns: 1fr 1fr; align-items: center; }
.me-stage.layout-free, .me-stage.layout-full { display: block; padding: 0; }
.me-stage.layout-full > * { position: absolute; inset: 0; }
.el-grammar { display: block; }
.el-grammar .w { display: inline-block; margin-right: 0.25em; }
.el-placeholder { box-sizing: border-box; max-width: 80%; padding: 32px; border: 4px dashed #ff9f1c; color: #ff9f1c; font: 500 32px/1.3 system-ui, sans-serif; text-align: left; }
.el-placeholder .ph-note { margin-top: 12px; font-size: 24px; opacity: 0.8; }
`.trim();

export function esc(text) {
  return String(text ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// A </script> inside a JSON literal would close the surrounding tag.
export function jsonLiteral(value) {
  return JSON.stringify(value).replace(/<\//g, "<\\/");
}

export function rationalFps(fps) {
  const n = Number(fps);
  if (!isFinite(n) || n <= 0) return "30";
  if (Number.isInteger(n)) return String(n);
  for (const [target, rational] of [[24000 / 1001, "24000/1001"], [30000 / 1001, "30000/1001"], [60000 / 1001, "60000/1001"]]) {
    if (Math.abs(n - target) < 0.01) return rational;
  }
  return String(n);
}

// ---------------------------------------------------------------------------
// Script folding, ported from ~/motion-ui/pipeline/generate-scenes.mjs. The
// HyperFrames CLI counts <script> lines against a 300 structural line ceiling,
// so inlined scripts are stripped of comments and folded onto one line. Every
// result is parsed before use, and a script that will not parse goes in
// verbatim rather than silently broken.
// ---------------------------------------------------------------------------

const REGEX_MAY_FOLLOW = /(^|[([{,;:=!&|?+\-*%~^<>])$|\b(return|typeof|instanceof|in|of|new|delete|void|case|do|else|yield|await)$/;

export function stripComments(src) {
  let out = "";
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    const next = src[i + 1];
    if (c === "/" && next === "/") { while (i < src.length && src[i] !== "\n") i++; continue; }
    if (c === "/" && next === "*") {
      i += 2;
      while (i < src.length && !(src[i] === "*" && src[i + 1] === "/")) i++;
      i += 2;
      out += " ";
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {
      const quote = c;
      out += c;
      i++;
      while (i < src.length) {
        out += src[i];
        if (src[i] === "\\") { out += src[i + 1] ?? ""; i += 2; continue; }
        if (src[i] === quote) { i++; break; }
        i++;
      }
      continue;
    }
    if (c === "/" && REGEX_MAY_FOLLOW.test(out.replace(/\s+$/, ""))) {
      out += c;
      i++;
      let inClass = false;
      while (i < src.length) {
        out += src[i];
        if (src[i] === "\\") { out += src[i + 1] ?? ""; i += 2; continue; }
        if (src[i] === "[") inClass = true;
        else if (src[i] === "]") inClass = false;
        else if (src[i] === "/" && !inClass) { i++; break; }
        i++;
      }
      while (i < src.length && /[a-z]/.test(src[i])) { out += src[i]; i++; }
      continue;
    }
    out += c;
    i++;
  }
  return out;
}

export function minifyScript(src) {
  const stripped = stripComments(src);
  const folded = stripped.split("\n").map((l) => l.trim()).filter(Boolean).join(" ").replace(/\s{2,}/g, " ");
  for (const candidate of [folded, stripped.split("\n").map((l) => l.trim()).filter(Boolean).join("\n"), src]) {
    try {
      new Function(candidate); // eslint-disable-line no-new-func
      return { code: candidate, minified: candidate !== src };
    } catch { /* try the next, less aggressive form */ }
  }
  return { code: src, minified: false };
}

export function inlineElement(source, name, notes) {
  return source.replace(/<script(\s[^>]*)?>([\s\S]*?)<\/script>/gi, (whole, attrs, body) => {
    const { code, minified } = minifyScript(body);
    if (!minified) notes.push(`${name}: script could not be folded and went in verbatim; it counts against the 300 line ceiling`);
    return `<script${attrs ?? ""}>${code}</script>`;
  });
}

// ---------------------------------------------------------------------------

// fonts.css then tokens.css, with any relative font url embedded as base64 so
// a frame or a composition is self-contained wherever it is served from.
export function styleCss(style, notes = []) {
  const parts = [];
  for (const [name, css0] of [["fonts.css", style.fontsCss], ["tokens.css", style.tokensCss]]) {
    if (!css0) continue;
    const css = css0.replace(/url\(\s*["']?((?!data:)[^"')]+\.(?:woff2|woff|otf|ttf))["']?\s*\)/g, (whole, rel) => {
      const asset = resolve(style.dir, rel);
      if (!existsSync(asset)) {
        notes.push(`${name} points at ${rel}, which does not exist`);
        return whole;
      }
      const mime = asset.endsWith(".woff2") ? "font/woff2" : asset.endsWith(".woff") ? "font/woff" : asset.endsWith(".otf") ? "font/otf" : "font/ttf";
      return `url(data:${mime};base64,${readFileSync(asset).toString("base64")})`;
    });
    parts.push(css.trim());
  }
  return parts.join("\n\n");
}

export function runtimeScript() {
  return minifyScript(readFileSync(resolve(HERE, "runtime.js"), "utf8")).code;
}

// Element files for the given scenes, each once, in first-use order.
export function elementBlocks(scenes, notes = []) {
  const seen = new Map();
  for (const s of scenes) for (const m of s.moves) if (m.file && !seen.has(m.file)) seen.set(m.file, m.name);
  return [...seen].map(([file, name]) => inlineElement(readFileSync(file, "utf8").trim(), name, notes));
}

// What the runtime needs to build a scene, and nothing that only review uses.
export function sceneSpec(scene) {
  return {
    id: scene.id,
    duration: scene.duration,
    moves: scene.moves.map((m) => ({ name: m.name, key: m.key, kind: m.kind, target: m.target, t: m.t, props: m.props, novel: m.novel, grammar_note: m.grammar_note })),
  };
}

export function frameInit(style, plan) {
  return { tokens: style.tokens ?? {}, frame: { w: plan.format.width, h: plan.format.height } };
}

// The scene root. In a composition it is also a clip.
export function sceneSection(scene, { clip = false } = {}) {
  const attrs = [
    `id="scene-${esc(scene.id)}"`,
    `class="${clip ? "clip " : ""}me-scene me-stage layout-${esc(scene.layout)}"`,
    `data-scene="${esc(scene.id)}"`,
    `data-feeling="${esc(scene.feeling)}"`,
  ];
  if (clip) attrs.push(`data-start="${scene.start}"`, `data-duration="${scene.duration}"`, `data-track-index="0"`);
  if (scene.background) attrs.push(`style="--scene-bg: ${esc(scene.background)}"`);
  return `<section ${attrs.join(" ")}></section>`;
}

export function frameLabel(scene) {
  return `${String(scene.index + 1).padStart(2, "0")} ${scene.title}`;
}

// ---------------------------------------------------------------------------
// A storyboard frame: one scene, its own paused timeline, the review overlay.
// ---------------------------------------------------------------------------

export function buildFrame({ scene, plan, style, css, elements, runtime, sfx = [], planRel = "" }) {
  const { width: W, height: H } = plan.format;
  const init = frameInit(style, plan);
  const review = {
    id: scene.id,
    label: frameLabel(scene),
    duration: scene.duration,
    feeling: scene.feeling,
    vo_line: scene.vo_line,
    words: scene.words,
    sfx: sfx.map((e) => ({ local: e.local, class: e.class, clipName: e.clipName, gain_db: e.gain_db, move: e.moveName, target: e.target })),
  };
  const overlayCss = readFileSync(resolve(HERE, "overlay.css"), "utf8");
  const overlayJs = minifyScript(readFileSync(resolve(HERE, "overlay.js"), "utf8")).code;
  const mrFs = Math.round(Math.min(W, H) / 52);
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="frame-size" content="${W}x${H}" />
    <meta name="viewport" content="width=${W}, height=${H}" />
    <title>${esc(frameLabel(scene))}</title>
    <!-- generated by toolkit/storyboard.mjs from ${esc(planRel)}. Change the plan or the library element and regenerate; the canvas hot-reloads. -->
    <script src="gsap.min.js"></script>
    <style>
html, body { margin: 0; padding: 0; background: #000; }
#frame { position: relative; width: ${W}px; height: ${H}px; overflow: hidden; --mr-fs: ${mrFs}px; }
${css}

${BASE_CSS}
    </style>
    <style>
${overlayCss}
    </style>
    <script>${runtime}</script>
${elements.join("\n")}
  </head>
  <body>
    <div id="frame">
    ${sceneSection(scene)}
    </div>
    <script>
      (function () {
        var M = window.__motionExpert;
        var init = ${jsonLiteral(init)};
        M.init(init.tokens, init.frame);
        var spec = ${jsonLiteral(sceneSpec(scene))};
        var tl = gsap.timeline({ paused: true });
        M.buildScene(document.getElementById("scene-${scene.id}"), tl, 0, spec);
        M.finish(tl, spec.duration);
        window.__timelines = { main: tl };
      })();
    </script>
    <script>window.__review = ${jsonLiteral(review)};</script>
    <script>${overlayJs}</script>
  </body>
</html>
`;
}

// ---------------------------------------------------------------------------
// The composition: every scene as a clip on one paused timeline, VO, music and
// sound effects as audio clips. No overlay, no clocks, no rAF.
// ---------------------------------------------------------------------------

export function buildComposition({ plan, scenes, style, css, elements, runtime, audio = [] }) {
  const { width: W, height: H, fps } = plan.format;
  const init = frameInit(style, plan);
  const specs = scenes.map((s) => ({ start: s.start, spec: sceneSpec(s) }));
  const audioTags = audio.map((a) => {
    const attrs = [`id="${a.id}"`, `src="${esc(a.src)}"`, `data-start="${a.start}"`, `data-duration="${a.duration}"`, `data-track-index="${a.track}"`];
    if (a.mediaStart) attrs.push(`data-media-start="${a.mediaStart}"`);
    if (a.volume !== undefined) attrs.push(`data-volume="${a.volume}"`);
    if (a.group) attrs.push(`data-audio-group="${a.group}"`);
    if (a.fxChain) attrs.push(`data-fx-chain="${esc(JSON.stringify(a.fxChain))}"`);
    if (a.automation) attrs.push(`data-automation="${esc(JSON.stringify(a.automation))}"`);
    return `    <audio ${attrs.join(" ")}></audio>`;
  });
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=${W}, height=${H}" />
    <title>${esc(plan.title)}</title>
    <!-- generated by toolkit/build-composition.mjs from the approved plan; regenerate rather than edit -->
    <script src="gsap.min.js"></script>
    <style>
body { margin: 0; background: #000; }
#root { position: relative; width: ${W}px; height: ${H}px; overflow: hidden; background: var(--color-bg, #000); }
${css}

${BASE_CSS}
    </style>
    <script>${runtime}</script>
${elements.join("\n")}
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="${plan.duration}" data-fps="${rationalFps(fps)}" data-width="${W}" data-height="${H}">
    ${scenes.map((s) => sceneSection(s, { clip: true })).join("\n    ")}
${audioTags.join("\n")}
    </div>
    <script>
      (function () {
        var M = window.__motionExpert;
        var init = ${jsonLiteral(init)};
        M.init(init.tokens, init.frame);
        var scenes = ${jsonLiteral(specs)};
        var tl = gsap.timeline({ paused: true });
        for (var i = 0; i < scenes.length; i++) {
          var s = scenes[i];
          M.buildScene(document.getElementById("scene-" + s.spec.id), tl, s.start, s.spec);
        }
        M.finish(tl, ${plan.duration});
        window.__timelines["main"] = tl;
      })();
    </script>
  </body>
</html>
`;
}

// Copied only when missing or different, so a re-run does not touch a file
// every frame loads and make the canvas reload the whole board.
export function copyGsap(dir) {
  mkdirSync(dir, { recursive: true });
  const dest = resolve(dir, "gsap.min.js");
  if (existsSync(dest) && readFileSync(dest).equals(readFileSync(GSAP_FILE))) return;
  copyFileSync(GSAP_FILE, dest);
}

// Write only when the content changed, so the canvas hot-reloads the frames
// that moved and leaves the rest where Umer had them scrubbed.
export function writeIfChanged(file, content) {
  if (existsSync(file) && readFileSync(file, "utf8") === content) return false;
  writeFileSync(file, content);
  return true;
}

export function rel(from, to) {
  return relative(from, to) || ".";
}
