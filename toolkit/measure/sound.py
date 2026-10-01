"""Sound: sound effects bound to motion, and the music bed under the voice.

Separation. The mix is decoded at 44.1 kHz stereo and split by Demucs htdemucs
(shifts 0, fixed seed, CPU by default so results are bit-reproducible, cached per
source under --stems-dir/<hash12>/) into vocals and the rest. A voice counts when its
stem is louder than -38 LUFS and within 12 dB of the bed; otherwise the source is
music-only, nothing is gated as speech and levels are quoted against the bed
(level_ref says which). With a voice, the signal searched for effects is the
non-vocal stem plus the vocal stem wherever nobody speaks, because Demucs files
isolated clicks and ticks under vocals. Speech is voiced frames on the vocal stem
(autocorrelation pitch strength in 80-400 Hz) dilated by 150 ms. If Demucs cannot
load, the mix itself is searched and method is "fallback".

Detection. A 96-band mel power spectrogram is compared with a running 1.2 s median
per band (the bed); the excess, as the mean of the 12 most excited bands minus the
median band, is high for an event and near zero for a gain change (a duck releasing,
a fade, the bed entering). Candidates start at onsets of that excess and run to the
next onset, so a kick and an effect on the next beat are judged apart. A candidate is
music when most of its excess energy on the non-vocal stem is also there one beat,
half a bar, one, two or four bars away (level-matched, best lag, +-40 ms); persistent
level steps, unvoiced breaths before speech and degenerate blips are dropped. A
second pass finds sample reuse: a sharp transient under speech that matches another
sample for sample off the beat grid, or matches an accepted effect, is an effect.

Per event: onset t and peak_t (2 ms band-limited envelope for the onset, 20 ms for
peak and end), duration, attack and decay (onset to peak, peak to -20 dB), level as
the 50 ms peak power of the excess against the reference (level_db_rel_vo) and the
mix (level_db_rel_mix), amplitude-weighted centroid and bandwidth, pan as (R-L)/(R+L)
of the excess and pan_move as late-half minus early-half pan, and a class from soft
rules (classify) with a confidence.

Binding. Every move keyframe (start, peak, land from motion.py) and every cut is an
anchor. Transient classes align their onset and sweep classes their peak to the
nearest anchor within 0.25 s; offset_to_move_s is always onset minus anchor, so a
placement puts the clip's first sample at anchor + offset. sync.chance_median_abs_s
is what evenly spaced random times score against the same anchors.

Clean clips. An event is written to clips/event_###.wav, Wiener-masked against the
local bed spectrum, when no speech and no other event overlaps it and it stands at
least 12 dB over the bed in its own bands. SOUND.md has the method and its measured
accuracy; SOUND_DEBUG=1 keeps private fields and rejected candidates in the output.

Usage: sound.py <video> --moves <motion-or-fingerprint.json> --out sound.json
       [--stems-dir DIR] [--plot spectrogram.png] [--device cpu|mps|auto]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import scipy.ndimage as nd
import scipy.signal as ss
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import FFMPEG, emit, pct, sha256  # noqa: E402

SR = 44100
HOP = 256
NFFT = 2048
NMELS = 96
FPS = SR / HOP  # analysis frames per second

P = {
    "bed_window_s": 1.2,
    "topk_bands": 12,
    "on_db": 9.0,
    "off_db": 4.0,
    "min_event_s": 0.012,
    "speech_dilate_s": 0.15,
    "speech_fill_s": 0.12,
    "voicing_thr": 0.45,
    "bind_window_s": 0.25,
    "clean_snr_db": 12.0,
    "music_repeat_sim": 0.5,
    "beat_tol_s": 0.07,
    "min_level_rel_mix_db": -50.0,
    "vo_min_lufs": -38.0,
    "vo_under_bed_db": 12.0,
    "recur_ncc": 0.6,
    "onset_db": 6.0,
}

CLASSES = ["whoosh", "riser", "impact", "click", "pop", "glitch", "chime", "typing", "sub-drop", "other"]
PEAK_ALIGNED = {"whoosh", "riser", "sub-drop"}  # perceived at the peak, so bind the peak


# ----------------------------------------------------------------------------- io

def decode(path: str) -> np.ndarray:
    """(n, 2) float32 at SR. Mono sources are duplicated."""
    raw = subprocess.run([FFMPEG, "-v", "error", "-nostdin", "-i", str(path), "-vn", "-ac", "2",
                          "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).reshape(-1, 2)
    if not len(x):
        raise SystemExit(f"no audio in {path}")
    return x.copy()


def separate(x: np.ndarray, src_hash: str, stems_dir: Path | None, device: str):
    """Return (vocals, nonvocal, method). Cached under stems_dir/<first 12 of the
    source hash>/ so one shared cache folder serves every source."""
    if stems_dir is not None:
        stems_dir = Path(stems_dir) / src_hash[:12]
        meta = stems_dir / "stems.json"
        if meta.exists():
            m = json.loads(meta.read_text())
            if m.get("source_sha256") == src_hash and (stems_dir / "vocals.wav").exists():
                v, _ = sf.read(stems_dir / "vocals.wav", dtype="float32", always_2d=True)
                nv, _ = sf.read(stems_dir / "nonvocal.wav", dtype="float32", always_2d=True)
                return v, nv, m.get("method", "demucs")
    try:
        import torch
        from demucs.apply import apply_model
        from demucs.pretrained import get_model
        torch.manual_seed(0)
        np.random.seed(0)
        model = get_model("htdemucs")
        model.eval()
        if device == "auto":
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        wav = torch.from_numpy(x.T.copy())[None]
        ref = wav.mean(1)
        mu, sd = ref.mean(), ref.std() + 1e-8
        with torch.no_grad():
            out = apply_model(model, (wav - mu) / sd, device=device, shifts=0, split=True,
                              overlap=0.25, progress=False)[0] * sd + mu
        out = out.cpu().numpy()
        stems = {s: out[i].T.astype(np.float32) for i, s in enumerate(model.sources)}
        vocals = stems["vocals"]
        nonvocal = (stems["drums"] + stems["bass"] + stems["other"]).astype(np.float32)
        method = "demucs"
    except Exception as e:  # pragma: no cover - only when torch or the weights are unavailable
        print(f"demucs unavailable ({e}); using the voicing-gated fallback", file=sys.stderr)
        stems = {}
        vocals = np.zeros_like(x)
        nonvocal = x
        method = "fallback"
    if stems_dir is not None:
        stems_dir.mkdir(parents=True, exist_ok=True)
        sf.write(stems_dir / "vocals.wav", vocals, SR, subtype="FLOAT")
        sf.write(stems_dir / "nonvocal.wav", nonvocal, SR, subtype="FLOAT")
        for s, a in stems.items():
            if s != "vocals":
                sf.write(stems_dir / f"{s}.wav", a, SR, subtype="FLOAT")
        (stems_dir / "stems.json").write_text(json.dumps(
            {"source_sha256": src_hash, "model": "htdemucs", "method": method, "device": device}, indent=1) + "\n")
    return vocals, nonvocal, method


# ----------------------------------------------------------------------------- speech

def voicing(mono: np.ndarray) -> np.ndarray:
    """Per analysis frame: normalised autocorrelation peak in the 80-400 Hz lag range
    times an energy gate. Computed at 16 kHz on 40 ms windows, mapped to HOP frames."""
    y = ss.resample_poly(mono, 160, 441)
    sr = 16000
    win, hop = 640, 160
    n = max(1, 1 + (len(y) - win) // hop)
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    fr = y[np.minimum(idx, len(y) - 1)] * np.hanning(win)[None, :]
    spec = np.fft.rfft(fr, 2 * win)
    ac = np.fft.irfft(np.abs(spec) ** 2)[:, :win]
    ac0 = ac[:, :1] + 1e-12
    lo, hi = sr // 400, sr // 80
    strength = (ac[:, lo:hi].max(1) / ac0[:, 0])
    rms_db = 10 * np.log10(ac0[:, 0] / win + 1e-12)
    active = rms_db > max(np.percentile(rms_db, 95) - 35, -60)
    v = np.where(active, strength, 0.0)
    t_v = (np.arange(n) * hop + win / 2) / sr
    n_out = int(math.ceil(len(mono) / HOP)) + 1
    return np.interp(np.arange(n_out) / FPS, t_v, v)


def speech_mask(vocals_mono: np.ndarray) -> np.ndarray:
    v = voicing(vocals_mono)
    m = v > P["voicing_thr"]
    m = nd.binary_closing(m, np.ones(int(P["speech_fill_s"] * FPS)))
    m = nd.binary_opening(m, np.ones(3))
    m = nd.binary_dilation(m, np.ones(2 * int(P["speech_dilate_s"] * FPS) + 1))
    return m


def regions(mask: np.ndarray):
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


# ----------------------------------------------------------------------------- spectra

def mel_bank():
    import librosa
    fb = librosa.filters.mel(sr=SR, n_fft=NFFT, n_mels=NMELS, fmin=30, fmax=16000, norm=None)
    freqs = librosa.mel_frequencies(n_mels=NMELS + 2, fmin=30, fmax=16000)[1:-1]
    return fb.astype(np.float32), freqs


def power_spec(x: np.ndarray) -> np.ndarray:
    _, _, Z = ss.stft(x, fs=SR, window="hann", nperseg=NFFT, noverlap=NFFT - HOP, boundary="even",
                      padded=True)
    return (np.abs(Z) ** 2).astype(np.float32)


def band_env(x_mono: np.ndarray, lo: float, hi: float, win_ms: float = 2.0) -> tuple[np.ndarray, float]:
    """Band-limited RMS envelope in dB at 1 kHz."""
    lo = max(30.0, lo)
    hi = min(SR / 2 * 0.95, hi)
    if hi <= lo * 1.2:
        hi = lo * 1.5
    sos = ss.butter(4, [lo, hi], btype="band", fs=SR, output="sos")
    y = ss.sosfiltfilt(sos, x_mono)
    w = max(1, int(SR * win_ms / 1000))
    e = np.sqrt(np.convolve(y * y, np.ones(w) / w, "same"))
    step = SR // 1000
    e = e[::step]
    return 20 * np.log10(e + 1e-9), 1000.0


# ----------------------------------------------------------------------------- features

def sig(x, c, w):
    return 1.0 / (1.0 + math.exp(-(x - c) / w))


def classify(f: dict) -> tuple[str, float, dict]:
    """Soft rules over the measured envelope and spectrum, calibrated on the media-use
    library (see SOUND.md). Each class scores 0..1; confidence is the top score scaled
    by its margin over the runner-up. "other" is the floor, so an event no rule fits
    is never forced into a class."""
    D, A, Dc = f["duration"], f["attack_ms"], f["decay_ms"]
    C, low, ton = f["centroid_hz"], f["low_share"], f["tonality"]
    sweep, n_on = f["sweep_oct_s"], f.get("micro_onsets", 1)
    gap, gcv = f.get("onset_gap_s", 0.0), f.get("onset_gap_cv", 0.0)
    ash = A / max(D * 1000, 1)
    s = {}
    s["click"] = sig(0.09 - D, 0, 0.02) * sig(30 - A, 0, 6) * sig(C, 1500, 400) * sig(2.5 - n_on, 0, 0.3)
    s["pop"] = sig(0.25 - D, 0, 0.05) * sig(20 - A, 0, 6) * sig(C, 250, 80) * sig(2500 - C, 0, 400) \
        * sig(ton, 0.35, 0.1) * sig(1.5 - n_on, 0, 0.3)
    s["impact"] = sig(40 - A, 0, 12) * sig(D, 0.15, 0.05) * sig(Dc, 150, 60) \
        * max(sig(low, 0.25, 0.08), sig(600 - C, 0, 150))
    s["whoosh"] = sig(D, 0.12, 0.04) * sig(2.5 - D, 0, 0.3) * sig(A, 30, 12) \
        * max(sig(0.4 - ton, 0, 0.1), sig(abs(sweep), 0.6, 0.2) * sig(0.75 - ton, 0, 0.08)) \
        * sig(ash, 0.12, 0.05) * sig(0.75 - ash, 0, 0.08) * sig(2.5 - n_on, 0, 0.4)
    s["riser"] = sig(D, 0.8, 0.2) * sig(A, 400, 100) * sig(ash, 0.35, 0.08) * (0.4 + 0.6 * sig(sweep, 0.3, 0.2))
    s["sub-drop"] = sig(300 - C, 0, 80) * sig(low, 0.5, 0.1) * sig(D, 0.25, 0.08) * sig(-sweep, 0.3, 0.15)
    s["chime"] = sig(ton, 0.5, 0.1) * sig(C, 700, 200) * sig(Dc, 250, 80)
    s["typing"] = sig(n_on, 2.5, 0.4) * sig(D, 0.25, 0.08) * sig(0.6 - gcv, 0, 0.12) \
        * sig(gap, 0.04, 0.01) * sig(0.3 - gap, 0, 0.05) * sig(0.7 - ton, 0, 0.1) * sig(C, 1000, 300)
    s["glitch"] = sig(n_on, 1.5, 0.4) * sig(gcv, 0.6, 0.12) * sig(0.6 - ton, 0, 0.1) * sig(D, 0.1, 0.04) \
        * sig(f["flatness"], 0.2, 0.06)
    s["other"] = 0.12
    ranked = sorted(s.items(), key=lambda kv: (-kv[1], CLASSES.index(kv[0])))
    top, second = ranked[0], ranked[1]
    conf = top[1] * top[1] / (top[1] + second[1] + 1e-9)
    return top[0], conf, s


# ----------------------------------------------------------------------------- moves

def load_anchors(path: str | None):
    """Find moves (dicts with t0/t1) and cuts (numbers) anywhere in a motion,
    fingerprint or hand-written moves file."""
    if not path:
        return [], []
    d = json.loads(Path(path).read_text())
    moves, cuts = [], []

    def walk(o, key=None):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, k)
        elif isinstance(o, list):
            if key == "moves" and o and isinstance(o[0], dict) and "t0" in o[0]:
                moves.extend(o)
            elif key == "cuts" and o and all(isinstance(v, (int, float)) for v in o):
                cuts.extend(float(v) for v in o)
            elif key == "cuts" and o and isinstance(o[0], dict) and "t" in o[0]:
                cuts.extend(float(v["t"]) for v in o)
            else:
                for v in o:
                    walk(v, key)

    if isinstance(d, list):
        walk(d, "moves")
    else:
        walk(d)
    anchors = []
    for i, m in enumerate(moves):
        prop = str(m.get("property") or m.get("prop") or m.get("kind") or m.get("name") or "move")
        mid = str(m.get("id") or m.get("name") or f"m{i:03d}")
        kf = m.get("keyframes") or {}
        start = kf.get("start", m.get("t0"))
        peak = kf.get("peak", m.get("peak_t"))
        land = kf.get("land", m.get("land_t", m.get("t1")))
        for key, t in (("start", start), ("peak", peak), ("land", land)):
            if t is not None:
                anchors.append({"t": float(t), "key": key, "move": mid, "property": prop})
    for j, t in enumerate(sorted(set(cuts))):
        anchors.append({"t": t, "key": "cut", "move": f"cut{j:03d}", "property": "cut"})
    anchors.sort(key=lambda a: (a["t"], a["key"], a["move"]))
    return anchors, moves


KEY_PRIORITY = {"cut": 0, "land": 1, "start": 2, "peak": 3}


def bind(ev: dict, anchors: list) -> dict:
    ref = ev["peak_t"] if ev["class"] in PEAK_ALIGNED else ev["t"]
    best = None
    for a in anchors:
        d = abs(ref - a["t"])
        if d <= P["bind_window_s"]:
            k = (round(d, 3), KEY_PRIORITY[a["key"]], a["move"])
            if best is None or k < best[0]:
                best = (k, a)
    if best is None:
        return {"bound_move": None, "bound_key": "none", "bound_property": None, "offset_to_move_s": None}
    a = best[1]
    return {"bound_move": a["move"], "bound_key": a["key"], "bound_property": a["property"],
            "offset_to_move_s": ev["t"] - a["t"], "align": "peak" if ev["class"] in PEAK_ALIGNED else "onset",
            "_anchor_t": a["t"]}


def chance_offset(anchors: list, duration: float) -> float | None:
    """Median nearest-anchor distance for a regular grid of times: what binding scores
    by accident against this move list."""
    if not anchors:
        return None
    ts = np.array([a["t"] for a in anchors])
    grid = np.linspace(0.5, max(0.6, duration - 0.5), 400)
    return float(np.median(np.abs(grid[:, None] - ts[None, :]).min(1)))


# ----------------------------------------------------------------------------- main analysis

class Ctx:
    """Everything the per-event measurements need, computed once."""


def build_ctx(video: str, stems_dir: str | None, device: str) -> Ctx:
    c = Ctx()
    x = decode(video)
    c.src_hash = sha256(video)
    vocals, nonvocal, c.method = separate(x, c.src_hash, Path(stems_dir) if stems_dir else None, device)
    L = min(len(vocals), len(nonvocal), len(x))
    c.x, c.vocals, c.nonvocal, c.L = x[:L], vocals[:L], nonvocal[:L], L
    c.duration = L / SR
    # Is there a voice at all? A music-only source still leaves a faint, garbled vocal
    # stem, and the voicing test fires on sung or synth harmonics, so gate on loudness.
    c.vo_lufs = lufs(c.vocals) if c.method == "demucs" else None
    c.nv_lufs = lufs(c.nonvocal)
    c.vo_present = c.method != "demucs" or (
        c.vo_lufs is not None and c.vo_lufs > P["vo_min_lufs"]
        and (c.nv_lufs is None or c.vo_lufs > c.nv_lufs - P["vo_under_bed_db"]))
    sp = speech_mask(c.vocals.mean(1) if c.method == "demucs" else c.x.mean(1))
    if not c.vo_present:
        sp = np.zeros_like(sp)
    nfr = int(math.ceil(L / HOP)) + 1
    c.sp = np.pad(sp, (0, max(0, nfr - len(sp))))[:nfr]
    gate = np.repeat(c.sp.astype(np.float32), HOP)[:L]
    ramp = int(0.02 * SR)
    gate = np.convolve(gate, np.ones(ramp) / ramp, "same").astype(np.float32)
    c.search = c.nonvocal + c.vocals * (1.0 - gate)[:, None] if c.method == "demucs" and c.vo_present else c.x
    c.fb, c.mel_f = mel_bank()
    c.ML = c.fb @ power_spec(c.search[:, 0])
    c.MR = c.fb @ power_spec(c.search[:, 1])
    c.M = c.ML + c.MR
    c.nF = c.M.shape[1]
    c.sp = np.pad(c.sp, (0, max(0, c.nF - len(c.sp))))[:c.nF]
    c.W = int(P["bed_window_s"] * FPS) | 1
    Mdb = 10 * np.log10(c.M + 1e-12)
    c.Mdb = Mdb
    c.Bdb = nd.median_filter(Mdb, size=(1, c.W), mode="nearest")
    c.Blin = 10 ** (c.Bdb / 10)
    c.E = np.clip(c.M - c.Blin, 0, None)

    def side(Mx):
        return np.clip(Mx - 10 ** (nd.median_filter(10 * np.log10(Mx + 1e-12), size=(1, c.W), mode="nearest") / 10),
                       0, None)
    c.EL, c.ER = side(c.ML), side(c.MR)
    X = np.clip(Mdb - c.Bdb, 0, None)
    top = np.sort(X, axis=0)[-P["topk_bands"]:].mean(0)
    c.act = nd.median_filter(top - np.median(X, axis=0), size=3)
    c.MN = c.fb @ (power_spec(c.nonvocal[:, 0]) + power_spec(c.nonvocal[:, 1]))
    c.MNdb = 10 * np.log10(c.MN + 1e-12)
    c.BN = 10 ** (nd.median_filter(c.MNdb, size=(1, c.W), mode="nearest") / 10)
    c.EN = np.clip(c.MN - c.BN, 0, None)
    Mv = c.fb @ (power_spec(c.vocals[:, 0]) + power_spec(c.vocals[:, 1]))
    c.w50 = max(1, int(0.05 * FPS))
    vpow = np.convolve(Mv.sum(0), np.ones(c.w50) / c.w50, "same")[:c.nF]
    c.vo_ref_db = float(10 * np.log10(np.percentile(vpow[c.sp], 90) + 1e-12)) if c.sp.any() else None
    npow = np.convolve(c.MN.sum(0), np.ones(c.w50) / c.w50, "same")[:c.nF]
    mpow = np.convolve((c.fb @ (power_spec(c.x[:, 0]) + power_spec(c.x[:, 1]))).sum(0), np.ones(c.w50) / c.w50,
                       "same")[:c.nF]
    c.mix_ref_db = float(10 * np.log10(np.percentile(mpow, 90) + 1e-12))
    # every level is quoted against the voice when there is one, else against the bed,
    # else against the mix; level_ref names which, and level_db_rel_mix is always there
    if c.vo_present and c.vo_ref_db is not None:
        c.level_ref, c.ref_db = "vo", c.vo_ref_db
    elif c.nv_lufs is not None and c.nv_lufs > -50:
        c.level_ref, c.ref_db = "music", float(10 * np.log10(np.percentile(npow, 90) + 1e-12))
    else:
        c.level_ref, c.ref_db = "mix", c.mix_ref_db
    c.mono = c.search.mean(1)
    c.mix_mono = c.x.mean(1)
    c.tempo, c.beats = beat_grid(c.nonvocal.mean(1))
    c.speech_on = [a / FPS for a, _ in regions(c.sp)]
    # whole-mix silence (digital or near), so level steps out of silence are not events
    mix_pow = (c.fb @ (power_spec(c.mix_mono))).sum(0)[:c.nF]
    c.mix_db = 10 * np.log10(mix_pow + 1e-12)
    return c


def mel_excess_features(c: Ctx, Es: np.ndarray) -> dict:
    tot = Es.sum(0)
    bandw = Es.sum(1)
    amp = np.sqrt(bandw)
    w = amp / (amp.sum() + 1e-18)  # amplitude weights: power weights let the bass decide
    cen = float((w * c.mel_f).sum())
    bw = float(np.sqrt((w * (c.mel_f - cen) ** 2).sum()))
    nz = bandw[bandw > bandw.max() * 1e-4]
    flat = float(np.exp(np.mean(np.log(nz))) / np.mean(nz)) if len(nz) else 0.0
    low = float(bandw[c.mel_f < 150].sum() / (bandw.sum() + 1e-18))
    fr_ok = tot > tot.max() * 0.1
    cent_t = (np.sqrt(Es) * c.mel_f[:, None]).sum(0) / (np.sqrt(Es).sum(0) + 1e-18)
    sweep = 0.0
    if fr_ok.sum() >= 4:
        tt = np.arange(Es.shape[1])[fr_ok] / FPS
        sweep = float(np.polyfit(tt, np.log2(cent_t[fr_ok] + 1), 1)[0])
    flux = np.clip(np.diff(10 * np.log10(Es + 1e-12), axis=1), 0, None).mean(0) if Es.shape[1] > 2 else np.zeros(1)
    n_on = 0
    if len(flux) > 3:
        pks, _ = ss.find_peaks(flux, height=max(3.0, flux.max() * 0.5), distance=max(1, int(0.04 * FPS)))
        n_on = int(len(pks))
    flux_cv = float(flux.std() / (flux.mean() + 1e-9)) if len(flux) > 1 else 0.0
    cdf = np.cumsum(bandw) / (bandw.sum() + 1e-18)
    lo_f = float(c.mel_f[min(NMELS - 1, int(np.searchsorted(cdf, 0.05)))])
    hi_f = float(c.mel_f[min(NMELS - 1, int(np.searchsorted(cdf, 0.95)))])
    return {"centroid_hz": cen, "bandwidth_hz": bw, "flatness": flat, "low_share": low, "sweep_oct_s": sweep,
            "micro_onsets": n_on, "flux_cv": flux_cv, "band": (lo_f, hi_f)}


def envelope_timing(env: np.ndarray, er: float, lo: int, hi: int, bg: float) -> tuple[int, int, int]:
    """Onset, peak and end indices of the event inside env[lo:hi] (dB at er Hz).
    Peak and end are read on a 20 ms power-smoothed copy, because a 1-2 ms envelope
    of noise dips far enough to end a whoosh at its first ripple; the onset is then
    refined on the fast envelope (first sample within 20 dB of the fast peak, or 6 dB
    over the bed) in the 40 ms before the smoothed onset, and a short hit takes its
    peak from the fast envelope too, so a click keeps millisecond timing."""
    lin = 10 ** (env / 10)
    w = max(1, int(0.02 * er))
    slow = 10 * np.log10(np.convolve(lin, np.ones(w) / w, "same") + 1e-14)
    lo, hi = max(0, lo), min(len(env), max(hi, lo + 1))
    ip = lo + int(np.argmax(slow[lo:hi]))
    pk = float(slow[ip])
    thr = max(bg + 6.0, pk - 20.0)
    j = ip
    while j > max(0, lo - int(0.05 * er)) and slow[j] > thr:
        j -= 1
    fpk = float(env[lo:hi].max())
    thr_f = max(bg + 6.0, fpk - 20.0)
    k0 = max(0, j - int(0.04 * er))
    above = np.where(env[k0:ip + 1] > thr_f)[0]
    on = k0 + int(above[0]) if len(above) else j
    k1 = min(len(env), ip + int(0.01 * er) + 1)
    if k1 > on:  # the sharp maximum up to the smoothed peak: a click keeps ms timing
        sharp = on + int(np.argmax(env[on:k1]))
        if env[sharp] >= fpk - 3.0 or (ip - on) / er < 0.025:
            ip = sharp
    thr_off = max(bg + 3.0, pk - 20.0)
    q = max(ip, on)
    while q < len(slow) - 1 and slow[q] > thr_off:
        q += 1
    return on, ip, q


def fine_timing(sig_mono: np.ndarray, t_a: float, t_b: float, band) -> dict | None:
    L = len(sig_mono)
    s0 = max(0, int((t_a - 0.35) * SR))
    s1 = min(L, int((t_b + 1.2) * SR))
    env, er = band_env(sig_mono[s0:s1], band[0] * 0.8, band[1] * 1.25)
    et = s0 / SR + np.arange(len(env)) / er
    pre = env[(et >= t_a - 0.33) & (et < t_a - 0.03)]
    bg = float(np.median(pre)) if len(pre) > 10 else float(np.percentile(env, 10))
    inside = np.where((et >= t_a - 0.03) & (et <= t_b + 0.03))[0]
    if not len(inside):
        return None
    on, ip, q = envelope_timing(env, er, int(inside[0]), int(inside[-1]) + 1, bg)
    q = min(q, int(np.searchsorted(et, t_b + 0.3)))
    t_on, peak_t = float(et[on]), float(et[ip])
    t_end = max(float(et[min(q, len(et) - 1)]), t_on + 0.005)
    post = env[(et >= t_end + 0.3) & (et < t_end + 0.9)]
    step = (float(np.median(post)) - bg) if len(post) > 50 else 0.0
    return {"t": t_on, "peak_t": peak_t, "t_end": t_end, "duration": t_end - t_on,
            "attack_ms": (peak_t - t_on) * 1000, "decay_ms": (t_end - peak_t) * 1000,
            "bg_db": bg, "peak_db": float(env[ip]), "step_db": step}


def pan_of(EL, ER):
    l, r = EL.sum(0), ER.sum(0)
    pan = float((r.sum() - l.sum()) / (r.sum() + l.sum() + 1e-18))
    n = len(l)
    if n < 4:
        return pan, 0.0
    h = n // 2
    p1 = (r[:h].sum() - l[:h].sum()) / (r[:h].sum() + l[:h].sum() + 1e-18)
    p2 = (r[h:].sum() - l[h:].sum()) / (r[h:].sum() + l[h:].sum() + 1e-18)
    return pan, float(p2 - p1)


def bar_repeat(c: Ctx, a: int, b: int, bands: np.ndarray) -> tuple[float, float]:
    """What the loop does not explain. The event's excess on the non-vocal stem is
    compared with the same stem one beat, half a bar, one, two and four bars away,
    either side, +-40 ms, each level-matched by the ratio of the two bed levels so a
    duck does not read as a difference. At the best-matching lag the unexplained
    energy is what exceeds the lagged patch. Returns (explained share, unexplained
    energy over the bed in dB): a loop hit is mostly explained and leaves little
    over the bed; an effect on top of a kick leaves its own energy unexplained."""
    if not c.tempo:
        return 0.0, 99.0
    per = 60.0 / c.tempo
    Lp = min(b - a, int(0.25 * FPS)) + 1
    a0 = max(0, a - 1)
    p0 = c.EN[bands, a0:a0 + Lp]
    bg0 = c.BN[bands, a0:a0 + Lp]
    tot = float(p0.sum())
    if tot <= 0:
        return 1.0, -99.0
    best = tot
    jit = int(0.04 * FPS)
    for kb in (1, 2, 4, 8, 16):
        for sgn in (-1, 1):
            base = int(round(a0 + sgn * kb * per * FPS))
            for s in range(base - jit, base + jit + 1):
                if s < 0 or s + Lp > c.nF or abs(s - a0) < Lp:
                    continue
                g = float(np.median(bg0) / (np.median(c.BN[bands, s:s + Lp]) + 1e-18))
                res = float(np.clip(p0 - c.EN[bands, s:s + Lp] * g, 0, None).sum())
                best = min(best, res)
    return 1.0 - best / tot, float(10 * np.log10(best / (bg0.sum() + 1e-18) + 1e-12))


def measure_region(c: Ctx, a: int, b: int, found_by: str):
    """Measure one candidate region of the searched signal. Returns (event, reject_reason)."""
    Es = c.E[:, a:b]
    if Es.sum() <= 0:
        return None, "empty"
    f = mel_excess_features(c, Es)
    ft = fine_timing(c.mono, a / FPS, b / FPS, f["band"])
    if ft is None:
        return None, "empty"
    if ft["duration"] < P["min_event_s"]:
        return None, "degenerate"
    epow = np.convolve(Es.sum(0), np.ones(c.w50) / c.w50, "same")
    lvl = float(10 * np.log10(epow.max() + 1e-12))
    rel = lvl - c.ref_db
    if lvl - c.mix_ref_db < P["min_level_rel_mix_db"]:
        return None, "quiet"
    pre_mix = c.mix_db[max(0, a - int(0.3 * FPS)):max(1, a - int(0.02 * FPS))]
    out_of_silence = len(pre_mix) and np.median(pre_mix) < np.percentile(c.mix_db, 50) - 25
    if ft["step_db"] > 8 and ft["duration"] > 0.25 or out_of_silence and ft["step_db"] > 6:
        return None, "step"
    nv_share = float(np.clip(c.MN[:, a:b] - c.Blin[:, a:b], 0, None).sum() / (Es.sum() + 1e-12))
    if c.method == "demucs" and c.vo_present and nv_share < 0.3 and any(0 <= s - ft["t_end"] <= 0.35 for s in c.speech_on) \
            and (rel is None or rel < -12):
        return None, "breath"
    bandw = Es.sum(1)
    bands = np.where(bandw >= bandw.max() * 0.05)[0]
    rep, unexpl_db = bar_repeat(c, a, b, bands)
    c.last_diag = {"rep": rep, "unexpl_db": unexpl_db, "rel": rel, "dur": ft["duration"], "t_on": ft["t"]}
    if rep >= P["music_repeat_sim"]:
        return None, "music"
    pan, pan_move = pan_of(c.EL[:, a:b], c.ER[:, a:b])
    s0 = max(0, int((ft["t"] - 0.01) * SR))
    env_e, er_e = band_env(c.mono[s0:min(c.L, int((ft["t_end"] + 0.02) * SR))], f["band"][0] * 0.8, f["band"][1] * 1.25)
    n_on, gap, gcv = onsets_in(env_e, er_e, 0, len(env_e))
    feats = dict(f, duration=ft["duration"], attack_ms=ft["attack_ms"], decay_ms=ft["decay_ms"],
                 tonality=tonality(c.mono, ft["t"], ft["duration"]), micro_onsets=n_on, onset_gap_s=gap,
                 onset_gap_cv=gcv)
    cls, conf, _ = classify(feats)
    snr = float(10 * np.log10(Es.sum() / (c.Blin[:, a:b][bands].sum() + 1e-12)))
    i0, i1 = max(0, int((ft["t"] - 0.03) * FPS)), int((ft["t_end"] + 0.03) * FPS) + 1
    ev = {"t": ft["t"], "peak_t": ft["peak_t"], "duration": ft["duration"], "class": cls, "confidence": conf,
          "level_db_rel_vo": rel, "level_db_rel_mix": lvl - c.mix_ref_db,
          "centroid_hz": f["centroid_hz"], "bandwidth_hz": f["bandwidth_hz"],
          "attack_ms": ft["attack_ms"], "decay_ms": ft["decay_ms"], "pan": pan, "pan_move": pan_move,
          "found_by": found_by,
          "_snr_db": snr, "_speech_overlap": float(c.sp[i0:i1].mean()) if i1 > i0 else 0.0,
          "_band": f["band"], "_feats": feats, "_repeat": rep, "_unexpl_db": unexpl_db, "_level_db": lvl}
    return ev, None


def detect_regions(c: Ctx):
    """Candidate events: onsets of the excess (half-wave rectified rise of the excess
    over the bed, summed over bands) inside active stretches, plus the start of any
    active stretch with no onset of its own (a riser fades in). Each candidate runs to
    the next onset or to where the excess falls back, capped at 4 s, so a kick and the
    effect laid on the next beat are judged separately."""
    active = c.act > P["off_db"]
    X = np.clip(c.Mdb - c.Bdb, 0, None)
    nov = np.clip(np.diff(X, axis=1, prepend=X[:, :1]), 0, None)
    nov = np.sort(nov, axis=0)[-P["topk_bands"]:].mean(0)
    nov = np.convolve(nov, np.ones(2) / 2, "same")
    pk, _ = ss.find_peaks(nov, height=P["onset_db"], distance=max(1, int(0.05 * FPS)))
    lab, _ = nd.label(active)
    hot = set(np.unique(lab[c.act > P["on_db"]]).tolist()) - {0}
    starts = []
    for i, sl in enumerate(nd.find_objects(lab), 1):
        if i not in hot:
            continue
        r0, r1 = sl[0].start, sl[0].stop
        inside = [int(p) for p in pk if r0 - 2 <= p < r1]
        if not inside or inside[0] - r0 > int(0.1 * FPS):
            starts.append(r0)
        starts.extend(max(r0, p - 1) for p in inside)
    starts = sorted(set(starts))
    cands = []
    for j, s in enumerate(starts):
        nxt = starts[j + 1] if j + 1 < len(starts) else c.nF
        e = s + 1
        cap = min(nxt, s + int(4 * FPS), c.nF)
        while e < cap and (active[e] or e - s < 2):
            e += 1
        if (e - s) / FPS >= P["min_event_s"]:
            cands.append((s, e))
    return cands


def hp(x: np.ndarray, f: float = 1500.0) -> np.ndarray:
    return ss.sosfiltfilt(ss.butter(4, f, btype="high", fs=SR, output="sos"), x)


def sharp_onsets(y: np.ndarray, rise_db: float = 12.0) -> np.ndarray:
    """Sample times where the 1 ms envelope of y rises rise_db within 6 ms over the
    quietest point of the previous 25 ms: the attack of a struck or clicked sample."""
    w = SR // 1000
    n = len(y) // w
    e = 10 * np.log10((y[:n * w].reshape(n, w) ** 2).mean(1) + 1e-14)
    prev_min = nd.minimum_filter1d(e, 25, origin=12)
    rise = nd.maximum_filter1d(e, 6, origin=-3) - prev_min
    cand = np.where((rise >= rise_db) & (e > np.percentile(e, 30)))[0]
    out, last = [], -10 ** 9
    for i in cand:
        if i - last > 60:
            j = i + int(np.argmax(np.diff(e[i:i + 8]))) if i + 8 < n else i
            out.append(j)
        last = i
    return np.array(out, dtype=int) * w


def ncc_max(A: np.ndarray, B: np.ndarray, maxlag: int):
    """Row-wise max normalised cross-correlation of every row of A against every row
    of B within +-maxlag samples. Returns (ncc, lag) matrices."""
    n = A.shape[1]
    nfft = 1 << int(math.ceil(math.log2(2 * n)))
    FA = np.fft.rfft(A, nfft)
    FB = np.fft.rfft(B, nfft)
    na = np.linalg.norm(A, axis=1) + 1e-12
    nb = np.linalg.norm(B, axis=1) + 1e-12
    best = np.zeros((len(A), len(B)))
    lag = np.zeros((len(A), len(B)), dtype=int)
    lags = np.r_[np.arange(0, maxlag + 1), np.arange(-maxlag, 0)]
    for i in range(len(A)):
        cc = np.fft.irfft(FA[i][None, :] * np.conj(FB), nfft)
        cc = np.concatenate([cc[:, :maxlag + 1], cc[:, -maxlag:]], 1) / (na[i] * nb[:, None])
        k = np.argmax(cc, 1)
        best[i] = cc[np.arange(len(B)), k]
        lag[i] = lags[k]
    return best, lag


def recurrence_pass(c: Ctx, events: list) -> tuple[list, int]:
    """Editors reuse samples. A sharp transient under speech that matches another one
    sample for sample, or matches an effect already found, is an effect even when
    Demucs filed it under vocals. Returns new events found this way."""
    y = hp(c.mix_mono)
    on = sharp_onsets(y)
    covered = np.zeros(c.L, bool)
    for e in events:
        covered[max(0, int((e["t"] - 0.03) * SR)):int((e["t"] + e["duration"] + 0.03) * SR)] = True
    spS = np.repeat(c.sp, HOP)[:c.L]
    cand = [int(s) for s in on if s < c.L - SR // 10 and spS[s] and not covered[s]]
    pre, n = int(0.003 * SR), int(0.04 * SR)

    def snip(s):
        seg = y[max(0, s - pre):s - pre + n]
        return np.pad(seg, (0, n - len(seg)))
    temps = [e for e in events if e["duration"] <= 0.6 and e["_snr_db"] >= 8]
    rows = [snip(s) for s in cand]
    trows = [snip(int(e["t"] * SR)) for e in temps]
    if not rows:
        return [], 0
    A = np.array(rows)
    thr = P["recur_ncc"]
    linked = {}
    if len(cand) > 1:
        cc, lg = ncc_max(A, A, int(0.004 * SR))
        np.fill_diagonal(cc, 0)
        for i in range(len(cand)):
            for j in np.where(cc[i] >= thr)[0]:
                if abs(cand[i] - cand[j]) > 0.1 * SR and (c.tempo is None or not on_grid_pair(c, cand[i], cand[j])):
                    linked.setdefault(i, []).append(("pair", j, float(cc[i, j])))
    if trows:
        ct, _ = ncc_max(A, np.array(trows), int(0.004 * SR))
        for i in range(len(cand)):
            for j in np.where(ct[i] >= thr)[0]:
                linked.setdefault(i, []).append(("template", j, float(ct[i, j])))
    new = []
    per_sample_music = {}

    def loop_member(s):
        if s not in per_sample_music:
            a = int(s / HOP)
            rp, ud = bar_repeat(c, a, a + int(0.06 * FPS), np.arange(NMELS))
            per_sample_music[s] = rp >= P["music_repeat_sim"]
        return per_sample_music[s]
    for i in sorted(linked):
        s = cand[i]
        if loop_member(s):
            continue
        linked[i] = [r for r in linked[i] if r[0] == "template" or not loop_member(cand[r[1]])]
        if not linked[i]:
            continue
        kind, j, score = max(linked[i], key=lambda r: r[2])
        if kind == "template":
            src = temps[j]
            gain = proj_gain(y, s, trows[j], pre)
            ev = {k: v for k, v in src.items() if not k.startswith("_")}
            ev.update({"t": s / SR, "peak_t": s / SR + src["peak_t"] - src["t"],
                       "level_db_rel_vo": src["level_db_rel_vo"] + 20 * math.log10(max(gain, 1e-6)),
                       "level_db_rel_mix": src["level_db_rel_mix"] + 20 * math.log10(max(gain, 1e-6)),
                       "confidence": src["confidence"] * min(1.0, score / 0.9),
                       "found_by": "template", "_snr_db": 0.0, "_band": src["_band"], "_feats": src["_feats"]})
        else:
            ev = measure_recurrent(c, s, [cand[j]], y, score)
            if ev is None:
                continue
        i0, i1 = int(ev["t"] * FPS), int((ev["t"] + ev["duration"]) * FPS) + 1
        ev["_speech_overlap"] = float(c.sp[i0:i1].mean()) if i1 > i0 else 1.0
        new.append(ev)
    return new, len(cand)


def on_grid_pair(c: Ctx, s1: int, s2: int) -> bool:
    """True when two transients sit a whole number of half-beats apart: a drum loop
    repeats itself, which is not sample reuse by an editor."""
    per = 60.0 / c.tempo / 2
    d = abs(s1 - s2) / SR
    k = round(d / per)
    return k >= 1 and abs(d - k * per) <= 0.02


def proj_gain(y, s, temp, pre):
    seg = y[max(0, s - pre):max(0, s - pre) + len(temp)]
    seg = np.pad(seg, (0, len(temp) - len(seg)))
    return float(abs(np.dot(seg, temp)) / (np.dot(temp, temp) + 1e-12))


def measure_recurrent(c: Ctx, s: int, partners: list, y: np.ndarray, score: float):
    """Measure a transient found by recurrence. Its onset is the sharp onset itself;
    its length is how long the occurrences stay correlated (the shared sample ends
    where they diverge); its spectrum is that of the occurrences averaged, which
    cancels the uncorrelated voice under each."""
    occ = [s] + list(partners)
    pre = int(0.003 * SR)
    win = int(1.0 * SR)
    if any(q - pre < 0 or q - pre + win > c.L for q in occ):
        return None
    segs = np.array([c.mix_mono[q - pre:q - pre + win] for q in occ])
    step = int(0.01 * SR)
    n_shared = 0
    misses = 0
    for k in range(0, win - step, step):
        A, B = segs[0, k:k + step], segs[1, k:k + step]
        r = float(np.dot(A, B) / (np.linalg.norm(A) * np.linalg.norm(B) + 1e-12))
        if r >= 0.5:
            n_shared = k + step
            misses = 0
        else:
            misses += 1
            if misses >= 2:
                break
    dur = max(0.01, n_shared / SR - 0.003)
    avg = segs.mean(0)[:pre + int(dur * SR)]
    Pm = c.fb @ power_spec(np.pad(avg, (SR // 10, SR // 10)))
    f = mel_excess_features(c, Pm)
    env, _ = band_env(avg, f["band"][0] * 0.8, f["band"][1] * 1.25)
    sm = np.convolve(env, np.ones(3) / 3, "same")
    ip = int(np.argmax(sm[pre // 44:]) + pre // 44)
    pk = sm[ip]
    q = ip
    while q < len(sm) - 1 and sm[q] > pk - 20:
        q += 1
    attack = max(0.0, (ip - pre / 44.1))
    decay = float(q - ip)
    lvl = float(10 * np.log10(np.convolve(Pm.sum(0), np.ones(c.w50) / c.w50, "same").max() + 1e-12))
    rel = lvl - c.ref_db
    sl = c.x[s:s + int(dur * SR)]
    l, r = float((sl[:, 0] ** 2).sum()), float((sl[:, 1] ** 2).sum())
    feats = dict(f, duration=dur, attack_ms=attack, decay_ms=decay, tonality=tonality(avg, pre / SR, dur))
    cls, conf, _ = classify(feats)
    return {"t": s / SR, "peak_t": s / SR + attack / 1000.0, "duration": dur, "class": cls,
            "confidence": conf * min(1.0, score / 0.9), "level_db_rel_vo": rel,
            "level_db_rel_mix": lvl - c.mix_ref_db,
            "centroid_hz": f["centroid_hz"], "bandwidth_hz": f["bandwidth_hz"],
            "attack_ms": attack, "decay_ms": decay,
            "pan": (r - l) / (r + l + 1e-12), "pan_move": 0.0, "found_by": "recurrence",
            "_snr_db": 0.0, "_band": f["band"], "_feats": feats}


def analyse(video: str, moves_path: str | None, out: str, stems_dir: str | None, device: str,
            plot: str | None) -> dict:
    c = build_ctx(video, stems_dir, device)
    events, dropped = [], {}
    rejected = []
    for a, b in detect_regions(c):
        c.last_diag = None
        ev, why = measure_region(c, a, b, "excess")
        if ev is None:
            dropped[why] = dropped.get(why, 0) + 1
            rejected.append({"t": a / FPS, "t_end": b / FPS, "why": why, **(c.last_diag or {})})
        else:
            events.append(ev)
    events.sort(key=lambda e: e["t"])
    ded = []
    for e in events:
        if ded and abs(e["t"] - ded[-1]["t"]) < 0.03:
            continue
        ded.append(e)
    events = ded
    new, n_cand = recurrence_pass(c, events)
    events = sorted(events + new, key=lambda e: e["t"])

    anchors, moves = load_anchors(moves_path)
    out_dir = Path(out).resolve().parent
    clip_dir = out_dir / "clips"
    for i, e in enumerate(events):
        e.update(bind(e, anchors) if anchors else
                 {"bound_move": None, "bound_key": "none", "bound_property": None, "offset_to_move_s": None})
        prev_end = events[i - 1]["t"] + events[i - 1]["duration"] if i else -1e9
        next_t = events[i + 1]["t"] if i + 1 < len(events) else 1e9
        isolated = prev_end < e["t"] - 0.05 and next_t > e["t"] + e["duration"] + 0.05
        e["clean"] = bool(e["found_by"] == "excess" and e["_speech_overlap"] == 0 and isolated
                          and e["_snr_db"] >= P["clean_snr_db"])
        e["clip"] = None
        if e["clean"]:
            clip_dir.mkdir(parents=True, exist_ok=True)
            name = f"event_{i:03d}.wav"
            export_clip(c.search, e, clip_dir / name)
            e["clip"] = str((clip_dir / name).relative_to(out_dir))

    res = summarise(events, anchors, moves, c.duration, c.method)
    res["music"] = music_stats(c, events, anchors)
    res["vo"] = {"present": bool(c.vo_present), "lufs": c.vo_lufs, "ref_db_p90_50ms": c.vo_ref_db,
                 "speech_share": float(c.sp.mean())}
    res["level_ref"] = c.level_ref
    res["level_ref_db"] = c.ref_db
    res["mix_ref_db"] = c.mix_ref_db
    res["source"] = {"path": str(Path(video).resolve()), "sha256": c.src_hash, "duration": c.duration}
    dropped["recurrence_candidates"] = n_cand
    res["dropped"] = dict(sorted(dropped.items()))
    res["params"] = P
    import os
    if os.environ.get("SOUND_DEBUG") == "1":
        res["_rejected"] = rejected
    if plot:
        draw(plot, c.Mdb, c.act, c.sp, events, anchors, c.duration, video)
    return res


def tonality(mono: np.ndarray, t: float, dur: float) -> float:
    """Share of the event's power in spectral peaks standing 8 dB over the local
    spectral envelope (a 15-bin median across frequency), median over its loud frames
    in the first 400 ms: about 0.8 to 1 for a chime, ping or sine pop, under 0.2 for a
    whoosh, click or any noise burst."""
    s0 = int(max(0.0, t) * SR)
    s1 = min(len(mono), s0 + int(max(0.03, min(dur, 0.4)) * SR))
    seg = mono[s0:s1]
    if len(seg) < 2048:
        seg = np.pad(seg, (0, 2048 - len(seg)))
    f, _, Z = ss.stft(seg, fs=SR, nperseg=2048, noverlap=1536)
    Pw = np.abs(Z) ** 2 + 1e-14
    band = (f > 80) & (f < 12000)
    Pw = Pw[band]
    Pdb = 10 * np.log10(Pw)
    env = nd.median_filter(Pdb, size=(15, 1), mode="nearest")
    peak = Pdb - env > 8.0
    fe = Pw.sum(0)
    loud = fe > fe.max() * 0.05
    share = (Pw * peak).sum(0) / fe
    return float(np.median(share[loud])) if loud.any() else 0.0


def onsets_in(env: np.ndarray, er: float, lo: int, hi: int) -> tuple[int, float, float]:
    """Separate hits inside an event, counted on a 12 ms power-smoothed envelope so the
    ripple of a bass or tonal waveform is not counted: a hit is a rise of 10 dB within
    15 ms from the quietest point before it, 40 ms after the previous hit and within
    25 dB of the loudest. Returns (count, median gap s, gap coefficient of variation),
    the last two telling a regular typing run from a stuttering glitch."""
    seg = env[max(0, lo):max(lo + 1, hi)]
    if len(seg) < 10:
        return 1, 0.0, 0.0
    w = max(1, int(0.012 * er))
    sm = 10 * np.log10(np.convolve(10 ** (seg / 10), np.ones(w) / w, "same") + 1e-14)
    k = max(1, int(0.015 * er))
    floor = nd.minimum_filter1d(sm, k, origin=(k - 1) // 2)
    rise = sm - floor
    top = sm.max()
    hits, last = [], -10 ** 9
    for i in np.where((rise >= 10) & (sm > top - 25))[0]:
        if i - last >= int(0.04 * er):
            hits.append(i)
            last = i
    if len(hits) < 2:
        return max(1, len(hits)), 0.0, 0.0
    g = np.diff(hits) / er
    return int(len(hits)), float(np.median(g)), float(g.std() / (g.mean() + 1e-9))


def lufs(x: np.ndarray) -> float | None:
    import pyloudnorm as pyln
    if len(x) < SR * 0.5:
        return None
    v = pyln.Meter(SR).integrated_loudness(x.astype(np.float64))
    return float(v) if np.isfinite(v) else None


def beat_grid(mono: np.ndarray):
    import librosa
    y = ss.resample_poly(mono, 1, 2)  # 22.05 kHz
    oenv = librosa.onset.onset_strength(y=y, sr=SR // 2, hop_length=512)
    if oenv.max() <= 0:
        return None, np.array([])
    tempo, beats = librosa.beat.beat_track(onset_envelope=oenv, sr=SR // 2, hop_length=512)
    tempo = float(np.atleast_1d(tempo)[0])
    return (tempo if tempo > 0 else None), librosa.frames_to_time(beats, sr=SR // 2, hop_length=512)



def export_clip(sig2: np.ndarray, e: dict, path: Path):
    """Cut [t-10 ms, end+60 ms], subtract the local bed spectrum (Wiener mask from the
    median spectrum of the 1 s either side), fade 2 ms in and 15 ms out."""
    t0, t1 = e["t"] - 0.01, e["t"] + e["duration"] + 0.06
    c0, c1 = max(0, int((t0 - 1.0) * SR)), min(len(sig2), int((t1 + 1.0) * SR))
    out = []
    for ch in range(2):
        y = sig2[c0:c1, ch].astype(np.float64)
        f, tt, Z = ss.stft(y, fs=SR, nperseg=1024, noverlap=768)
        tt = tt + c0 / SR
        ctx = (tt < e["t"] - 0.03) | (tt > e["t"] + e["duration"] + 0.08)
        if ctx.sum() >= 5:
            bed = np.median(np.abs(Z[:, ctx]) ** 2, axis=1, keepdims=True)
            g = np.sqrt(np.clip(1 - 1.5 * bed / (np.abs(Z) ** 2 + 1e-14), 0.03, 1))
            Z = Z * g
        _, yy = ss.istft(Z, fs=SR, nperseg=1024, noverlap=768)
        s0 = int((t0 - c0 / SR) * SR)
        out.append(yy[max(0, s0):max(0, s0) + int((t1 - t0) * SR)])
    n = min(len(o) for o in out)
    clip = np.stack([o[:n] for o in out], 1)
    fi, fo = int(0.002 * SR), int(0.015 * SR)
    clip[:fi] *= np.linspace(0, 1, fi)[:, None]
    clip[-fo:] *= np.linspace(1, 0, fo)[:, None]
    sf.write(path, clip.astype(np.float32), SR, subtype="PCM_16")


# ----------------------------------------------------------------------------- summary

def stats(vals):
    v = [x for x in vals if x is not None]
    if not v:
        return {"median": None, "p10": None, "p90": None, "n": 0}
    return {"median": pct(v, 50), "p10": pct(v, 10), "p90": pct(v, 90), "n": len(v)}


def summarise(events, anchors, moves, duration, method) -> dict:
    bound = [e for e in events if e["bound_key"] != "none"]
    offs = [e["offset_to_move_s"] for e in bound]
    by_class = {}
    for c in sorted({e["class"] for e in bound}):
        by_class[c] = stats([e["offset_to_move_s"] for e in bound if e["class"] == c])
    s_all = stats(offs)
    sync = {"median_offset_s": s_all["median"], "p10": s_all["p10"], "p90": s_all["p90"], "n_bound": len(bound),
            "by_class": by_class, "chance_median_abs_s": chance_offset(anchors, duration),
            "median_abs_offset_s": pct([abs(o) for o in offs], 50) if offs else None}
    classes = {}
    for c in sorted({e["class"] for e in events}):
        ev = [e for e in events if e["class"] == c]
        props = {}
        for e in ev:
            k = e["bound_property"] or "none"
            props[k] = props.get(k, 0) + 1
        classes[c] = {
            "count": len(ev),
            "median_duration": pct([e["duration"] for e in ev], 50),
            "median_centroid_hz": pct([e["centroid_hz"] for e in ev], 50),
            "median_bandwidth_hz": pct([e["bandwidth_hz"] for e in ev], 50),
            "median_level_db_rel_vo": pct([e["level_db_rel_vo"] for e in ev if e["level_db_rel_vo"] is not None], 50)
            if any(e["level_db_rel_vo"] is not None for e in ev) else None,
            "median_level_db_rel_mix": pct([e["level_db_rel_mix"] for e in ev], 50),
            "median_attack_ms": pct([e["attack_ms"] for e in ev], 50),
            "median_decay_ms": pct([e["decay_ms"] for e in ev], 50),
            "median_pan": pct([e["pan"] for e in ev], 50),
            "median_pan_move": pct([e["pan_move"] for e in ev], 50),
            "bound_property_share": {k: v / len(ev) for k, v in sorted(props.items())},
            "clean_clips": sorted(e["clip"] for e in ev if e["clip"]),
        }
    # binding rules: (property, class, key) with the median offset, and how often a
    # move of that property gets a sound at all (coverage), so placement never over-scores
    n_by_prop = {}
    for m in moves:
        p = str(m.get("property") or m.get("prop") or m.get("kind") or m.get("name") or "move")
        n_by_prop[p] = n_by_prop.get(p, 0) + 1
    n_by_prop["cut"] = len({a["move"] for a in anchors if a["key"] == "cut"})
    groups = {}
    for e in bound:
        groups.setdefault((e["bound_property"], e["class"], e["bound_key"]), []).append(e)
    rules = []
    for (prop, cls, key), ev in groups.items():
        rules.append({
            "move_property": prop, "class": cls, "key": key,
            "offset_s": pct([e["offset_to_move_s"] for e in ev], 50),
            "peak_offset_s": pct([e["peak_t"] - e["_anchor_t"] for e in ev], 50),
            "align": ev[0]["align"], "n": len(ev),
            "coverage": len(ev) / n_by_prop[prop] if n_by_prop.get(prop) else None,
            "level_db_rel_vo": pct([e["level_db_rel_vo"] for e in ev if e["level_db_rel_vo"] is not None], 50)
            if any(e["level_db_rel_vo"] is not None for e in ev) else None,
            "level_db_rel_mix": pct([e["level_db_rel_mix"] for e in ev], 50),
            "pan": pct([e["pan"] for e in ev], 50),
        })
    rules.sort(key=lambda r: (-r["n"], r["move_property"], r["class"], r["key"]))
    import os
    dbg = os.environ.get("SOUND_DEBUG") == "1"
    public = []
    for e in events:
        public.append({k: (list(v) if isinstance(v, tuple) else v) for k, v in e.items()
                       if dbg or not k.startswith("_")})
    return {"method": method, "events": public,
            "density_per_10s": len(events) / duration * 10 if duration else 0.0,
            "sync": sync, "classes": classes, "binding_rules": rules,
            "moves_seen": {k: v for k, v in sorted(n_by_prop.items())}}


def beat_phase(beats: np.ndarray, times) -> np.ndarray:
    """Where each time falls inside its beat, 0 at the beat and 0.5 halfway, using the
    local beat interval. Its circular concentration (beat lock, 0 random to 1 locked)
    does not depend on the tracker getting the phase right, which it often does not."""
    out = []
    for x in times:
        j = int(np.searchsorted(beats, x)) - 1
        if 0 <= j < len(beats) - 1:
            out.append((x - beats[j]) / (beats[j + 1] - beats[j]))
    return np.array(out)


def music_stats(c, events, anchors) -> dict:
    """The bed with every effect cut out: integrated LUFS, tempo, whether cuts land on
    beats, and the duck as the median bed level inside speech minus inside pauses,
    300 ms in from each edge and ignoring stretches where the whole mix is silent."""
    nonvocal, sp, L = c.nonvocal, c.sp, c.L
    keep = np.ones(L, bool)
    for e in events:
        keep[max(0, int((e["t"] - 0.02) * SR)):int((e["t"] + e["duration"] + 0.05) * SR)] = False
    bed = nonvocal[keep]
    lu = lufs(bed)
    blk = int(0.4 * SR)
    nb = len(bed) // blk
    act_share = 0.0
    if nb:
        r = np.sqrt((bed[:nb * blk].mean(1).reshape(nb, blk) ** 2).mean(1))
        act_share = float((20 * np.log10(r + 1e-9) > -55).mean())
    present = bool(lu is not None and lu > -45 and act_share > 0.4)
    # duck: at every speech-to-pause boundary with a pause of 0.5 s or more, the bed's
    # 200 ms level over the last 0.5 s of speech against its 80th percentile inside the
    # pause from 0.2 s in; the median over boundaries. Local, so the music's own
    # build across the piece does not read as ducking.
    fr = int(0.05 * SR)
    nfr = L // fr
    pw = (nonvocal[:nfr * fr].mean(1).reshape(nfr, fr) ** 2).mean(1)
    pw = np.convolve(pw, np.ones(4) / 4, "same")
    kf = keep[:nfr * fr].reshape(nfr, fr).all(1)
    t = (np.arange(nfr) + 0.5) * fr / SR
    spt = sp[np.minimum((t * FPS).astype(int), len(sp) - 1)].astype(bool)
    ducks = []
    for r0, r1 in regions(~spt):
        if r0 == 0 or (r1 - r0) * 0.05 < 0.5:
            continue
        before = [i for i in range(max(0, r0 - 10), r0) if kf[i] and spt[i]]
        inside = [i for i in range(r0 + 4, r1) if kf[i]]
        if len(before) >= 4 and len(inside) >= 4:
            ducks.append(10 * np.log10(np.median(pw[before]) + 1e-14)
                         - 10 * np.log10(np.percentile(pw[inside], 80) + 1e-14))
    duck = float(np.median(ducks)) if present and c.vo_present and ducks else None
    cuts = [a["t"] for a in anchors if a["key"] == "cut"]
    on_beat = chance = vs = phase = None
    if present and cuts and len(c.beats) > 2:
        on_beat = float(np.mean([np.min(np.abs(c.beats - x)) <= P["beat_tol_s"] for x in cuts]))
        chance = min(1.0, 2 * P["beat_tol_s"] * c.tempo / 60.0)
        ph = beat_phase(c.beats, cuts)
        if len(ph):
            z = np.exp(2j * np.pi * ph).mean()
            vs, phase = float(abs(z)), float((np.angle(z) / (2 * np.pi)) % 1.0)
    return {"present": present, "lufs": lu, "tempo_bpm": c.tempo if present else None,
            "cuts_on_beat_share": on_beat, "cuts_on_beat_chance": chance,
            "cuts_beat_lock": vs, "cuts_beat_phase": phase, "duck_db_under_vo": duck, "active_share": act_share,
            "duck_boundaries": len(ducks)}


# ----------------------------------------------------------------------------- plot

def draw(path, Mdb, act, sp, events, anchors, duration, video):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    segs = max(1, int(math.ceil(duration / 15)))
    fig, axes = plt.subplots(segs, 1, figsize=(22, 4.2 * segs), squeeze=False)
    colors = {"click": "#ff3b30", "pop": "#ff9500", "impact": "#ffcc00", "whoosh": "#34c759", "riser": "#00c7be",
              "sub-drop": "#5856d6", "chime": "#af52de", "typing": "#ff2d55", "glitch": "#a2845e", "other": "#ffffff"}
    for s in range(segs):
        ax = axes[s, 0]
        t0, t1 = s * 15, min(duration, (s + 1) * 15)
        f0, f1 = int(t0 * FPS), int(t1 * FPS)
        ax.imshow(Mdb[:, f0:f1], origin="lower", aspect="auto", cmap="magma", extent=[t0, t1, 0, NMELS],
                  vmin=np.percentile(Mdb, 5), vmax=np.percentile(Mdb, 99.7))
        tt = np.arange(f0, f1) / FPS
        ax.plot(tt, np.clip(act[f0:f1], 0, 30) * 2, color="cyan", lw=0.7, alpha=0.8)
        spx = sp[f0:f1].astype(float)
        ax.fill_between(tt[:len(spx)], NMELS - 4, NMELS - 4 + 4 * spx[:len(tt)], color="#4aa3ff", alpha=0.6, step="mid")
        for a in anchors:
            if t0 <= a["t"] < t1:
                ax.plot([a["t"], a["t"]], [0, 4 if a["key"] != "cut" else 10], color="#9be7ff" if a["key"] != "cut" else "white", lw=0.8)
        for i, e in enumerate(events):
            if t0 <= e["t"] < t1:
                c = colors.get(e["class"], "white")
                ax.axvline(e["t"], color=c, lw=1.2, ls="--", alpha=0.95)
                ax.text(e["t"], NMELS - 12 - (i % 3) * 8, f"{i}:{e['class']}{'*' if e['clean'] else ''}",
                        color=c, fontsize=8, rotation=0, ha="left",
                        bbox=dict(facecolor="black", alpha=0.5, pad=1, lw=0))
        ax.set_xlim(t0, t0 + 15)
        ax.set_ylabel("mel band")
    axes[0, 0].set_title(f"{Path(video).name}: searched signal (non-vocal + vocal outside speech). dashed = events, "
                         f"* = clean clip, cyan = excess curve, blue strip = speech, ticks = move keyframes, tall = cuts")
    fig.tight_layout()
    fig.savefig(path, dpi=70)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("--moves", help="motion.json, fingerprint.json or any JSON with moves[] (t0, t1, keyframes) and cuts[]")
    ap.add_argument("--out", required=True)
    ap.add_argument("--stems-dir", help="cache for the Demucs stems (vocals.wav, nonvocal.wav, ...)")
    ap.add_argument("--device", default="cpu", choices=["auto", "cpu", "mps"],
                    help="cpu (default) is bit-reproducible across runs and machines; mps is faster and differs in the 4th decimal")
    ap.add_argument("--plot", help="write a spectrogram PNG with event markers (the listen-proxy check)")
    a = ap.parse_args()
    emit(analyse(a.video, a.moves, a.out, a.stems_dir, a.device, a.plot), a.out)


if __name__ == "__main__":
    main()
