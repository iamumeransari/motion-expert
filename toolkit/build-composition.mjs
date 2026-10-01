#!/usr/bin/env node
// Approved scene plan -> HyperFrames project.
//
//   node toolkit/build-composition.mjs <plan.json> --out <dir>
//        [--style-dir <dir>] [--sfx <sfx-plan.json>] [--beats <json>]
//
// Writes <dir>/index.html: a standalone root with data-composition-id, width,
// height and duration, every scene as a clip, one paused timeline on
// window.__timelines["main"] built by the same runtime and element code the
// storyboard frames ran, the voice-over as <audio id="vo"> when the plan has
// one, the music bed with its gain ducked under the voice (or, with no voice,
// left as the piece's timing spine and only faded at the tail), and each sound
// effect as its own audio clip. Audio is copied under <dir>/assets, and every
// image or video the props or style assets reference under
// <dir>/assets/plates, so the project renders on its own. A piece (any plan
// not in "mode": "replica") that references a calibration-only file is
// refused here as well as at the gate. Run only after Umer has approved the
// board.

import { existsSync, mkdirSync, copyFileSync, writeFileSync, rmSync } from "node:fs";
import { resolve, isAbsolute, extname, basename } from "node:path";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { loadPlan, validatePlan, printReport, parseArgs } from "./validate-plan.mjs";
import { loadSfx, duckLane } from "./lib/sfx.mjs";
import { styleCss, elementBlocks, runtimeScript, buildComposition, copyGsap } from "./lib/scene-html.mjs";
import { stageMedia, copyMedia, calibrationHits, planMode } from "./lib/media.mjs";

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

