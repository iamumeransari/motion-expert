#!/usr/bin/env node
// Scene plan -> storyboard board for the review canvas.
//
//   node toolkit/storyboard.mjs <plan.json> --out <board-folder> [--name <board>]
//        [--style-dir <dir>] [--sfx <sfx-plan.json>] [--register] [--force]
//
// Writes one standalone HTML per scene (01-<id>.html, 02-<id>.html, ...) under
// the storyboard-canvas contract, plus board.json and a local gsap.min.js. Each
// frame inlines the style's tokens and the library elements its moves use,
// builds a paused GSAP timeline by calling each element's animate(), registers
// it as window.__timelines = { main: tl } for the canvas scrubber, and carries a
// toggleable review overlay that never reaches a render. Re-running into the
// same folder rewrites only frames whose content changed and keeps the
// canvas's .canvas/ comment state.

import { existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { resolve, isAbsolute } from "node:path";
import { spawnSync } from "node:child_process";
import { homedir } from "node:os";
import { pathToFileURL } from "node:url";
import { loadPlan, validatePlan, printReport, parseArgs } from "./validate-plan.mjs";
import { loadSfx } from "./lib/sfx.mjs";
import { styleCss, elementBlocks, runtimeScript, buildFrame, copyGsap, writeIfChanged, frameLabel, rel } from "./lib/scene-html.mjs";

const CANVAS = resolve(homedir(), "storyboard-canvas", "bin", "canvas");
const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export function frameFile(scene) {
  return `${String(scene.index + 1).padStart(2, "0")}-${scene.id}.html`;
}

function moveNote(m) {
  const tag = m.kind === "signature" ? "signature" : m.kind === "composed" ? "novel, composed" : m.kind === "placeholder" ? "novel, not built" : "novel";
  const at = m.word ? `on "${m.word.w}" (${m.tRef})` : `at ${m.t.toFixed(2)}s`;
  return `${m.name} -> ${m.target} ${at} [${tag}]`;
}

export async function buildBoard(planPath, { out, name = null, styleDir = null, sfxPath = null, force = false, log = console.log } = {}) {
  const { plan, path, dir: planDir } = loadPlan(planPath);
  const result = validatePlan(plan, { planDir, styleDir });
  if (!result.ok) {
    printReport(result, path, log);
    if (!force) throw new Error("plan gate is closed; fix the plan or pass --force to draw the board anyway");
    log("--force: drawing the board from a plan that does not pass the gate");
  } else {
    for (const w of result.warnings) log(`! ${w.scene ? `[${w.scene}] ` : ""}${w.message}`);
  }
  const { style, resolved: scenes } = result;

  const sfx = loadSfx(sfxPath ? resolve(process.cwd(), sfxPath) : null, plan, scenes, planDir);
  for (const w of sfx.warnings) log(`! sfx: ${w}`);
  for (const e of sfx.errors) log(`x sfx: ${e}`);

  const outDir = isAbsolute(out) ? out : resolve(process.cwd(), out);
  mkdirSync(outDir, { recursive: true });
  copyGsap(outDir);

  const notes = [];
  const css = styleCss(style, notes);
  const runtime = runtimeScript();
  const planRel = rel(outDir, path);

  const frames = [];
  const wanted = new Set();
  let changed = 0;
  for (const scene of scenes) {
    const file = frameFile(scene);
    wanted.add(file);
    const elements = elementBlocks([scene], notes);
    const events = sfx.events.filter((e) => e.sceneId === scene.id);
    const html = buildFrame({ scene, plan, style, css, elements, runtime, sfx: events, planRel });
    if (writeIfChanged(resolve(outDir, file), html)) changed++;

    const lines = [
      `Feeling: ${scene.feeling}`,
      `VO: ${scene.vo_line ? `"${scene.vo_line}"` : "(silent)"}`,
      `Moves: ${scene.moves.length ? scene.moves.map(moveNote).join("; ") : "none"}`,
    ];
    if (events.length) lines.push(`SFX: ${events.map((e) => `${e.class} ${e.clipName} at ${e.local.toFixed(2)}s${e.gain_db ? ` ${e.gain_db}dB` : ""}${e.moveName ? ` on ${e.moveName}` : ""}`).join("; ")}`);
    if (scene.notes) lines.push(`Notes: ${scene.notes}`);
    frames.push({ file, title: frameLabel(scene), duration: scene.duration, notes: lines.join("\n") });
  }

  // Scenes cut from the plan lose their frame; nothing else in the folder is touched.
  for (const f of readdirSync(outDir)) {
    if (/^\d{2,}-.+\.html$/.test(f) && !wanted.has(f)) {
      rmSync(resolve(outDir, f));
      log(`removed ${f}: no longer in the plan`);
    }
  }

  const board = {
    title: plan.title,
    size: `${plan.format.width}x${plan.format.height}`,
    plan: path,
    style: plan.style,
    styleDir: result.stats.styleDir,
    duration: plan.duration,
    sfx: sfx.source,
    music: sfx.music ? `${sfx.music.clipName} at ${sfx.music.gain_db}dB, ducking ${sfx.music.duck_db_under_vo}dB under the VO` : null,
    frames,
  };
  writeIfChanged(resolve(outDir, "board.json"), JSON.stringify(board, null, 2) + "\n");
  for (const n of notes) log(`! ${n}`);

  const boardName = name ?? slug(plan.title);
  return { outDir, boardName, frames, changed, result, sfx };
}

export function registerBoard(outDir, boardName, log = console.log) {
  const res = spawnSync(CANVAS, ["add", outDir, "--name", boardName], { encoding: "utf8" });
  if (res.status !== 0) throw new Error(`canvas add failed: ${(res.stderr || res.stdout || "").trim()}`);
  const url = res.stdout.trim().split("\n").pop();
  log(`board "${boardName}" is on the canvas: ${url}`);
  log("");
  log("Arm the comment monitor now, and re-arm it whenever it expires while review continues:");
  log(`  Monitor({ command: "${CANVAS} watch ${boardName}", description: "storyboard comments on ${boardName}", timeout_ms: 1800000 })`);
  return url;
}

async function main(argv) {
  const args = parseArgs(argv, ["out", "name", "style-dir", "sfx"]);
  const planPath = args._[0];
  if (!planPath || !args.out) {
    console.error("usage: node toolkit/storyboard.mjs <plan.json> --out <board-folder> [--name <board>] [--style-dir <dir>] [--sfx <sfx-plan.json>] [--register] [--force]");
    process.exit(2);
  }
  try {
    const { outDir, boardName, frames, changed } = await buildBoard(planPath, {
      out: args.out, name: args.name ?? null, styleDir: args["style-dir"] ?? null, sfxPath: args.sfx ?? null, force: !!args.force,
    });
    console.log(`${frames.length} frame(s) in ${outDir} (${changed} written, the rest unchanged)`);
    for (const f of frames) console.log(`  ${f.file}  ${f.duration}s  ${f.title}`);
    if (args.register) registerBoard(outDir, boardName);
    else console.log(`register with: ${CANVAS} add ${outDir} --name ${boardName}`);
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main(process.argv);
