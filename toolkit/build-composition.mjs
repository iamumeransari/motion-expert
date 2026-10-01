#!/usr/bin/env node
// Approved scene plan -> HyperFrames project.
//
//   node toolkit/build-composition.mjs <plan.json> --out <dir>
//        [--style-dir <dir>] [--sfx <sfx-plan.json>]
//
// Writes <dir>/index.html: a standalone root with data-composition-id, width,
// height and duration, every scene as a clip, one paused timeline on
// window.__timelines["main"] built by the same runtime and element code the
// storyboard frames ran, the voice-over as <audio id="vo">, the music bed with
// its gain ducked under the voice, and each sound effect as its own audio clip.
// Media is copied under <dir>/assets so the project renders on its own.
// Run only after Umer has approved the board.

import { existsSync, mkdirSync, copyFileSync, writeFileSync, rmSync } from "node:fs";
import { resolve, isAbsolute, extname, basename } from "node:path";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { loadPlan, validatePlan, printReport, parseArgs } from "./validate-plan.mjs";
import { loadSfx, duckLane } from "./lib/sfx.mjs";
import { styleCss, elementBlocks, runtimeScript, buildComposition, copyGsap } from "./lib/scene-html.mjs";

const MAX_VOLUME = 3.98; // +12 dB, the HyperFrames ceiling on data-volume

function probeDuration(file) {
  const r = spawnSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", file], { encoding: "utf8" });
  const d = Number(r.stdout.trim());
  if (r.status !== 0 || !isFinite(d)) throw new Error(`ffprobe could not read ${file}`);
  return d;
}

function must(cmd, args, what) {
  const r = spawnSync(cmd, args, { encoding: "utf8" });
  if (r.status !== 0) throw new Error(`${what} failed: ${(r.stderr || r.stdout || "").trim().split("\n").slice(-4).join(" ")}`);
}

const r3 = (n) => Number(n.toFixed(3));
const dbToVolume = (db) => r3(Math.min(MAX_VOLUME, Math.pow(10, db / 20)));