export async function buildProject(planPath, { out, styleDir = null, sfxPath = null, beats = null, log = console.log } = {}) {
  const { plan, path, dir: planDir } = loadPlan(planPath);
  const sfxAbs = sfxPath ? resolve(process.cwd(), sfxPath) : null;
  const result = validatePlan(plan, { planDir, styleDir, beats, sfxPath: sfxAbs });
  const blockers = [];
  if (!result.ok) blockers.push("the plan gate is closed");
  for (const s of result.resolved) for (const m of s.moves) {
    if (m.kind === "placeholder") blockers.push(`${s.id}: novel move "${m.name}" is not built (no library/${m.name}.html beside the plan, no props.tweens)`);
  }
  const voAudio = plan.vo?.audio ? (isAbsolute(plan.vo.audio) ? plan.vo.audio : resolve(planDir, plan.vo.audio)) : null;
  const sfx = loadSfx(sfxAbs, plan, result.resolved, planDir);
  for (const e of sfx.errors) blockers.push(`sfx: ${e}`);

  // The bed: the sfx plan's music wins, plan.music.clip stands in when the
  // sfx plan has none. With no voice it is the spine the piece is timed to.
  const planMusic = typeof plan.music?.clip === "string" ? (isAbsolute(plan.music.clip) ? plan.music.clip : resolve(planDir, plan.music.clip)) : null;
  let music = sfx.music;
  if (!music && planMusic) {
    music = { clip: planMusic, clipName: basename(planMusic), gain_db: typeof plan.music.gain_db === "number" ? plan.music.gain_db : 0, duck_db_under_vo: 0, from: "plan.music" };
  } else if (music && planMusic && resolve(music.clip) !== resolve(planMusic)) {
    log(`! the sfx plan's music ${music.clip} is the bed; plan.music.clip ${planMusic} is not used`);
  }
  if (music && !existsSync(music.clip)) blockers.push(`music clip ${music.clip} is not on disk`);

  // Media staged now so the re-check below sees exactly what gets copied.
  const media = stageMedia({ scenes: result.resolved, style: result.style, planDir });
  const { scenes, style } = media;

  // The calibration guard, re-checked over every file this build copies or
  // inlines, independent of the gate above.
  const mode = planMode(plan);
  const copied = [
    ...(voAudio ? [{ file: voAudio, what: "voice-over" }] : []),
    ...(music ? [{ file: music.clip, what: "music bed" }] : []),
    ...sfx.events.map((e) => ({ file: e.clip, what: `sfx ${e.id}` })),
    ...[...media.files.keys()].map((f) => ({ file: f, what: "plate" })),
    ...[...new Set(scenes.flatMap((s) => s.moves.map((m) => m.file)).filter(Boolean))].map((f) => ({ file: f, what: "element" })),
    ...(result.beats?.source && !result.beats.source.includes("(inline)") ? [{ file: result.beats.source, what: "beat grid" }] : []),
  ];
  const hits = calibrationHits(copied);
  if (mode !== "replica") for (const h of hits) blockers.push(`calibration-only ${h.what} ${h.file} (${h.why}) cannot enter a piece; only a plan with "mode": "replica" may use the source's own frames`);

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
  copyMedia(media.files, outDir);

  const total = plan.duration;
  const audio = [];

  // Voice-over, when the piece has one.
  if (voAudio) {
    const voName = `vo${extname(voAudio)}`;
    copyFileSync(voAudio, resolve(assets, voName));
    const voDur = probeDuration(voAudio);
    if (voDur > total + 0.05) log(`! the voice-over runs ${voDur.toFixed(2)}s and the piece ${total}s; the tail is cut`);
    audio.push({ id: "vo", src: `assets/${voName}`, start: 0, duration: r3(Math.min(voDur, total)), track: 10, group: "voiceover", volume: 1 });
  } else {
    log(music ? `no voice-over: rendering music-only, ${music.clipName} is the timing spine` : "! no voice-over and no music bed: the piece renders with sound effects only");
  }

  // Music bed: level as a gain stage, ducked under the voice by automating it,
  // so the lane is in dB and the bed breathes back between phrases. With no
  // voice there is nothing to duck under, and the lane only fades the tail.
  if (music) {
    const name = `music${extname(music.clip)}`;
    copyFileSync(music.clip, resolve(assets, name));
    const musicDur = probeDuration(music.clip);
    const frame = 1 / (Number(plan.format.fps) || 30);
    if (!voAudio && musicDur < total - frame) log(`! the music runs ${musicDur.toFixed(2)}s and the piece ${total}s; with no voice the last ${(total - musicDur).toFixed(2)}s is silent`);
    const dur = r3(Math.min(musicDur, total));
    const base = Math.max(-60, Math.min(12, music.gain_db));
    const duck = voAudio ? music.duck_db_under_vo : 0;
    const points = duckLane(voAudio ? plan.vo.words : [], dur, base, duck);
    audio.push({
      id: "music", src: `assets/${name}`, start: 0, duration: dur, track: 11, group: "music",
      fxChain: { version: 1, nodes: [{ type: "gain", id: "n1", label: duck ? "Bed level, ducked under VO" : "Bed level", params: { gain: base } }] },
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
    css: media.rewriteStyleCss(styleCss(style, notes)),
    elements: elementBlocks(scenes, notes, media.rewriteElement),
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
    mode,
    vo: voAudio,
    music: music ? { clip: music.clip, gain_db: music.gain_db, duck_db_under_vo: voAudio ? music.duck_db_under_vo : 0, from: music.from ?? "sfx plan" } : null,
    beats: result.beats ? { source: result.beats.source, beats: result.beats.beats.length, downbeats: result.beats.downbeats.length } : null,
    plates: Object.fromEntries([...media.files].map(([abs, n]) => [`assets/plates/${n}`, abs])),
    duration: total,
    format: plan.format,
    scenes: scenes.map((s) => ({ id: s.id, start: s.start, duration: s.duration, moves: s.moves.map((m) => ({ name: m.name, target: m.target, kind: m.kind, t: m.tAbs, ...(m.beat ? { beat: `${m.beat.kind}:${m.beat.index}` } : {}) })) })),
    audio: audio.map(({ fxChain, automation, ...a }) => ({ ...a, ducking: automation ? automation.lanes[0].points : undefined })),
    sfx: sfx.events.map((e) => ({ id: e.id, t: e.t, class: e.class, clip: e.clipName, gain_db: e.gain_db, pan: e.pan, move: e.move, origin: e.origin })),
    silenced: sfx.silenced.map((e) => ({ t: e.t, class: e.class, move: e.move, reason: e.reason })),
  }, null, 2) + "\n");

  return { outDir, audio, scenes, sfx, plates: media.files };
}

async function main(argv) {
  const args = parseArgs(argv, ["out", "style-dir", "sfx", "beats"]);
  const planPath = args._[0];
  if (!planPath || !args.out) {
    console.error("usage: node toolkit/build-composition.mjs <plan.json> --out <dir> [--style-dir <dir>] [--sfx <sfx-plan.json>] [--beats <json>]");
    process.exit(2);
  }
  try {
    const { outDir, audio, scenes, plates } = await buildProject(planPath, { out: args.out, styleDir: args["style-dir"] ?? null, sfxPath: args.sfx ?? null, beats: args.beats ?? null });
    console.log(`composition written to ${outDir}/index.html`);
    console.log(`  ${scenes.length} scene clip(s), ${audio.length} audio clip(s): ${audio.map((a) => `${a.id}@${a.start}s`).join(", ")}`);
    if (plates.size) console.log(`  ${plates.size} plate(s) in assets/plates: ${[...plates.values()].join(", ")}`);
    console.log(`render with: toolkit/render.sh ${outDir} <out.mp4>`);
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main(process.argv);
