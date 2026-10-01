"""SFX: build and serve a style's sound palette.

  sfx.py palette <sound.json> --style-dir DIR [--music music.json]
  sfx.py generate DIR --class C [--target JSON|file] [--n 4] [--prompt TEXT] [--dry-run]
  sfx.py pick DIR --move PROPERTY [--class C] [--key start|peak|land|cut]
  sfx.py analyse <clip.wav>

palette writes DIR/sound/palette.json, one entry per class with the measured target
profile (duration, centroid, bandwidth, attack, decay, level against the voice and
the mix, pan) and the binding rules from sound.json, and copies every clean source
clip into DIR/sound/source/. A clean source clip is reference audio and is used as is
in new pieces, because the sound is part of the hand and not the source's content.

generate asks ElevenLabs sound generation (POST /v1/sound-generation, model
eleven_text_to_sound_v2) for n candidates at spread prompt_influence, trims each to its
onset and to the class's envelope, measures it the way sound.py measures events, and
scores it against the target profile and, when one exists, against the clean source
clip by MFCC distance. The best is kept in DIR/sound/generated/ with its score and
listed in palette.json. Prompting notes that held up are in toolkit/SFX.md.

pick returns the clip for a move: a clean source clip of the class first, else the best
generated one, else exit 2 naming the generate command to run. Without --class the
class comes from the binding rules for that move property.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import scipy.signal as ss
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "measure"))
import sound as S  # noqa: E402
from common import dumps, pct  # noqa: E402

API = "https://api.elevenlabs.io/v1/sound-generation"
MODEL = "eleven_text_to_sound_v2"
SR = S.SR

# What each class is called when asking for it. Concrete nouns and the envelope in
# words work better than adjectives about mood (see SFX.md).
PROMPTS = {
    "whoosh": "a fast swish of air passing close by, {tone}, {dur}, smooth rise and fall, no low rumble, clean isolated sound effect, no music",
    "riser": "a rising noise swell that builds and stops at its peak, {dur} long, {tone}, clean isolated sound effect, no music, no impact at the end",
    "impact": "one deep punchy impact hit, {dur} long including its tail, {tone}, clean isolated sound effect, no music",
    "click": "one single crisp UI click, very short, {tone}, dry, clean isolated sound effect, no music, no reverb",
    "pop": "one short soft bubble pop, {dur} long, {tone}, dry, clean isolated sound effect, no music",
    "glitch": "one short digital glitch stutter, {dur} long, {tone}, clean isolated sound effect, no music",
    "chime": "one clean bright notification chime, {dur} long with natural decay, {tone}, isolated sound effect, no music",
    "typing": "fast keyboard typing, several keystrokes, {dur} long, {tone}, dry, clean isolated sound effect, no music",
    "sub-drop": "a deep sub bass drop falling in pitch, {dur} long, clean isolated sound effect, no music",
    "other": "a short clean interface sound effect, {dur} long, {tone}, isolated, no music",
}


# ----------------------------------------------------------------------------- clip analysis

def load(path) -> np.ndarray:
    raw = subprocess.run([S.FFMPEG, "-v", "error", "-nostdin", "-i", str(path), "-ac", "2", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def envelope(x: np.ndarray) -> tuple[np.ndarray, float, int]:
    m = x.mean(1)
    w = SR // 1000
    n = len(m) // w
    e = 10 * np.log10((m[:n * w].reshape(n, w) ** 2).mean(1) + 1e-14)
    sm = np.convolve(e, np.ones(3) / 3, "same")
    return sm, float(sm.max()), int(np.argmax(sm))


def trim(x: np.ndarray, keep_db: float = 35.0, max_s: float | None = None) -> np.ndarray:
    """Cut to the onset (first ms within keep_db of the peak, less 2 ms) and the tail
    (last ms within keep_db), cap the length, fade 2 ms in and 15 ms out."""
    e, pk, _ = envelope(x)
    above = np.where(e > pk - keep_db)[0]
    if not len(above):
        return x
    a = max(0, (above[0] - 2) * (SR // 1000))
    b = min(len(x), (above[-1] + 5) * (SR // 1000))
    if max_s:
        b = min(b, a + int(max_s * SR))
    y = x[a:b].copy()
    fi, fo = min(len(y) // 4, int(0.002 * SR)), min(len(y) // 3, int(0.015 * SR))
    if fi:
        y[:fi] *= np.linspace(0, 1, fi)[:, None]
    if fo:
        y[-fo:] *= np.linspace(1, 0, fo)[:, None]
    return y


def analyse(x: np.ndarray) -> dict:
    """The same profile sound.py records for an event, measured on an isolated clip
    with the same envelope timing, plus a typing check: three or more regular
    keystroke onsets make the whole run one typing event."""
    import librosa
    m = x.mean(1)
    env, er = S.band_env(m, 40.0, 16000.0)
    bg = float(np.percentile(env, 5))
    on, ip, q = S.envelope_timing(env, er, 0, len(env), bg)
    n_on, gap, gcv = S.onsets_in(env, er, max(0, on - int(0.01 * er)), len(env))
    fb, mel_f = S.mel_bank()
    Mp = fb @ S.power_spec(np.pad(m, (SR // 20, SR // 20)))

    class C:  # minimal context for the shared feature function
        pass
    c = C()
    c.mel_f = mel_f
    f = S.mel_excess_features(c, Mp)
    dur = max(0.005, (q - on) / er)
    if n_on >= 3 and 0.04 <= gap <= 0.3:  # a run of hits: the event spans the run
        act = np.where(env > env.max() - 25)[0]
        dur = max(dur, (act[-1] - on) / er)
    f.update(micro_onsets=n_on, onset_gap_s=gap, onset_gap_cv=gcv)
    feats = dict(f, duration=dur, attack_ms=float(ip - on) / er * 1000, decay_ms=float(q - ip) / er * 1000,
                 tonality=S.tonality(m, on / er, dur))
    cls, conf, _ = S.classify(feats)
    l, r = float((x[:, 0] ** 2).sum()), float((x[:, 1] ** 2).sum())
    mf = librosa.feature.mfcc(y=m[: max(len(m), 2048)], sr=SR, n_mfcc=20, n_fft=1024, hop_length=256)
    return {"duration": dur, "attack_ms": feats["attack_ms"], "decay_ms": feats["decay_ms"],
            "centroid_hz": f["centroid_hz"], "bandwidth_hz": f["bandwidth_hz"], "class": cls, "confidence": conf,
            "pan": (r - l) / (r + l + 1e-12), "peak_dbfs": float(env.max()), "mfcc_mean": mf.mean(1).tolist(),
            "mfcc_std": mf.std(1).tolist(), "_feats": {k: v for k, v in feats.items() if k != "band"}}


def match(prof: dict, target: dict, ref: dict | None) -> dict:
    """0..1 per part and a weighted total. Ratios are compared in log2 so a click twice
    as long counts as far off as one half as long."""
    def lr(a, b, span):
        if a is None or b is None:
            return None
        return max(0.0, 1 - abs(math.log2((a + 1e-3) / (b + 1e-3))) / span)
    parts = {
        "duration": lr(prof["duration"], target.get("duration"), 1.5),
        "centroid": lr(prof["centroid_hz"], target.get("centroid_hz"), 1.5),
        "bandwidth": lr(prof["bandwidth_hz"], target.get("bandwidth_hz"), 2.0),
        "attack": lr(prof["attack_ms"] + 2, (target.get("attack_ms") or 0) + 2, 2.5),
        "decay": lr(prof["decay_ms"] + 5, (target.get("decay_ms") or 0) + 5, 2.0),
        "class": 1.0 if prof["class"] == target.get("class") else 0.3,
    }
    w = {"duration": 0.2, "centroid": 0.2, "bandwidth": 0.1, "attack": 0.15, "decay": 0.15, "class": 0.2}
    if ref is not None:
        a = np.r_[ref["mfcc_mean"], ref["mfcc_std"]]
        b = np.r_[prof["mfcc_mean"], prof["mfcc_std"]]
        d = float(np.linalg.norm(a - b) / (np.linalg.norm(a) + 1e-9))
        parts["mfcc"] = max(0.0, 1 - d)
        w["mfcc"] = 0.35
    have = {k: v for k, v in parts.items() if v is not None}
    total = sum(w[k] * v for k, v in have.items()) / sum(w[k] for k in have)
    return {"total": total, "parts": have}


# ----------------------------------------------------------------------------- palette

def target_of(events: list) -> dict:
    def med(k):
        v = [e[k] for e in events if e.get(k) is not None]
        return pct(v, 50) if v else None

    def rng(k):
        v = [e[k] for e in events if e.get(k) is not None]
        return [pct(v, 10), pct(v, 90)] if v else None
    keys = ["duration", "centroid_hz", "bandwidth_hz", "attack_ms", "decay_ms", "level_db_rel_vo",
            "level_db_rel_mix", "pan", "pan_move"]
    t = {k: med(k) for k in keys}
    t["ranges"] = {k: rng(k) for k in keys}
    return t


def palette(sound_json: str, style_dir: str, music_json: str | None) -> dict:
    sj = Path(sound_json).resolve()
    d = json.loads(sj.read_text())
    root = Path(style_dir) / "sound"
    (root / "source").mkdir(parents=True, exist_ok=True)
    (root / "generated").mkdir(parents=True, exist_ok=True)
    old = {}
    if (root / "palette.json").exists():
        old = json.loads((root / "palette.json").read_text())
    classes = {}
    for cls in sorted({e["class"] for e in d["events"]}):
        ev = [e for e in d["events"] if e["class"] == cls]
        src = []
        for e in ev:
            if e.get("clean") and e.get("clip"):
                name = f"{cls}_{len(src):02d}.wav"
                shutil.copyfile(sj.parent / e["clip"], root / "source" / name)
                prof = analyse(load(root / "source" / name))
                src.append({"file": f"source/{name}", "t": e["t"], "level_db_rel_vo": e["level_db_rel_vo"],
                            "level_db_rel_mix": e.get("level_db_rel_mix"), "pan": e["pan"],
                            "profile": {k: v for k, v in prof.items() if not k.startswith(("mfcc", "_"))}})
        tgt = target_of(ev)
        tgt["class"] = cls
        classes[cls] = {"count": len(ev), "target": tgt, "source_clips": src,
                        "generated": (old.get("classes", {}).get(cls, {}).get("generated") or []),
                        "bound_property_share": d["classes"].get(cls, {}).get("bound_property_share", {})}
    pal = {"from": {"sound_json": str(sj), "source_sha256": d.get("source", {}).get("sha256")},
           "level_ref": d.get("level_ref", "vo"), "move_map": old.get("move_map", {}), "density_per_10s": d["density_per_10s"], "sync": d["sync"],
           "binding_rules": d["binding_rules"], "moves_seen": d.get("moves_seen", {}),
           "music": d.get("music", {}), "vo": d.get("vo", {}), "level_ref_db": d.get("level_ref_db"),
           "classes": classes}
    if music_json:
        shutil.copyfile(music_json, root / "music.json")
        pal["music_profile"] = "music.json"
    (root / "palette.json").write_text(dumps(pal))
    return {"palette": str(root / "palette.json"), "classes": {k: {"count": v["count"], "source_clips": len(v["source_clips"])}
                                                               for k, v in classes.items()}}


# ----------------------------------------------------------------------------- generate

def words_for(t: dict) -> dict:
    c = t.get("centroid_hz") or 2000
    # graded on purpose: "bright high-frequency hiss" lands near 6 kHz, "airy, mid-range"
    # near 2-3 kHz, and an unqualified whoosh comes back dark, near 1 kHz (SFX.md)
    tone = ("very bright, thin high-frequency hiss" if c > 5000 else "bright airy hiss" if c > 3500
            else "airy, mid-range, not harsh" if c > 1500 else "warm, soft" if c > 600 else "deep, low")
    a = t.get("attack_ms") or 10
    attack = "instant sharp attack" if a < 8 else "fast attack" if a < 40 else "smooth swelling attack"
    d = t.get("duration") or 0.3
    dur = f"{d * 1000:.0f} milliseconds" if d < 1 else f"{d:.1f} seconds"
    return {"tone": tone, "attack": attack, "dur": dur}


def api_key() -> str:
    if os.environ.get("ELEVENLABS_API_KEY"):
        return os.environ["ELEVENLABS_API_KEY"]
    for p in (HERE.parent / ".env", Path.home() / ".env"):
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("ELEVENLABS_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("ELEVENLABS_API_KEY not found")


def call(prompt: str, duration: float, influence: float, out: Path) -> tuple[int, str]:
    import requests
    body = {"text": prompt, "duration_seconds": round(min(30.0, max(0.5, duration)), 2),
            "prompt_influence": influence, "model_id": MODEL}
    r = requests.post(API, params={"output_format": "mp3_44100_128"}, json=body,
                      headers={"xi-api-key": api_key(), "Content-Type": "application/json"}, timeout=120)
    if r.status_code == 200 and r.headers.get("content-type", "").startswith("audio"):
        out.write_bytes(r.content)
        return 200, ""
    return r.status_code, r.text[:400]


def generate(style_dir: str, cls: str, target_arg: str | None, n: int, prompt: str | None, dry: bool) -> dict:
    root = Path(style_dir) / "sound"
    pal = json.loads((root / "palette.json").read_text())
    entry = pal["classes"].get(cls) or {"count": 0, "target": {"class": cls}, "source_clips": [], "generated": []}
    target = dict(entry["target"])
    if target_arg:
        extra = json.loads(Path(target_arg).read_text()) if Path(target_arg).exists() else json.loads(target_arg)
        target.update(extra)
    target["class"] = cls
    ref = None
    if entry["source_clips"]:
        ref = analyse(load(root / entry["source_clips"][0]["file"]))
    text = prompt or PROMPTS.get(cls, PROMPTS["other"]).format(**words_for(target))
    dur = target.get("duration") or 0.4
    ask = max(0.5, min(30.0, dur * 1.3 + (0.15 if cls in ("impact", "chime", "sub-drop") else 0.05)))
    infl = [0.35, 0.55, 0.75, 0.9][:n] if n <= 4 else list(np.linspace(0.3, 0.95, n))
    if dry:
        return {"prompt": text, "duration_seconds": ask, "prompt_influence": infl, "target": target}
    tmp = root / "generated" / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    cands = []
    for i, pi in enumerate(infl):
        raw = tmp / f"{cls}_{i}.mp3"
        code, err = call(text, ask, float(pi), raw)
        if code != 200:
            return {"error": code, "reason": err}
        x = trim(load(raw), max_s=max(dur * 2.5, 0.12))
        prof = analyse(x)
        sc = match(prof, target, ref)
        cands.append((sc["total"], i, pi, x, prof, sc))
    cands.sort(key=lambda c: (-c[0], c[1]))
    best = cands[0]
    k = len(entry.get("generated", []))
    name = f"{cls}_{k:02d}.wav"
    sf.write(root / "generated" / name, best[3], SR, subtype="PCM_16")
    rec = {"file": f"generated/{name}", "score": best[5], "prompt": text, "prompt_influence": best[2],
           "duration_seconds": ask, "profile": {k2: v for k2, v in best[4].items() if not k2.startswith(("mfcc", "_"))},
           "candidates": [{"prompt_influence": c[2], "score": c[0]} for c in cands]}
    entry.setdefault("generated", []).append(rec)
    entry["generated"].sort(key=lambda g: -g["score"]["total"])
    pal["classes"][cls] = entry
    (root / "palette.json").write_text(dumps(pal))
    shutil.rmtree(tmp, ignore_errors=True)
    return rec


# ----------------------------------------------------------------------------- pick

def pick(style_dir: str, move: str, cls: str | None, key: str | None) -> dict:
    root = Path(style_dir) / "sound"
    pal = json.loads((root / "palette.json").read_text())
    rules = [r for r in pal["binding_rules"] if r["move_property"] == move and (key is None or r["key"] == key)]
    if cls is None:
        if not rules:
            raise SystemExit(f"no binding rule for move property {move!r}; pass --class")
        cls = rules[0]["class"]
    rule = next((r for r in rules if r["class"] == cls), None)
    entry = pal["classes"].get(cls)
    clip, origin = None, None
    if entry and entry["source_clips"]:
        clip, origin = entry["source_clips"][0]["file"], "source"
    elif entry and entry.get("generated"):
        clip, origin = entry["generated"][0]["file"], "generated"
    if clip is None:
        print(f"no clip for class {cls!r}: run sfx.py generate {style_dir} --class {cls}", file=sys.stderr)
        sys.exit(2)
    tgt = entry["target"]
    return {"clip": str((root / clip).resolve()), "class": cls, "origin": origin,
            "key": rule["key"] if rule else None, "offset_s": rule["offset_s"] if rule else 0.0,
            "level_db_rel_vo": (rule or {}).get("level_db_rel_vo", tgt.get("level_db_rel_vo")),
            "level_ref": pal.get("level_ref", "vo"),
            "pan": (rule or {}).get("pan", tgt.get("pan")) or 0.0}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("palette")
    p.add_argument("sound_json")
    p.add_argument("--style-dir", required=True)
    p.add_argument("--music")
    g = sub.add_parser("generate")
    g.add_argument("style_dir")
    g.add_argument("--class", dest="cls", required=True)
    g.add_argument("--target")
    g.add_argument("--n", type=int, default=4)
    g.add_argument("--prompt")
    g.add_argument("--dry-run", action="store_true")
    k = sub.add_parser("pick")
    k.add_argument("style_dir")
    k.add_argument("--move", required=True)
    k.add_argument("--class", dest="cls")
    k.add_argument("--key")
    a_ = sub.add_parser("analyse")
    a_.add_argument("clip")
    a = ap.parse_args()
    if a.cmd == "palette":
        out = palette(a.sound_json, a.style_dir, a.music)
    elif a.cmd == "generate":
        out = generate(a.style_dir, a.cls, a.target, a.n, a.prompt, a.dry_run)
    elif a.cmd == "pick":
        out = pick(a.style_dir, a.move, a.cls, a.key)
    else:
        out = analyse(load(a.clip))
        out = {k2: v for k2, v in out.items() if not k2.startswith(("mfcc", "_"))}
    sys.stdout.write(dumps(out))


if __name__ == "__main__":
    main()