export async function buildProject(planPath, { out, styleDir = null, sfxPath = null, log = console.log } = {}) {
  const { plan, path, dir: planDir } = loadPlan(planPath);
  const result = validatePlan(plan, { planDir, styleDir });
  const blockers = [];
  if (!result.ok) blockers.push("the plan gate is closed");
  const { style, resolved: scenes } = result;
  for (const s of scenes) for (const m of s.moves) {
    if (m.kind === "placeholder") blockers.push(`${s.id}: novel move "${m.name}" is not built (no library/${m.name}.html beside the plan, no props.tweens)`);
  }
  const voAudio = plan.vo?.audio ? (isAbsolute(plan.vo.audio) ? plan.vo.audio : resolve(planDir, plan.vo.audio)) : null;
  if (!voAudio) blockers.push("vo.audio is not set; a piece renders with its voice");
  const sfx = loadSfx(sfxPath ? resolve(process.cwd(), sfxPath) : null, plan, scenes, planDir);
  for (const e of sfx.errors) blockers.push(`sfx: ${e}`);
  if (blockers.length) {
    if (!result.ok) printReport(result, path, log);
    throw new Error(`refusing to build:\n  ${blockers.join("\n  ")}`);
  }
  for (const w of [...result.warnings.map((w) => `${w.scene ? `[${w.scene}] ` : ""}${w.message}`), ...sfx.warnings.map((w) => `sfx: ${w}`)]) log(`! ${w}`);

  const outDir = isAbsolute(out) ? out : resolve(process.cwd(), out);
  const assets = resolve(outDir, "assets");
  rmSync(assets, { recursive: true, force: true });
  mkdirSync(resolve(assets, "sfx"), { recursive: true });
  copyGsap(outDir);

  const total = plan.duration;
  const audio = [];

  // Voice-over
  const voName = `vo${extname(voAudio)}`;
  copyFileSync(voAudio, resolve(assets, voName));
  const voDur = probeDuration(voAudio);
  if (voDur > total + 0.05) log(`! the voice-over runs ${voDur.toFixed(2)}s and the piece ${total}s; the tail is cut`);
  audio.push({ id: "vo", src: `assets/${voName}`, start: 0, duration: r3(Math.min(voDur, total)), track: 10, group: "voiceover", volume: 1 });

  // Music bed: level as a gain stage, ducked under the voice by automating it,
  // so the lane is in dB and the bed breathes back between phrases.
  if (sfx.music) {
    const name = `music${extname(sfx.music.clip)}`;
    copyFileSync(sfx.music.clip, resolve(assets, name));
    const dur = r3(Math.min(probeDuration(sfx.music.clip), total));
    const base = Math.max(-60, Math.min(12, sfx.music.gain_db));
    const points = duckLane(plan.vo.words, dur, base, sfx.music.duck_db_under_vo);
    audio.push({
      id: "music", src: `assets/${name}`, start: 0, duration: dur, track: 11, group: "music",
      fxChain: { version: 1, nodes: [{ type: "gain", id: "n1", label: "Bed level, ducked under VO", params: { gain: base } }] },
      automation: { version: 1, lanes: [{ target: "fx.n1.gain", points }] },
    });
  }

  // Sound effects, one clip each on its own lane. HyperFrames has no pan
  // effect, so a panned event is rendered to a derived stereo file first.
  sfx.events.forEach((e, i) => {
    let src = e.clip;
    let name = `${e.id}-${basename(e.clip)}`;
    if (e.pan) {
      name = `${e.id}-${basename(e.clip, extname(e.clip))}-pan${e.pan}.wav`;
      const l = e.pan > 0 ? 1 - e.pan : 1;
      const r = e.pan < 0 ? 1 + e.pan : 1;
      must("ffmpeg", ["-v", "error", "-y", "-i", e.clip, "-af", `aformat=channel_layouts=stereo,pan=stereo|c0=${l.toFixed(3)}*c0|c1=${r.toFixed(3)}*c1`, resolve(assets, "sfx", name)], `panning ${e.id}`);
      src = resolve(assets, "sfx", name);
    } else {
      copyFileSync(src, resolve(assets, "sfx", name));
    }
    const dur = r3(Math.min(probeDuration(src), total - e.t));
    audio.push({ id: e.id, src: `assets/sfx/${name}`, start: e.t, duration: dur, track: 20 + i, group: "sfx", volume: dbToVolume(e.gain_db) });
  });

  const notes = [];
  const html = buildComposition({
    plan, scenes, style,
    css: styleCss(style, notes),
    elements: elementBlocks(scenes, notes),
    runtime: runtimeScript(),
    audio,
  });
  writeFileSync(resolve(outDir, "index.html"), html);
  for (const n of notes) log(`! ${n}`);

  // What was built from what, for the compare loop and for anyone reading the
  // project later.
  writeFileSync(resolve(outDir, "build.json"), JSON.stringify({
    plan: path,
    style: plan.style,
    styleDir: result.stats.styleDir,
    sfxPlan: sfx.source,
    duration: total,
    format: plan.format,
    scenes: scenes.map((s) => ({ id: s.id, start: s.start, duration: s.duration, moves: s.moves.map((m) => ({ name: m.name, target: m.target, kind: m.kind, t: m.tAbs })) })),
    audio: audio.map(({ fxChain, automation, ...a }) => ({ ...a, ducking: automation ? automation.lanes[0].points : undefined })),
    sfx: sfx.events.map((e) => ({ id: e.id, t: e.t, class: e.class, clip: e.clipName, gain_db: e.gain_db, pan: e.pan, move: e.move, origin: e.origin })),
    silenced: sfx.silenced.map((e) => ({ t: e.t, class: e.class, move: e.move, reason: e.reason })),
  }, null, 2) + "\n");

  return { outDir, audio, scenes, sfx };
}

async function main(argv) {
  const args = parseArgs(argv, ["out", "style-dir", "sfx"]);
  const planPath = args._[0];
  if (!planPath || !args.out) {
    console.error("usage: node toolkit/build-composition.mjs <plan.json> --out <dir> [--style-dir <dir>] [--sfx <sfx-plan.json>]");
    process.exit(2);
  }
  try {
    const { outDir, audio, scenes } = await buildProject(planPath, { out: args.out, styleDir: args["style-dir"] ?? null, sfxPath: args.sfx ?? null });
    console.log(`composition written to ${outDir}/index.html`);
    console.log(`  ${scenes.length} scene clip(s), ${audio.length} audio clip(s): ${audio.map((a) => `${a.id}@${a.start}s`).join(", ")}`);
    console.log(`render with: toolkit/render.sh ${outDir} <out.mp4>`);
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main(process.argv);
