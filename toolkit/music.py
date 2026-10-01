"""Music: the bed as part of the hand. Measure it, export its beat grid, generate a new
one in the same profile through ElevenLabs Music, and score what comes back.

  music.py measure <video|audio> --out music.json [--stems-dir DIR] [--beats-out beats.json]
  music.py generate <music.json> --duration S --out-dir DIR [--n 2] [--sections a,b,..] [--dry-run]
  music.py score <music.json> <audio> [--out score.json]

Measure runs on the non-vocal Demucs stem (reusing the cache sound.py writes into
--stems-dir), so a voice-over never pollutes tempo, key or timbre. Beats come from
librosa's tracker; the downbeat is the beat phase (of four) carrying the most kick
energy plus harmonic change, since bars turn over on the kick and chords move on the
one. Bars are grouped into sections by agglomerative clustering of per-bar loudness,
brightness, low end, onset density and chroma, and sections that sound alike share a
letter. The energy arc is per-bar loudness relative to the loudest bar. Drops are bars
at least 6 dB over the two before them; breaks are bars 6 dB under their neighbours.
Key is Krumhansl-Schmuckler on the harmonic part's chroma, with its margin over the
runner-up as confidence. Timbre is the stem shares (drums, bass, other), percussive
share, centroid and low-end share, written as words for the generator prompt too.

Generate builds a music_v2_5 composition plan with one chunk per section, scaled to
the new duration, styled from the measured profile, instrumental by negative styles,
and keeps the best of n by score. Score compares tempo (octave-tolerant), key, energy
arc shape, timbre and density, each 0..1, and a weighted total. A key without access
writes a queued job file instead of failing.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import scipy.signal as ss
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "measure"))
from common import emit, pct, sha256  # noqa: E402

SR = 22050
HOP = 512
API = "https://api.elevenlabs.io/v1/music"
MODEL = "music_v2_5"
KEYS = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
KS_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KS_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


# ----------------------------------------------------------------------------- load

def load_bed(path: str, stems_dir: str | None):
    """Non-vocal stem at 22.05 kHz mono, plus per-stem arrays when Demucs ran."""
    import sound  # noqa: WPS433 (measure/sound.py)
    x = sound.decode(path)
    h = sha256(path)
    sd = Path(stems_dir) if stems_dir else None
    vocals, nonvocal, method = sound.separate(x, h, sd, "cpu")
    stems = {}
    if sd is not None:
        sd = sd / h[:12]
        for s in ("drums", "bass", "other"):
            f = sd / f"{s}.wav"
            if f.exists():
                stems[s] = sf.read(f, dtype="float32", always_2d=True)[0].mean(1)
    stems["vocals"] = vocals.mean(1)
    to22 = lambda a: ss.resample_poly(a, 1, 2).astype(np.float32)  # noqa: E731
    return to22(nonvocal.mean(1)), {k: to22(v) for k, v in stems.items()}, method, h, x


def load_plain(path: str) -> np.ndarray:
    raw = subprocess.run(["/opt/homebrew/bin/ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-vn", "-ac", "1",
                          "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


# ----------------------------------------------------------------------------- measure

def measure_audio(y: np.ndarray, stems: dict | None = None) -> dict:
    import librosa
    import pyloudnorm as pyln
    dur = len(y) / SR
    yh, yp = librosa.effects.hpss(y)
    oenv = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    tempo, bfr = librosa.beat.beat_track(onset_envelope=oenv, sr=SR, hop_length=HOP, tightness=100)
    tempo = float(np.atleast_1d(tempo)[0])
    beats = librosa.frames_to_time(bfr, sr=SR, hop_length=HOP)
    lufs = pyln.Meter(SR).integrated_loudness(y.astype(np.float64)) if dur > 0.5 else float("nan")
    out = {"duration": dur, "tempo_bpm": tempo if tempo > 0 and len(beats) > 4 else None,
           "lufs": float(lufs) if np.isfinite(lufs) else None}
    if out["tempo_bpm"] is None:
        out.update(present=bool(out["lufs"] is not None and out["lufs"] > -45), beats=[], downbeats=[], bars=[],
                   sections=[], energy_arc=[], drops=[], breaks=[])
        return out
    # downbeat phase: kick energy (<150 Hz onset strength) plus chroma change
    S = np.abs(librosa.stft(y, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=SR)
    low_on = np.clip(np.diff(np.log1p(S[freqs < 150].sum(0)), prepend=0), 0, None)
    chroma = librosa.feature.chroma_stft(S=S ** 2, sr=SR, hop_length=HOP)
    cchg = np.r_[0, np.linalg.norm(np.diff(chroma, axis=1), axis=0)]
    scores = []
    for k in range(4):
        fr = bfr[k::4]
        fr = fr[fr < len(low_on)]
        a = low_on[fr].mean() / (low_on[bfr].mean() + 1e-9) if len(fr) else 0
        b = cchg[fr].mean() / (cchg[bfr].mean() + 1e-9) if len(fr) else 0
        scores.append(float(a + b))
    k = int(np.argmax(scores))
    srt = sorted(scores, reverse=True)
    down = beats[k::4]
    bars = [(float(down[i]), float(down[i + 1])) for i in range(len(down) - 1)]
    # per-bar features
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    cent = librosa.feature.spectral_centroid(S=S, sr=SR)[0]
    lowsh = S[freqs < 150].sum(0) / (S.sum(0) + 1e-9)
    on_t = librosa.onset.onset_detect(onset_envelope=oenv, sr=SR, hop_length=HOP, units="time")
    feats, bar_db = [], []
    for t0, t1 in bars:
        f0, f1 = librosa.time_to_frames([t0, t1], sr=SR, hop_length=HOP)
        f1 = max(f1, f0 + 1)
        db = 20 * np.log10(np.sqrt((rms[f0:f1] ** 2).mean()) + 1e-9)
        bar_db.append(db)
        dens = ((on_t >= t0) & (on_t < t1)).sum() / max(1e-3, (t1 - t0)) * (60 / tempo)
        feats.append(np.r_[db / 6, math.log2(cent[f0:f1].mean() + 1) / 2, lowsh[f0:f1].mean() * 4, dens / 2,
                           chroma[:, f0:f1].mean(1) * 2])
    bar_db = np.array(bar_db)
    peak_db = float(bar_db.max()) if len(bar_db) else 0.0
    # sections
    sections = []
    if len(bars) >= 4:
        F = np.array(feats).T
        kk = int(np.clip(round(len(bars) / 6), 2, 8))
        bnd = librosa.segment.agglomerative(F, kk)
        bnd = sorted(set([0] + [int(b) for b in bnd] + [len(bars)]))
        means = []
        for i in range(len(bnd) - 1):
            a, b = bnd[i], bnd[i + 1]
            if b <= a:
                continue
            means.append((a, b, F[:, a:b].mean(1)))
        labels, protos = [], []
        for a, b, m in means:
            lab = None
            for j, pm in enumerate(protos):
                if np.linalg.norm(m - pm) < 0.6:
                    lab = j
                    break
            if lab is None:
                protos.append(m)
                lab = len(protos) - 1
            labels.append(lab)
        for (a, b, _), lab in zip(means, labels):
            db = float(bar_db[a:b].mean())
            sections.append({"t0": bars[a][0], "t1": bars[b - 1][1], "bars": b - a, "label": "ABCDEFGH"[lab],
                             "energy_db": db - peak_db, "role": role_of(db - peak_db, a, b, len(bars))})
    drops = [bars[i][0] for i in range(2, len(bars)) if bar_db[i] - bar_db[i - 2:i].mean() >= 6]
    breaks = [bars[i][0] for i in range(1, len(bars) - 1)
              if bar_db[i] <= min(bar_db[i - 1], bar_db[i + 1]) - 6]
    hits = []
    if len(oenv):
        thr = np.percentile(oenv, 99)
        pk, _ = ss.find_peaks(oenv, height=thr, distance=int(0.25 * SR / HOP))
        hits = librosa.frames_to_time(pk, sr=SR, hop_length=HOP).tolist()
    # key
    ch = librosa.feature.chroma_cqt(y=yh, sr=SR, hop_length=HOP).mean(1)
    corr = []
    for i in range(12):
        corr.append((np.corrcoef(np.roll(KS_MAJ, i), ch)[0, 1], f"{KEYS[i]} major"))
        corr.append((np.corrcoef(np.roll(KS_MIN, i), ch)[0, 1], f"{KEYS[i]} minor"))
    corr.sort(reverse=True)
    # timbre
    tot = float((y ** 2).sum()) + 1e-12
    shares = {}
    if stems:
        e = {s: float((v[:len(y)] ** 2).sum()) for s, v in stems.items() if s != "vocals"}
        se = sum(e.values()) + 1e-12
        shares = {s: v / se for s, v in sorted(e.items())}
    timbre = {"stem_shares": shares, "percussive_share": float((yp ** 2).sum() / tot),
              "centroid_hz": float(np.median(cent)), "low_share": float(np.median(lowsh)),
              "onsets_per_beat": float(len(on_t) / max(1, len(beats)))}
    lu_st = short_term_lufs(y)
    out.update({
        "present": bool(out["lufs"] is not None and out["lufs"] > -45),
        "meter_assumed": 4,
        "beats": beats.tolist(), "downbeats": down.tolist(),
        "downbeat_confidence": float((srt[0] - srt[1]) / (srt[0] + 1e-9)),
        "bars": [{"t0": a, "t1": b} for a, b in bars],
        "bar_s": float(np.median([b - a for a, b in bars])) if bars else None,
        "sections": sections,
        "energy_arc": (bar_db - peak_db).tolist(),
        "arc": arc_summary(bar_db - peak_db),
        "drops": drops, "breaks": breaks, "hits": hits,
        "key": corr[0][1], "key_confidence": float(corr[0][0] - corr[1][0]),
        "timbre": timbre,
        "loudness_range_lu": (float(np.percentile(lu_st, 95) - np.percentile(lu_st, 10)) if len(lu_st) else None),
    })
    out["description"] = describe(out)
    return out


def role_of(rel_db, a, b, n):
    if a == 0 and rel_db < -6:
        return "intro"
    if b == n and rel_db < -6:
        return "outro"
    if rel_db > -2.5:
        return "peak"
    if rel_db < -8:
        return "break"
    return "build" if rel_db > -5 else "low"


def arc_summary(arc: np.ndarray) -> dict:
    if not len(arc):
        return {}
    n = len(arc)
    return {"start_db": float(arc[:max(1, n // 8)].mean()), "end_db": float(arc[-max(1, n // 8):].mean()),
            "peak_at": float(np.argmax(arc) / max(1, n - 1)), "range_db": float(arc.max() - arc.min()),
            "slope_db_per_bar": float(np.polyfit(np.arange(n), arc, 1)[0]) if n > 1 else 0.0}


def short_term_lufs(y: np.ndarray) -> np.ndarray:
    import pyloudnorm as pyln
    m = pyln.Meter(SR)
    w, h = 3 * SR, SR
    out = []
    for s in range(0, max(1, len(y) - w), h):
        v = m.integrated_loudness(y[s:s + w].astype(np.float64))
        if np.isfinite(v) and v > -70:
            out.append(v)
    return np.array(out)


def describe(p: dict) -> str:
    t = p["timbre"]
    words = []
    sh = t.get("stem_shares", {})
    if sh:
        lead = max(sh, key=sh.get)
        words.append({"drums": "drum-led", "bass": "bass-led", "other": "synth/instrument-led"}.get(lead, lead))
    words.append("punchy, percussive" if t["percussive_share"] > 0.45 else
                 "sustained, tonal" if t["percussive_share"] < 0.2 else "balanced groove")
    words.append("bright" if t["centroid_hz"] > 2500 else "dark, warm" if t["centroid_hz"] < 1200 else "mid-focused")
    if t["low_share"] > 0.35:
        words.append("heavy low end")
    words.append("busy rhythm" if t["onsets_per_beat"] > 1.6 else "sparse rhythm" if t["onsets_per_beat"] < 0.7
                 else "steady rhythm")
    a = p.get("arc", {})
    if a:
        words.append("builds to a peak late" if a["peak_at"] > 0.6 else "peaks early" if a["peak_at"] < 0.3
                     else "peaks mid-piece")
        if a["range_db"] < 4:
            words.append("flat energy, loop-like")
    if p.get("drops"):
        words.append(f"{len(p['drops'])} drop(s)")
    return ", ".join(words)


# ----------------------------------------------------------------------------- score

def score(src: dict, new: dict) -> dict:
    s = {}
    if src.get("tempo_bpm") and new.get("tempo_bpm"):
        r = min(abs(math.log2(new["tempo_bpm"] * m / src["tempo_bpm"])) for m in (0.5, 1, 2))
        s["tempo"] = max(0.0, 1 - r / 0.08)
    else:
        s["tempo"] = 0.0
    if src.get("key") and new.get("key"):
        s["key"] = key_score(src["key"], new["key"]) if src.get("key_confidence", 0) > 0.02 else 1.0
    a, b = np.array(src.get("energy_arc") or []), np.array(new.get("energy_arc") or [])
    if len(a) > 2 and len(b) > 2:
        xa, xb = np.interp(np.linspace(0, 1, 32), np.linspace(0, 1, len(a)), a), \
            np.interp(np.linspace(0, 1, 32), np.linspace(0, 1, len(b)), b)
        r = np.corrcoef(xa, xb)[0, 1] if xa.std() > 0.3 and xb.std() > 0.3 else 1 - abs(xa.std() - xb.std()) / 3
        s["arc"] = float(np.clip((r + 1) / 2, 0, 1))
    ta, tb = src.get("timbre", {}), new.get("timbre", {})
    if ta and tb:
        c = 1 - min(1.0, abs(math.log2((tb["centroid_hz"] + 1) / (ta["centroid_hz"] + 1))))
        pcs = 1 - min(1.0, abs(tb["percussive_share"] - ta["percussive_share"]) / 0.4)
        low = 1 - min(1.0, abs(tb["low_share"] - ta["low_share"]) / 0.3)
        den = 1 - min(1.0, abs(tb["onsets_per_beat"] - ta["onsets_per_beat"]) / max(0.5, ta["onsets_per_beat"]))
        s["timbre"] = float(np.mean([c, pcs, low]))
        s["density"] = float(den)
    w = {"tempo": 0.3, "key": 0.15, "arc": 0.2, "timbre": 0.25, "density": 0.1}
    tot = sum(w[k] * s[k] for k in s) / sum(w[k] for k in s) if s else 0.0
    return {"total": tot, "parts": s, "tempo_bpm": new.get("tempo_bpm"), "key": new.get("key")}


def key_score(a: str, b: str) -> float:
    ia, ma = KEYS.index(a.split()[0]), a.split()[1]
    ib, mb = KEYS.index(b.split()[0]), b.split()[1]
    if (ia, ma) == (ib, mb):
        return 1.0
    rel = (ia + (3 if ma == "minor" else -3)) % 12
    if ma != mb and rel == ib:
        return 0.8
    if ma == mb and (ia - ib) % 12 in (5, 7):
        return 0.6
    return 0.2


# ----------------------------------------------------------------------------- generate

def plan_for(profile: dict, duration: float, roles: list | None) -> dict:
    """A music_v2_5 composition plan: one chunk per section of the source, scaled to the
    new duration, or one per named role when --sections is given."""
    secs = profile.get("sections") or [{"t0": 0, "t1": profile["duration"], "role": "build", "energy_db": -3}]
    if roles:
        secs = [{"role": r, "t0": i, "t1": i + 1, "energy_db": {"intro": -9, "build": -4, "peak": 0, "break": -10,
                                                                 "outro": -9, "low": -7}.get(r, -4)}
                for i, r in enumerate(roles)]
    secs = [dict(s) for s in secs]
    # at most one chunk per 3 s; merge the adjacent pair with the least time between
    # them, keeping the louder member's role so a short piece still builds to its peak
    while len(secs) > max(1, int(duration // 3)):
        lens = [secs[i]["t1"] - secs[i]["t0"] + secs[i + 1]["t1"] - secs[i + 1]["t0"] for i in range(len(secs) - 1)]
        i = int(np.argmin(lens))
        a_, b_ = secs[i], secs[i + 1]
        keep = a_ if a_.get("energy_db", -5) >= b_.get("energy_db", -5) else b_
        secs[i] = dict(keep, t0=a_["t0"], t1=b_["t1"] - b_["t0"] + a_["t1"])
        del secs[i + 1]
    span = sum(s["t1"] - s["t0"] for s in secs)
    total = int(round(duration * 1000))
    ms = [max(3000, int(round((s["t1"] - s["t0"]) / span * total))) for s in secs]
    over = sum(ms) - total
    while over > 0:
        i = int(np.argmax(ms))
        cut = min(over, ms[i] - 3000)
        if cut <= 0:
            break
        ms[i] -= cut
        over -= cut
    ms[-1] += total - sum(ms) if sum(ms) < total else 0
    base = [f"{round(profile['tempo_bpm'])} BPM"] if profile.get("tempo_bpm") else []
    if profile.get("key") and profile.get("key_confidence", 0) > 0.02:
        base.append(f"in {profile['key']}")
    base += [w.strip() for w in profile.get("description", "").split(",") if w.strip() and "drop(s)" not in w]
    base += ["instrumental", "background music for a short video", "clean modern mix", "great production quality"]
    role_words = {"intro": ["sparse intro", "minimal elements"], "build": ["building energy", "groove established"],
                  "peak": ["full energy", "all elements in", "punchy drums"], "break": ["breakdown", "drums drop out"],
                  "outro": ["outro", "elements thinning out"], "low": ["laid-back section", "reduced drums"]}
    neg = ["vocals", "singing", "lyrics", "spoken word", "choir", "vocal chops"]
    chunks = []
    for i, (s, d) in enumerate(zip(secs, ms)):
        r = s.get("role", "build")
        styles = (base if i == 0 else base[:3]) + role_words.get(r, [])
        chunks.append({"text": f"[Instrumental {r.title()}]", "duration_ms": int(d),
                       "positive_styles": styles[:20], "negative_styles": neg})
    return {"chunks": chunks}


def call_music(body: dict, out: Path) -> tuple[int, str]:
    import requests
    key = os.environ.get("ELEVENLABS_API_KEY") or env_key()
    r = requests.post(API, params={"output_format": "mp3_44100_128"}, json=body,
                      headers={"xi-api-key": key, "Content-Type": "application/json"}, timeout=600)
    if r.status_code == 200 and r.headers.get("content-type", "").startswith("audio"):
        out.write_bytes(r.content)
        return 200, r.headers.get("song-id", "")
    return r.status_code, r.text[:500]


def env_key() -> str:
    for p in (HERE.parent / ".env", Path.home() / ".env"):
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("ELEVENLABS_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("ELEVENLABS_API_KEY not found in ~/motion-expert/.env or ~/.env")


def generate(profile_path: str, duration: float, out_dir: str, n: int, roles, dry: bool) -> dict:
    prof = json.loads(Path(profile_path).read_text())
    od = Path(out_dir)
    od.mkdir(parents=True, exist_ok=True)
    body = {"composition_plan": plan_for(prof, duration, roles), "model_id": MODEL}
    if dry:
        return {"request": body}
    results = []
    for i in range(n):
        path = od / f"bed_{i:02d}.mp3"
        code, info = call_music(body, path)
        if code != 200:
            job = od / "queued-job.json"
            job.write_text(json.dumps({"endpoint": API, "model_id": MODEL, "status": code, "reason": info,
                                       "body": body}, indent=1) + "\n")
            return {"error": code, "reason": info, "queued": str(job)}
        m = measure_audio(load_plain(str(path)))
        sc = score(prof, m)
        (od / f"bed_{i:02d}.music.json").write_text(json.dumps(m, indent=1, sort_keys=True) + "\n")
        (od / f"bed_{i:02d}.beats.json").write_text(json.dumps(beats_of(m), indent=1) + "\n")
        results.append({"file": path.name, "song_id": info, "score": sc})
    results.sort(key=lambda r: -r["score"]["total"])
    rep = {"best": results[0]["file"], "best_beats": results[0]["file"].replace(".mp3", ".beats.json"),
           "candidates": results, "request": body, "target_duration": duration}
    (od / "generated.json").write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n")
    return rep


def beats_of(p: dict) -> dict:
    return {"tempo_bpm": p.get("tempo_bpm"), "beats": p.get("beats", []), "downbeats": p.get("downbeats", []),
            "bars": p.get("bars", []), "sections": p.get("sections", []), "drops": p.get("drops", [])}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("media")
    m.add_argument("--out", required=True)
    m.add_argument("--stems-dir")
    m.add_argument("--beats-out")
    m.add_argument("--plain", action="store_true", help="measure the file as is, no separation (a music file)")
    g = sub.add_parser("generate")
    g.add_argument("profile")
    g.add_argument("--duration", type=float, required=True)
    g.add_argument("--out-dir", required=True)
    g.add_argument("--n", type=int, default=2)
    g.add_argument("--sections", help="comma list of roles (intro,build,peak,break,outro) to override the source's")
    g.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("score")
    s.add_argument("profile")
    s.add_argument("audio")
    s.add_argument("--out")
    a = ap.parse_args()
    if a.cmd == "measure":
        if a.plain:
            y, stems, method, h = load_plain(a.media), None, "plain", sha256(a.media)
        else:
            y, stems, method, h, _ = load_bed(a.media, a.stems_dir)
        prof = measure_audio(y, stems)
        prof["method"] = method
        prof["source"] = {"path": str(Path(a.media).resolve()), "sha256": h}
        emit(prof, a.out)
        if a.beats_out:
            emit(beats_of(prof), a.beats_out)
    elif a.cmd == "generate":
        roles = [r.strip() for r in a.sections.split(",")] if a.sections else None
        emit(generate(a.profile, a.duration, a.out_dir, a.n, roles, a.dry_run), None)
    else:
        prof = json.loads(Path(a.profile).read_text())
        emit(score(prof, measure_audio(load_plain(a.audio))), a.out)


if __name__ == "__main__":
    main()
