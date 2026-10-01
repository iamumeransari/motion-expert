#!/usr/bin/env python3
"""Score a render's fingerprint against its source style and export beat-matched sheets.

    compare.py SOURCE_FP RENDER_FP --out DIR [--mode novel|replica]
               [--source-video SRC.mp4] [--render-video RENDER.mp4]
               [--render-words words.json] [--source-words words.json] [--beats 8]

Every dotted path in the source's "tolerance" block is scored (pass or fail, distance
outside the band, the direction to move and a concrete fix). Built-in bands cover the
paths the tolerance block leaves out. On top of those it scores the energy curve's
shape (DTW after time-normalisation, with where the curves diverge most as
timestamps in both videos), palette match (share-weighted CIEDE2000 from each source
swatch to its nearest render swatch), curve match (each high-confidence source move
against its nearest render move by property), the shot-length distribution (two-sample
KS), structural beat alignment (cuts and energy peaks mapped by normalised time),
cut-to-VO offset, and the sound layer (density, sync per class, level, class mix,
timbre, music bed).

Replica mode is frame-time aligned and tight: cuts, moves and sound events are matched
one to one against the source's own. Novel mode is distributional only, since subject
and length differ, and skips every length-dependent count.

Writes DIR/report.json, DIR/report.md, DIR/frames/*.png and DIR/sheets/sheet-NN.png.
Exit 0 when every scored metric passes, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"

# Built-in bands for paths the source's tolerance block does not carry. "rel" is a
# share of the source value, "abs" an absolute +/- around it. Novel mode drops the
# entries marked replica_only. A tolerance entry for the same path always wins.
DEFAULT_BANDS = {
    "timing.cuts_per_10s": {"rel": 0.20, "why": "cut rhythm"},
    "timing.shot_length.median": {"rel": 0.20, "why": "typical shot length"},
    "timing.shot_length.p10": {"rel": 0.30, "why": "shortest shots"},
    "timing.shot_length.p90": {"rel": 0.30, "why": "longest shots"},
    "timing.hold_share": {"abs": 0.08, "why": "share of time the frame is still"},
    "timing.hard_cut_share": {"abs": 0.20, "why": "hard cuts against dissolves"},
    "motion.energy_stats.mean": {"rel": 0.25, "why": "overall amount of motion"},
    "motion.energy_stats.p90": {"rel": 0.25, "why": "how hard the peaks hit"},
    "motion.move_stats.per_10s": {"rel": 0.30, "why": "move density"},
    "motion.move_stats.overshoot_share": {"abs": 0.20, "why": "how often moves overshoot"},
    "look.margins.top": {"abs": 0.03, "why": "safe area"},
    "look.margins.right": {"abs": 0.03, "why": "safe area"},
    "look.margins.bottom": {"abs": 0.03, "why": "safe area"},
    "look.margins.left": {"abs": 0.03, "why": "safe area"},
    "look.density": {"rel": 0.25, "why": "how full a frame gets"},
    "look.sharpness": {"rel": 0.30, "why": "edge crispness and grain"},
    "look.aspect": {"abs": 0.01, "why": "format", "replica_only": True},
    "delivery.wpm": {"rel": 0.08, "why": "speaking pace"},
    "delivery.pauses.median": {"abs": 0.08, "why": "typical pause"},
    "delivery.pauses.p90": {"abs": 0.15, "why": "long pauses"},
    "delivery.pauses.per_min": {"rel": 0.25, "why": "how often the voice stops"},
    "delivery.vo_lufs": {"abs": 2.0, "why": "voice loudness"},
    "delivery.music_lufs": {"abs": 2.0, "why": "music loudness"},
}

# Built-in thresholds for the derived checks; override any of them with a tolerance
# entry under "compare.<id>" in the source fingerprint.
DERIVED = {
    "novel": {"energy_shape": (0.75, None), "energy_arc": (None, 0.22), "palette_de": (None, 6.0),
              "palette_share": (None, 0.25), "curve_match_share": (0.75, None), "shot_ks": (None, 0.35),
              "beat_alignment": (0.60, None), "luma_emd": (None, 0.10), "vo_cut_offset": (-0.10, 0.04)},
    "replica": {"energy_shape": (0.85, None), "energy_arc": (None, 0.12), "palette_de": (None, 4.0),
                "palette_share": (None, 0.15), "curve_match_share": (0.90, None), "shot_ks": (None, 0.20),
                "beat_alignment": (0.85, None), "luma_emd": (None, 0.05), "vo_cut_offset": (-0.10, 0.04),
                "cut_offset_median": (None, 0.08), "cut_offset_max": (None, 0.20)},
}
CURVE = {"novel": {"bezier": 0.15, "dur_lo": 0.85, "dur_hi": 1.15, "overshoot": 0.05},
         "replica": {"bezier": 0.10, "dur_lo": 0.90, "dur_hi": 1.10, "overshoot": 0.03}}
SOUND = {"sync_ms": 30, "spread_ms": 40, "level_db": 3.0, "mix_tv": {"novel": 0.25, "replica": 0.15},
         "density_rel": 0.25, "centroid_oct": 0.30, "env_ratio": 1.5, "dur_ratio": 1.33,
         "music_lufs": 2.0, "tempo_rel": 0.04, "duck_db": 2.0, "beat_share": 0.15, "bound_share": 0.25,
         "event_match_s": 0.10}

LENGTH_DEPENDENT = {"cuts", "dissolves", "shot_lengths", "holds", "values", "raw", "peak_times", "moves",
                    "count", "words", "duration", "events", "high_confidence", "peak_raw", "frames"}


# ---------------------------------------------------------------- small helpers

def get(d, path, default=None):
    cur = d
    for k in path.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        elif isinstance(cur, list) and k.isdigit() and int(k) < len(cur):
            cur = cur[int(k)]
        else:
            return default
    return cur


def num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def f2(x, nd=2):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def conf_value(c):
    if num(c):
        return float(c)
    return {"high": 0.9, "medium": 0.6, "low": 0.3}.get(str(c).lower(), 0.0)


def cut_times(fp):
    cuts = []
    for c in get(fp, "timing.cuts", []) or []:
        t = c if num(c) else (c.get("t") if isinstance(c, dict) else None)
        if num(t):
            cuts.append(float(t))
    for d in get(fp, "timing.dissolves", []) or []:
        if isinstance(d, dict) and num(d.get("t0")) and num(d.get("t1")):
            cuts.append((d["t0"] + d["t1"]) / 2)
        elif num(d):
            cuts.append(float(d))
    return sorted(cuts)


def probe_duration(path):
    try:
        out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              str(path)], capture_output=True, text=True, check=True).stdout
        return float(out.strip())
    except Exception:
        return None


def duration_of(fp, video):
    for p in ("source.duration", "source.duration_s", "duration"):
        v = get(fp, p)
        if num(v) and v > 0:
            return float(v)
    vals = get(fp, "motion.energy.values")
    hz = get(fp, "motion.energy.hz", 10) or 10
    if vals:
        return len(vals) / hz
    if video:
        return probe_duration(video)
    return None


# ---------------------------------------------------------------- metric records

class Report:
    def __init__(self, mode):
        self.mode = mode
        self.metrics = []
        self.sections = {}

    def add(self, mid, layer, value, lo, hi, fix, src=None, why="", unit="", detail=None, skipped=None):
        rec = {"id": mid, "layer": layer, "value": value, "source": src, "lo": lo, "hi": hi,
               "why": why, "unit": unit}
        if skipped:
            rec.update(status="skipped", reason=skipped)
        else:
            ok_lo = lo is None or value >= lo - 1e-9
            ok_hi = hi is None or value <= hi + 1e-9
            passed = ok_lo and ok_hi
            dist = 0.0 if passed else ((lo - value) if not ok_lo else (value - hi))
            width = (hi - lo) if (lo is not None and hi is not None and hi > lo) else (
                abs(hi if hi is not None else lo) or 1.0)
            direction = None if passed else ("raise" if not ok_lo else "lower")
            rec.update(status="pass" if passed else "fail", distance=round(dist, 4),
                       norm_distance=round(dist / width, 3) if width else None, direction=direction,
                       fix=None if passed else (fix(direction, dist) if callable(fix) else fix))
        if detail is not None:
            rec["detail"] = detail
        self.metrics.append(rec)
        return rec


# ---------------------------------------------------------------- fix hints for tolerance paths

def tolerance_fix(path, direction, dist, value, src):
    up = direction == "raise"
    amt = f"{dist:.3g}"
    pct = f" ({dist / abs(src) * 100:.0f}% of the source value)" if num(src) and src else ""
    rules = [
        (r"timing\.cuts_per_10s", "cut more often: split the longest shots or bring the next scene in earlier"
         if up else "cut less often: merge neighbouring short shots or hold the landing longer"),
        (r"timing\.shot_length\.(median|p10|p90)", lambda m: (
            f"shots at the {m.group(1)} run {amt}s short; hold those scenes longer" if up else
            f"shots at the {m.group(1)} run {amt}s long; trim those scenes or split them on a VO beat")),
        (r"timing\.hold_share|timing\.holds", "add still holds after each landing before the next move"
         if up else "keep something moving through the holds (a slow drift or a stagger)"),
        (r"timing\.hard_cut_share", "swap dissolves for hard cuts" if up else "swap some hard cuts for dissolves"),
        (r"timing\.dissolves", "add dissolves between scenes" if up else "replace dissolves with hard cuts"),
        (r"motion\.energy_stats\.mean", "more motion overall: longer travel or more elements moving at once"
         if up else "calmer overall: shorter travel, fewer simultaneous moves"),
        (r"motion\.energy_stats\.p90", "peaks hit too softly: give the hero moves more travel or a faster ease-out"
         if up else "peaks hit too hard: shorten travel on the hero moves"),
        (r"motion\.move_stats\.per_10s", "too few moves: add staggered entrances" if up else
         "too many moves: drop decorative ones, keep the signature moves"),
        (r"motion\.move_stats\.overshoot_share", "more moves should overshoot: use the style's overshoot curve"
         if up else "fewer moves should overshoot: use the plain ease-out token"),
        (r"look\.margins\.(\w+)", lambda m: (
            f"pull content in from the {m.group(1)} edge by {amt} of the frame" if up else
            f"push content toward the {m.group(1)} edge by {amt} of the frame")),
        (r"look\.density", "frames are too empty: add the supporting elements the grammar allows" if up else
         "frames are too full: strip elements back to the style's density"),
        (r"look\.sharpness", "render is softer than the source: use vector or 2x assets, drop blur" if up else
         "render is crisper than the source: add the style's grain or blur token"),
        (r"look\.aspect", "change the composition's aspect to the source's"),
        (r"delivery\.wpm", "voice is slow: tts.py --retime with the style's profile (trims pauses first)" if up
         else "voice is fast: tts.py --retime with the style's profile (adds pauses at punctuation)"),
        (r"delivery\.pauses\.(median|p90)", lambda m: (
            f"pauses at the {m.group(1)} are {amt}s short: tts.py --retime, or add ellipses and [short pause] tags"
            if up else f"pauses at the {m.group(1)} are {amt}s long: tts.py --retime, or cut ellipses from the script")),
        (r"delivery\.pauses\.per_min", "pause more often: break long lines at commas or retime with --pauses-per-min"
         if up else "pause less often: join short lines or retime with --pauses-per-min"),
        (r"delivery\.vo_lufs", f"raise the VO gain by {amt} dB" if up else f"lower the VO gain by {amt} dB"),
        (r"delivery\.music_lufs", f"raise the music bed by {amt} dB" if up else f"lower the music bed by {amt} dB"),
        (r"delivery\.emphasis", "add CAPITALISED emphasis words in the script" if up else "remove CAPITALISED emphasis"),
        (r"sound\.", "see the sound section for the class-level fix"),
    ]
    for pat, hint in rules:
        m = re.match(pat, path)
        if m:
            text = hint(m) if callable(hint) else hint
            return f"{direction} by {amt}{pct}; {text}"
    return f"{direction} by {amt}{pct}"


def resolve_band(tol, src_val):
    """Tolerance lo/hi are absolute bounds on the render's value. When the source's own
    value sits outside them and the band straddles zero, they are deltas around it."""
    lo, hi = tol.get("lo"), tol.get("hi")
    kind = tol.get("kind") or tol.get("mode")
    if kind == "relative" and num(src_val):
        return (src_val * (1 + lo) if num(lo) else None, src_val * (1 + hi) if num(hi) else None, "relative")
    if kind == "delta" and num(src_val):
        return (src_val + lo if num(lo) else None, src_val + hi if num(hi) else None, "delta")
    if num(src_val) and num(lo) and num(hi) and not (lo <= src_val <= hi) and lo <= 0 <= hi:
        return src_val + lo, src_val + hi, "delta"
    return (lo if num(lo) else None, hi if num(hi) else None, "absolute")


def emd_hist(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.sum() <= 0 or b.sum() <= 0 or len(a) != len(b):
        return None
    a, b = a / a.sum(), b / b.sum()
    return float(np.abs(np.cumsum(a) - np.cumsum(b)).sum() / len(a))


def hist_mean(h):
    h = np.asarray(h, float)
    return float((h * (np.arange(len(h)) + 0.5)).sum() / h.sum() / len(h)) if h.sum() > 0 else None


def score_tolerances(R, S, T, tol, mode):
    covered = set()
    paths = dict(DEFAULT_BANDS)
    for p in tol:
        paths[p] = None
    for path in sorted(paths):
        if path.startswith("compare."):
            continue
        src_val, val = get(S, path), get(T, path)
        layer = path.split(".")[0]
        leaf = path.split(".")[-1]
        if tol.get(path) is None:
            spec = DEFAULT_BANDS[path]
            if spec.get("replica_only") and mode == "novel":
                continue
            if not (num(src_val) and num(val)):
                continue
            w = spec["rel"] * abs(src_val) if "rel" in spec else spec["abs"]
            lo, hi, why, interp = src_val - w, src_val + w, spec["why"] + " (built-in band)", "built-in"
        else:
            t = tol[path]
            why = t.get("why", "")
            if mode == "novel" and (leaf in LENGTH_DEPENDENT or path.startswith("source.")):
                R.add(path, layer, None, None, None, None, src=None, why=why,
                      skipped="length-dependent; novel mode compares distributions only")
                covered.add(path)
                continue
            if isinstance(src_val, list) or isinstance(val, list):
                if leaf == "luma_hist" or "hist" in leaf:
                    d = emd_hist(src_val or [], val or [])
                    if d is None:
                        R.add(path, layer, None, None, None, None, skipped="histogram missing on one side")
                    else:
                        lo, hi, interp = resolve_band(t, 0.0)
                        R.add(path, layer, round(d, 4), lo if lo is not None and lo > 0 else None, hi,
                              lambda dr, ds: luma_fix(src_val, val), src=0.0, why=why + " (EMD)")
                    covered.add(path)
                    continue
                R.add(path, layer, None, None, None, None, why=why,
                      skipped="list-valued; scored by the derived checks below")
                covered.add(path)
                continue
            if not (num(src_val) or num(val)):
                R.add(path, layer, None, None, None, None, why=why, skipped="missing on both sides")
                continue
            if not num(val):
                R.add(path, layer, None, None, None, None, why=why, skipped="missing in the render fingerprint")
                continue
            lo, hi, interp = resolve_band(t, src_val)
        rec = R.add(path, layer, float(val), lo, hi,
                    lambda d, dist, p=path, v=val, s=src_val: tolerance_fix(p, d, dist, v, s),
                    src=src_val, why=why)
        rec["band_kind"] = interp
        covered.add(path)
    return covered


def luma_fix(src_h, ren_h):
    ms, mr = hist_mean(src_h), hist_mean(ren_h)
    if ms is None or mr is None:
        return "match the source's brightness distribution"
    word = "darker" if mr < ms else "brighter"
    return (f"render is {word} overall (mean luma {mr:.2f} vs {ms:.2f}); "
            f"{'lift' if mr < ms else 'drop'} the background and surface tokens toward the source palette")


# ---------------------------------------------------------------- energy shape (DTW)

def resample(v, n):
    v = np.asarray(v, float)
    if len(v) < 2:
        return np.zeros(n)
    return np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(v)), v)


def robust_norm(v):
    lo, hi = np.percentile(v, 2), np.percentile(v, 98)
    if hi - lo < 1e-9:
        return np.zeros_like(v)
    return np.clip((v - lo) / (hi - lo), 0, 1.5)


def dtw(a, b, band):
    n, m = len(a), len(b)
    w = max(int(band * max(n, m)), abs(n - m) + 1)
    D = np.full((n + 1, m + 1), np.inf)
    D[0, 0] = 0
    for i in range(1, n + 1):
        j0, j1 = max(1, i - w), min(m, i + w)
        for j in range(j0, j1 + 1):
            c = abs(a[i - 1] - b[j - 1])
            D[i, j] = c + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])
    i, j, path = n, m, []
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        k = int(np.argmin([D[i - 1, j - 1], D[i - 1, j], D[i, j - 1]]))
        if k == 0:
            i, j = i - 1, j - 1
        elif k == 1:
            i -= 1
        else:
            j -= 1
    return path[::-1]


def energy_block(R, S, T, ds, dr, mode, th):
    sv, rv = get(S, "motion.energy.values"), get(T, "motion.energy.values")
    if not sv or not rv:
        R.add("energy_shape", "motion", None, None, None, None, skipped="energy curve missing on one side")
        return None
    N = 200
    a, b = robust_norm(resample(sv, N)), robust_norm(resample(rv, N))
    band = 0.05 if mode == "replica" else 0.15
    path = dtw(a, b, band)
    diffs = np.array([b[j] - a[i] for i, j in path])
    sim = float(max(0.0, 1 - np.abs(diffs).mean()))
    corr = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else 0.0
    # where the curves diverge most along the warp
    k = max(3, len(path) // 25)
    sm = np.convolve(np.abs(diffs), np.ones(k) / k, mode="same")
    picks = []
    for idx in np.argsort(-sm):
        if all(abs(idx - p) > len(path) * 0.1 for p in picks):
            picks.append(int(idx))
        if len(picks) == 3:
            break
    top = float(sm[picks[0]]) if picks else 0.0
    picks = [p for p in picks if sm[p] >= max(0.08, 0.3 * top)]
    div = []
    for idx in sorted(picks):
        i, j = path[idx]
        us, ur = i / (N - 1), j / (N - 1)
        lo_i, hi_i = max(0, idx - k), min(len(diffs), idx + k)
        sign = float(diffs[lo_i:hi_i].mean())
        div.append({"u_source": round(us, 3), "u_render": round(ur, 3),
                    "t_source": round(us * ds, 2), "t_render": round(ur * dr, 2),
                    "gap": round(float(sm[idx]), 3),
                    "render_is": "busier" if sign > 0 else "calmer",
                    "warp": round(ur - us, 3)})
    lo, hi = th["energy_shape"]

    def fix(d, dist):
        if not div:
            return f"energy shape {sim:.2f} below {lo}: the curves differ evenly; compare the arc below"
        w = max(div, key=lambda x: x["gap"])
        lead = (f"worst at source {w['t_source']}s against render {w['t_render']}s, where the render is "
                f"{w['render_is']}")
        tail = ("; add movement there (a staggered entrance or a push on the hero element)"
                if w["render_is"] == "calmer" else "; calm it there (fewer simultaneous moves, a hold)")
        warp = ""
        if abs(w["warp"]) > 0.05:
            warp = (f"; the render reaches this beat {abs(w['warp']) * 100:.0f}% of the piece "
                    f"{'late' if w['warp'] > 0 else 'early'}, so move the scene "
                    f"{'earlier' if w['warp'] > 0 else 'later'}")
        return f"energy shape {sim:.2f} below {lo}: {lead}{tail}{warp}"
    R.add("energy_shape", "motion", round(sim, 3), lo, hi, fix, why="energy curve shape after time-normalisation",
          detail={"pearson_unwarped": round(corr, 3), "dtw_band": band, "divergences": div})
    # energy arc: ten sections, no warp, catches a peak in the wrong part of the piece
    sa = [float(a[int(s * N / 10):int((s + 1) * N / 10)].mean()) for s in range(10)]
    sb = [float(b[int(s * N / 10):int((s + 1) * N / 10)].mean()) for s in range(10)]
    dev = [y - x for x, y in zip(sa, sb)]
    worst = int(np.argmax(np.abs(dev)))
    arc = float(np.abs(dev).mean())
    lo2, hi2 = th["energy_arc"]
    R.add("energy_arc", "motion", round(arc, 3), lo2, hi2,
          lambda d, dist: (f"the {worst * 10}-{worst * 10 + 10}% section is "
                           f"{'busier' if dev[worst] > 0 else 'calmer'} than the source's "
                           f"(source {worst * ds / 10:.1f}-{(worst + 1) * ds / 10:.1f}s, render "
                           f"{worst * dr / 10:.1f}-{(worst + 1) * dr / 10:.1f}s); move the "
                           f"{'peak' if dev[worst] < 0 else 'calm'} scene there or retime the structure"),
          why="mean energy per tenth of the piece, unwarped",
          detail={"source": [round(x, 3) for x in sa], "render": [round(x, 3) for x in sb]})
    return {"path": path, "N": N, "divergences": div}


def map_u(u, energy, mode):
    """Source normalised time to render normalised time."""
    if mode == "replica" or not energy:
        return u
    N, path = energy["N"], energy["path"]
    i = u * (N - 1)
    js = [j for (ii, j) in path if abs(ii - i) <= 0.5]
    if not js:
        near = min(path, key=lambda p: abs(p[0] - i))
        js = [near[1]]
    return float(np.mean(js)) / (N - 1)


# ---------------------------------------------------------------- palette (CIEDE2000)

def hex_to_lab(h):
    h = h.lstrip("#")
    rgb = np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    x, y, z = M @ lin / np.array([0.95047, 1.0, 1.08883])
    f = lambda t: t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def de2000(l1, l2):
    L1, a1, b1 = l1
    L2, a2, b2 = l2
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    else:
        dhp = h2p - h1p
        if dhp > 180:
            dhp -= 360
        elif dhp < -180:
            dhp += 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))
    Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    if C1p * C2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) > 180:
        hbp = (h1p + h2p + 360) / 2 if (h1p + h2p) < 360 else (h1p + h2p - 360) / 2
    else:
        hbp = (h1p + h2p) / 2
    T = (1 - 0.17 * math.cos(math.radians(hbp - 30)) + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6)) - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    dth = 30 * math.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / math.sqrt(20 + (Lbp - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    Rt = -math.sin(math.radians(2 * dth)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def color_move(src_lab, ren_lab):
    dL = src_lab[0] - ren_lab[0]
    cs, cr = math.hypot(*src_lab[1:]), math.hypot(*ren_lab[1:])
    bits = []
    if abs(dL) >= 3:
        bits.append(f"{'lighten' if dL > 0 else 'darken'} by {abs(dL):.0f} L*")
    if abs(cs - cr) >= 4:
        bits.append(f"{'more' if cs > cr else 'less'} saturated by {abs(cs - cr):.0f} C*")
    if cs > 8 and cr > 8:
        hs = math.degrees(math.atan2(src_lab[2], src_lab[1])) % 360
        hr = math.degrees(math.atan2(ren_lab[2], ren_lab[1])) % 360
        dh = (hs - hr + 180) % 360 - 180
        if abs(dh) >= 8:
            bits.append(f"rotate hue {dh:+.0f} degrees")
    return ", ".join(bits) or "nudge toward the source swatch"


def palette_block(R, S, T, th):
    sp, rp = get(S, "look.palette") or [], get(T, "look.palette") or []
    sp = [s for s in sp if isinstance(s, dict) and s.get("hex")]
    rp = [s for s in rp if isinstance(s, dict) and s.get("hex")]
    if not sp or not rp:
        R.add("palette_de", "look", None, None, None, None, skipped="palette missing on one side")
        return
    sl = [hex_to_lab(s["hex"]) for s in sp]
    rl = [hex_to_lab(s["hex"]) for s in rp]
    ws = np.array([float(s.get("share", 1)) for s in sp])
    ws = ws / ws.sum()
    wr = np.array([float(s.get("share", 1)) for s in rp])
    wr = wr / wr.sum()
    rows = []
    for k, (s, lab) in enumerate(zip(sp, sl)):
        des = [de2000(lab, r) for r in rl]
        j = int(np.argmin(des))
        rows.append({"source": s["hex"], "share": round(float(ws[k]), 3), "render": rp[j]["hex"],
                     "render_share": round(float(wr[j]), 3), "de2000": round(des[j], 2),
                     "move": color_move(lab, rl[j])})
    score = float(sum(r["de2000"] * r["share"] for r in rows))
    worst = sorted(rows, key=lambda r: -r["de2000"] * r["share"])[:3]

    def fix(d, dist):
        bits = []
        for w in worst:
            if w["de2000"] > 20:
                bits.append(f"render has nothing near {w['source']} ({w['share'] * 100:.0f}% of the source); "
                            f"add it from tokens.json")
            else:
                bits.append(f"{w['render']} stands in for {w['source']} at dE {w['de2000']}: {w['move']}")
        return "; ".join(bits)
    lo, hi = th["palette_de"]
    R.add("palette_de", "look", round(score, 2), lo, hi, fix, why="share-weighted CIEDE2000, source swatch to nearest render swatch",
          detail={"swatches": rows, "lab_from": "hex (sRGB D65)"})
    # share: each render swatch's area goes to its nearest source swatch
    agg = np.zeros(len(sp))
    for j, lab in enumerate(rl):
        agg[int(np.argmin([de2000(lab, s) for s in sl]))] += wr[j]
    tv = float(0.5 * np.abs(agg - ws).sum())
    k = int(np.argmax(np.abs(agg - ws)))
    lo, hi = th["palette_share"]
    R.add("palette_share", "look", round(tv, 3), lo, hi,
          lambda d, dist: (f"{sp[k]['hex']} holds {ws[k] * 100:.0f}% of the source frame and "
                           f"{agg[k] * 100:.0f}% of the render's; "
                           f"{'give it more of the frame (backgrounds, panels)' if agg[k] < ws[k] else 'pull it back'}"),
          why="how the frame area splits across the palette (total variation)")


# ---------------------------------------------------------------- curves

def parse_bez(b):
    if isinstance(b, dict):
        b = [b.get(k) for k in ("x1", "y1", "x2", "y2")]
    if isinstance(b, (list, tuple)) and len(b) == 4 and all(num(v) for v in b):
        return [float(v) for v in b]
    return None


def bez_progress(b, tau):
    x1, y1, x2, y2 = b
    lo, hi = 0.0, 1.0
    for _ in range(40):
        s = (lo + hi) / 2
        x = 3 * (1 - s) ** 2 * s * x1 + 3 * (1 - s) * s ** 2 * x2 + s ** 3
        lo, hi = (s, hi) if x < tau else (lo, s)
    s = (lo + hi) / 2
    return 3 * (1 - s) ** 2 * s * y1 + 3 * (1 - s) * s ** 2 * y2 + s ** 3


def move_label(m):
    reg = m.get("region")
    where = ""
    if isinstance(reg, dict) and num(reg.get("x")):
        where = f" at ({reg['x']:.2f},{reg['y']:.2f})"
    elif isinstance(reg, str):
        where = f" on {reg}"
    return f"{m.get('property', '?')}{where}"


def curves_block(R, S, T, ds, dr, mode):
    sm = [m for m in (get(S, "motion.moves") or []) if conf_value(m.get("confidence")) >= 0.8
          and parse_bez(m.get("bezier"))]
    rm = [m for m in (get(T, "motion.moves") or []) if conf_value(m.get("confidence")) >= 0.5
          and parse_bez(m.get("bezier"))]
    if not sm:
        R.add("curve_match_share", "motion", None, None, None, None, skipped="no high-confidence source moves")
        return []
    c = CURVE[mode]
    scale = (dr / ds) if (ds and dr) else 1.0
    rows = []
    for m in sm:
        bs = parse_bez(m["bezier"])
        cands = [r for r in rm if r.get("property") == m.get("property")]
        if mode == "replica":
            cands = [r for r in cands if abs(r.get("t0", 0) - m.get("t0", 0) * scale) <= 0.25]
        if not cands:
            rows.append({"t0": m.get("t0"), "label": move_label(m), "match": None, "pass": False,
                         "fix": (f"no render {m.get('property')} move "
                                 f"{'within 0.25s of ' + f2(m.get('t0') * scale) + 's' if mode == 'replica' else 'anywhere'}; "
                                 f"place the library element for this move")})
            continue

        def cost(r):
            br = parse_bez(r["bezier"])
            d = math.dist(bs, br)
            dur = abs(math.log(max(r.get("duration", 1e-3), 1e-3) / max(m.get("duration", 1e-3), 1e-3)))
            ov = abs(r.get("overshoot", 0) - m.get("overshoot", 0))
            t = abs(r.get("t0", 0) - m.get("t0", 0) * scale) if mode == "replica" else 0
            return d + dur + ov + t
        r = min(cands, key=cost)
        br = parse_bez(r["bezier"])
        bd = math.dist(bs, br)
        ratio = r.get("duration", 0) / m["duration"] if m.get("duration") else None
        ovd = r.get("overshoot", 0) - m.get("overshoot", 0)
        ok = bd <= c["bezier"] and (ratio is None or c["dur_lo"] <= ratio <= c["dur_hi"]) and abs(ovd) <= c["overshoot"]
        fixes = []
        if bd > c["bezier"]:
            q_s, q_r = bez_progress(bs, 0.25), bez_progress(br, 0.25)
            feel = ("starts slower than the source" if q_r < q_s else "starts faster than the source")
            fixes.append(f"curve {feel} ({q_r * 100:.0f}% vs {q_s * 100:.0f}% done at a quarter of its time); "
                         f"set the ease to cubic-bezier({', '.join(f'{v:.2f}' for v in bs)})")
        if ratio is not None and not (c["dur_lo"] <= ratio <= c["dur_hi"]):
            fixes.append(f"{'shorten' if ratio > 1 else 'lengthen'} it from {r['duration']:.2f}s to {m['duration']:.2f}s")
        if abs(ovd) > c["overshoot"]:
            fixes.append(f"{'cut' if ovd > 0 else 'add'} overshoot ({r.get('overshoot', 0) * 100:.0f}% vs "
                         f"{m.get('overshoot', 0) * 100:.0f}% of travel)")
        rows.append({"t0": m.get("t0"), "label": move_label(m), "match_t0": r.get("t0"),
                     "bezier_dist": round(bd, 3), "duration_ratio": round(ratio, 3) if ratio else None,
                     "overshoot_delta": round(ovd, 3), "pass": ok,
                     "fix": "; ".join(fixes) if fixes else None})
    share = sum(r["pass"] for r in rows) / len(rows)
    lo, hi = DERIVED[mode]["curve_match_share"]
    fails = [r for r in rows if not r["pass"]]

    def fix(d, dist):
        return "; ".join(f"source {r['label']} at {f2(r['t0'])}s"
                         + (f" (render {f2(r['match_t0'])}s)" if r.get("match_t0") is not None else "")
                         + f": {r['fix']}" for r in fails[:4])
    R.add("curve_match_share", "motion", round(share, 3), lo, hi, fix,
          why=f"share of {len(rows)} high-confidence source moves matched by a render move within curve bands",
          detail={"moves": rows, "bands": c})
    return rows


# ---------------------------------------------------------------- shots, beats, cuts

def shots_block(R, S, T, th):
    a = [x for x in (get(S, "timing.shot_lengths") or []) if num(x)]
    b = [x for x in (get(T, "timing.shot_lengths") or []) if num(x)]
    if len(a) < 3 or len(b) < 3:
        R.add("shot_ks", "timing", None, None, None, None, skipped="fewer than three shots on one side")
        return
    from scipy.stats import ks_2samp
    res = ks_2samp(a, b)
    qs = [(q, float(np.percentile(a, q)), float(np.percentile(b, q))) for q in (25, 50, 75, 90)]
    worst = max(qs, key=lambda x: abs(x[2] - x[1]) / max(x[1], 1e-3))
    lo, hi = th["shot_ks"]
    R.add("shot_ks", "timing", round(float(res.statistic), 3), lo, hi,
          lambda d, dist: (f"shots at the p{worst[0]} run {worst[2]:.2f}s against the source's {worst[1]:.2f}s; "
                           f"{'trim or split the long scenes' if worst[2] > worst[1] else 'hold those scenes longer'}"),
          why="two-sample KS statistic on shot lengths",
          detail={"p_value": round(float(res.pvalue), 4), "n_source": len(a), "n_render": len(b),
                  "quantiles": [{"q": q, "source": round(s, 3), "render": round(r, 3)} for q, s, r in qs]})


def beats_of(fp, dur):
    out = []
    for t in cut_times(fp):
        out.append({"kind": "cut", "t": t, "u": t / dur})
    for t in get(fp, "motion.energy_stats.peak_times") or []:
        if num(t):
            out.append({"kind": "peak", "t": float(t), "u": float(t) / dur})
    return out


def beats_block(R, S, T, ds, dr, energy, mode, th):
    sb, rb = beats_of(S, ds), beats_of(T, dr)
    if not sb:
        R.add("beat_alignment", "timing", None, None, None, None, skipped="source has no cuts or peaks")
        return []
    tol_u = (0.1 / ds) if mode == "replica" else 0.05
    rows = []
    for b in sb:
        mu = map_u(b["u"], energy, mode)
        same = [r for r in rb if r["kind"] == b["kind"]]
        near = min(same, key=lambda r: abs(r["u"] - mu)) if same else None
        du = (near["u"] - mu) if near else None
        rows.append({**b, "mapped_u": round(mu, 3), "render_t": round(near["t"], 3) if near else None,
                     "du": round(du, 4) if du is not None else None,
                     "matched": du is not None and abs(du) <= tol_u})
    share = sum(r["matched"] for r in rows) / len(rows)
    lo, hi = th["beat_alignment"]
    miss = [r for r in rows if not r["matched"]]

    def fix(d, dist):
        bits = []
        for r in miss[:4]:
            if r["render_t"] is None:
                bits.append(f"source {r['kind']} at {r['t']:.2f}s has no render {r['kind']} at all")
            else:
                late = r["du"] > 0
                bits.append(f"source {r['kind']} at {r['t']:.2f}s (u {r['u']:.2f}) lands at render "
                            f"{r['render_t']:.2f}s, {abs(r['du']) * dr:.2f}s {'late' if late else 'early'}; "
                            f"move it {'earlier' if late else 'later'}")
        return "; ".join(bits)
    R.add("beat_alignment", "timing", round(share, 3), lo, hi, fix,
          why=f"share of source cuts and energy peaks with a render counterpart within "
              f"{'0.1s' if mode == 'replica' else '5% of the piece'} after mapping",
          detail={"beats": rows})
    return rows


def replica_cuts_block(R, S, T, ds, dr, th):
    a, b = cut_times(S), cut_times(T)
    if not a:
        return
    if not b:
        R.add("cut_offset_median", "timing", 99.0, None, th["cut_offset_median"][1],
              "the render has no cuts; rebuild the scene boundaries from the source", why="replica cut timing")
        return
    offs = [min(b, key=lambda x: abs(x - t)) - t for t in a]
    med = float(np.median(offs))
    absmed = float(np.median(np.abs(offs)))
    lo, hi = th["cut_offset_median"]
    R.add("cut_offset_median", "timing", round(absmed, 3), lo, hi,
          lambda d, dist: (f"cuts land {abs(med):.2f}s {'late' if med > 0 else 'early'} against the source; "
                           f"shift scene starts {'earlier' if med > 0 else 'later'} by {abs(med):.2f}s"
                           if abs(med) >= 0.02 and abs(med) >= 0.5 * absmed else
                           f"cuts scatter {absmed:.2f}s either side of the source's; rebuild the scene "
                           f"boundaries from the source cut list (offsets per cut are in report.json)"),
          why="median absolute offset of each source cut to its nearest render cut",
          detail={"signed_median": round(med, 3), "offsets": [round(o, 3) for o in offs],
                  "source_cuts": len(a), "render_cuts": len(b)})
    worst = int(np.argmax(np.abs(offs)))
    lo, hi = th["cut_offset_max"]
    R.add("cut_offset_max", "timing", round(abs(offs[worst]), 3), lo, hi,
          lambda d, dist: (f"the cut at source {a[worst]:.2f}s lands {abs(offs[worst]):.2f}s "
                           f"{'late' if offs[worst] > 0 else 'early'}; move that scene boundary"),
          why="worst single cut offset")
    R.add("cut_count", "timing", float(len(b)), float(len(a)), float(len(a)),
          lambda d, dist: f"render has {len(b)} cuts against the source's {len(a)}; "
                          f"{'add' if len(b) < len(a) else 'remove'} {abs(len(a) - len(b))} scene boundaries",
          src=len(a), why="replica cut count")


def word_list(fp, path_override):
    if path_override:
        data = json.loads(Path(path_override).read_text())
        return data.get("words", data) if isinstance(data, dict) else data
    w = get(fp, "delivery.words")
    return w if isinstance(w, list) else None


def vo_offsets(cuts, words):
    starts = [w.get("start", w.get("t0", w.get("t"))) for w in words if isinstance(w, dict)]
    starts = [s for s in starts if num(s)]
    offs = []
    for c in cuts:
        if not starts:
            break
        s = min(starts, key=lambda x: abs(x - c))
        if abs(s - c) <= 0.6:
            offs.append(c - s)
    return offs


def vo_block(R, S, T, a):
    rw = word_list(T, a.render_words)
    if not rw:
        R.add("vo_cut_offset", "timing", None, None, None, None,
              skipped="no render word timings (pass --render-words words.json)")
        return
    ro = vo_offsets(cut_times(T), rw)
    if not ro:
        R.add("vo_cut_offset", "timing", None, None, None, None, skipped="no cut lands within 0.6s of a word")
        return
    sw = word_list(S, a.source_words)
    so = vo_offsets(cut_times(S), sw) if sw else []
    rmed = float(np.median(ro))
    if so:
        smed = float(np.median(so))
        lo, hi, why = smed - 0.06, smed + 0.06, "median cut-to-word offset against the source's"
    else:
        smed = None
        lo, hi = DERIVED[a.mode]["vo_cut_offset"]
        why = "median cut-to-word offset (built-in band: on the word or up to 0.1s ahead of it)"
    R.add("vo_cut_offset", "timing", round(rmed, 3), lo, hi,
          lambda d, dist: (f"cuts land {abs(rmed - (smed or 0)):.2f}s {'late' if d == 'lower' else 'early'} "
                           f"vs VO; shift scene starts {'earlier' if d == 'lower' else 'later'} "
                           f"(recompute the scene plan's word offsets from words.json)"),
          src=smed, why=why, detail={"render_offsets": [round(o, 3) for o in ro]})


# ---------------------------------------------------------------- sound

def sound_block(R, S, T, ds, dr, mode, covered):
    ss, ts = S.get("sound"), T.get("sound")
    if not ss or not ts:
        side = "source" if not ss else "render"
        R.add("sound", "sound", None, None, None, None, skipped=f"sound is null on the {side}")
        return

    def add(mid, val, lo, hi, fix, src=None, why="", detail=None):
        if mid in covered or val is None:
            return
        R.add(mid, "sound", round(float(val), 4), lo, hi, fix, src=src, why=why, detail=detail)

    sd, td = get(ss, "density_per_10s"), get(ts, "density_per_10s")
    if num(sd) and num(td):
        w = max(SOUND["density_rel"] * sd, 0.5)
        add("sound.density_per_10s", td, sd - w, sd + w,
            lambda d, dist: (f"{'add' if d == 'raise' else 'drop'} about {dist:.1f} effects per 10s; "
                             f"{'bind effects to more of the moves the binding rules name' if d == 'raise' else 'leave decorative moves silent, keep the bound ones'}"),
            src=sd, why="sound effects per 10s")

    for key, lab in (("median_offset_s", "median"),):
        sv, tv = get(ss, f"sync.{key}"), get(ts, f"sync.{key}")
        if num(sv) and num(tv):
            w = SOUND["sync_ms"] / 1000
            add(f"sound.sync.{key}", tv, sv - w, sv + w,
                lambda d, dist, sv=sv, tv=tv: (f"effects land {abs(tv - sv) * 1000:.0f} ms "
                                               f"{'late' if tv > sv else 'early'} against their moves; shift every "
                                               f"effect {abs(tv - sv) * 1000:.0f} ms {'earlier' if tv > sv else 'later'} "
                                               f"in sound-plan (or fix the binding rule's offset)"),
                src=sv, why="effect onset minus its bound move's keyframe")
    sp = (get(ss, "sync.p90") or 0) - (get(ss, "sync.p10") or 0)
    tp = (get(ts, "sync.p90") or 0) - (get(ts, "sync.p10") or 0)
    if get(ss, "sync.p90") is not None and get(ts, "sync.p90") is not None:
        add("sound.sync.spread", tp, None, sp + SOUND["spread_ms"] / 1000,
            lambda d, dist: (f"sync is loose: p10 to p90 spans {tp * 1000:.0f} ms against {sp * 1000:.0f} ms; "
                             f"snap stray effects to their move keyframes"),
            src=sp, why="p10 to p90 spread of sync offsets")
    for cls, sv in (get(ss, "sync.by_class") or {}).items():
        tv = (get(ts, "sync.by_class") or {}).get(cls)
        sv_ = sv.get("median_offset_s", sv.get("median")) if isinstance(sv, dict) else sv
        tv_ = tv.get("median_offset_s", tv.get("median")) if isinstance(tv, dict) else tv
        if num(sv_) and num(tv_):
            w = SOUND["sync_ms"] / 1000
            add(f"sound.sync.by_class.{cls}", tv_, sv_ - w, sv_ + w,
                lambda d, dist, cls=cls, sv_=sv_, tv_=tv_: (
                    f"{cls} lands {abs(tv_ - sv_) * 1000:.0f} ms {'late' if tv_ > sv_ else 'early'} against its move; "
                    f"pull {cls} clips {abs(tv_ - sv_) * 1000:.0f} ms {'earlier' if tv_ > sv_ else 'later'}, or trim "
                    f"the clip's {'lead-in silence' if tv_ > sv_ else 'pre-roll'}"),
                src=sv_, why=f"{cls} sync")

    def lvl(evts):
        v = [e.get("level_db_rel_vo") for e in evts or [] if num(e.get("level_db_rel_vo"))]
        return float(np.median(v)) if v else None
    sl, tl = lvl(ss.get("events")), lvl(ts.get("events"))
    if sl is not None and tl is not None:
        add("sound.level_db_rel_vo", tl, sl - SOUND["level_db"], sl + SOUND["level_db"],
            lambda d, dist: f"effects sit {abs(tl - sl):.1f} dB {'low' if tl < sl else 'hot'} against the VO; "
                            f"{'raise' if tl < sl else 'lower'} effect gain by {abs(tl - sl):.1f} dB",
            src=sl, why="median effect level relative to the VO")

    sc, tc = get(ss, "classes") or {}, get(ts, "classes") or {}
    if sc and tc:
        names = sorted(set(sc) | set(tc))
        a = np.array([float((sc.get(n) or {}).get("count", 0)) for n in names])
        b = np.array([float((tc.get(n) or {}).get("count", 0)) for n in names])
        if a.sum() > 0 and b.sum() > 0:
            pa, pb = a / a.sum(), b / b.sum()
            tv = float(0.5 * np.abs(pa - pb).sum())
            k = int(np.argmax(np.abs(pa - pb)))
            add("sound.class_mix", tv, None, SOUND["mix_tv"][mode],
                lambda d, dist: (f"{names[k]} is {pb[k] * 100:.0f}% of the render's effects against "
                                 f"{pa[k] * 100:.0f}% in the source; "
                                 f"{'use it on more of the moves its binding rule covers' if pb[k] < pa[k] else 'drop it from moves the binding rules leave silent'}"),
                why="class mix (total variation)",
                detail={n: {"source": round(float(x), 3), "render": round(float(y), 3)} for n, x, y in zip(names, pa, pb)})
        for n in names:
            s, t = sc.get(n), tc.get(n)
            if not s or not t:
                continue
            for key, label in (("median_level_db_rel_vo", "level"),):
                if num(s.get(key)) and num(t.get(key)):
                    add(f"sound.classes.{n}.{key}", t[key], s[key] - SOUND["level_db"], s[key] + SOUND["level_db"],
                        lambda d, dist, n=n, s=s, t=t, key=key: (
                            f"{n} sits {abs(t[key] - s[key]):.1f} dB {'low' if t[key] < s[key] else 'hot'}; "
                            f"{'raise' if t[key] < s[key] else 'lower'} its clip gain"),
                        src=s[key], why=f"{n} level against VO")
            if num(s.get("median_centroid_hz")) and num(t.get("median_centroid_hz")) and s["median_centroid_hz"] > 0:
                o = math.log2(t["median_centroid_hz"] / s["median_centroid_hz"])
                add(f"sound.classes.{n}.centroid_oct", o, -SOUND["centroid_oct"], SOUND["centroid_oct"],
                    lambda d, dist, n=n, o=o: (f"{n} is {abs(o):.2f} octave {'brighter' if o > 0 else 'darker'} than "
                                               f"the source's; {'low-pass' if o > 0 else 'high-shelf'} the clip or "
                                               f"regenerate it from the palette prompt"),
                    src=0.0, why=f"{n} spectral centroid, octaves from the source")
            if num(s.get("median_duration")) and num(t.get("median_duration")) and s["median_duration"] > 0:
                r = t["median_duration"] / s["median_duration"]
                add(f"sound.classes.{n}.duration_ratio", r, 1 / SOUND["dur_ratio"], SOUND["dur_ratio"],
                    lambda d, dist, n=n, r=r, s=s: (f"{n} runs {r:.2f}x the source's length "
                                                    f"({s['median_duration']:.2f}s); "
                                                    f"{'trim the tail' if r > 1 else 'use a longer clip'}"),
                    src=1.0, why=f"{n} duration ratio")
            if num(s.get("bound_property_share")) and num(t.get("bound_property_share")):
                add(f"sound.classes.{n}.bound_property_share", t["bound_property_share"],
                    s["bound_property_share"] - SOUND["bound_share"], s["bound_property_share"] + SOUND["bound_share"],
                    lambda d, dist, n=n: f"{n} is bound to the wrong share of its property's moves; follow the binding rule",
                    src=s["bound_property_share"], why=f"{n} binding share")

    # attack and decay per class from events
    def env(evts, cls, key):
        v = [e.get(key) for e in evts or [] if e.get("class") == cls and num(e.get(key))]
        return float(np.median(v)) if v else None
    classes = {e.get("class") for e in (ss.get("events") or [])} & {e.get("class") for e in (ts.get("events") or [])}
    for n in sorted(c for c in classes if c):
        for key, word in (("attack_ms", "attack"), ("decay_ms", "decay")):
            s, t = env(ss.get("events"), n, key), env(ts.get("events"), n, key)
            if s and t and s > 0:
                r = t / s
                add(f"sound.classes.{n}.{key}_ratio", r, 1 / SOUND["env_ratio"], SOUND["env_ratio"],
                    lambda d, dist, n=n, r=r, s=s, t=t, word=word: (
                        f"{n} {word} is {t:.0f} ms against {s:.0f} ms; "
                        f"{'shorten' if r > 1 else 'soften'} the clip's {word} (fade or pick a clip with a "
                        f"{'sharper' if r > 1 else 'gentler'} {word})"),
                    src=1.0, why=f"{n} {word} ratio")

    sm, tm = get(ss, "music") or {}, get(ts, "music") or {}
    if sm or tm:
        if bool(sm.get("present")) != bool(tm.get("present")):
            R.add("sound.music.present", "sound", float(bool(tm.get("present"))), float(bool(sm.get("present"))),
                  float(bool(sm.get("present"))),
                  "add a music bed matching the source's tempo and duck" if sm.get("present") else
                  "remove the music bed; the source runs on voice and effects alone",
                  src=float(bool(sm.get("present"))), why="music bed present")
        elif sm.get("present"):
            if num(sm.get("lufs")) and num(tm.get("lufs")):
                add("sound.music.lufs", tm["lufs"], sm["lufs"] - SOUND["music_lufs"], sm["lufs"] + SOUND["music_lufs"],
                    lambda d, dist: f"{'raise' if d == 'raise' else 'lower'} the bed by {dist:.1f} dB",
                    src=sm["lufs"], why="music loudness")
            if num(sm.get("tempo_bpm")) and num(tm.get("tempo_bpm")) and sm["tempo_bpm"] > 0:
                t = tm["tempo_bpm"]
                cand = min((t, t * 2, t / 2), key=lambda x: abs(x - sm["tempo_bpm"]))
                w = SOUND["tempo_rel"] * sm["tempo_bpm"]
                add("sound.music.tempo_bpm", cand, sm["tempo_bpm"] - w, sm["tempo_bpm"] + w,
                    lambda d, dist: f"bed runs at {t:.0f} bpm against {sm['tempo_bpm']:.0f}; pick a track nearer the source tempo",
                    src=sm["tempo_bpm"], why="music tempo (half and double time allowed)")
            if num(sm.get("duck_db_under_vo")) and num(tm.get("duck_db_under_vo")):
                s = sm["duck_db_under_vo"]
                add("sound.music.duck_db_under_vo", tm["duck_db_under_vo"], s - SOUND["duck_db"], s + SOUND["duck_db"],
                    lambda d, dist: f"change the duck under the VO by {dist:.1f} dB toward {s:.1f} dB",
                    src=s, why="music duck under the voice")
            if num(sm.get("cuts_on_beat_share")) and num(tm.get("cuts_on_beat_share")):
                s = sm["cuts_on_beat_share"]
                add("sound.music.cuts_on_beat_share", tm["cuts_on_beat_share"], s - SOUND["beat_share"],
                    s + SOUND["beat_share"],
                    lambda d, dist: ("land more cuts on the bed's beats" if d == "raise"
                                     else "let more cuts fall off the beat, as the source does"),
                    src=s, why="share of cuts on a music beat")

    if mode == "replica":
        se, te = ss.get("events") or [], ts.get("events") or []
        rows, scale = [], (dr / ds if ds and dr else 1.0)
        for e in se:
            if not num(e.get("t")):
                continue
            same = [x for x in te if x.get("class") == e.get("class") and num(x.get("t"))]
            m = min(same, key=lambda x: abs(x["t"] - e["t"] * scale)) if same else None
            off = (m["t"] - e["t"] * scale) if m else None
            rows.append({"t": e["t"], "class": e.get("class"), "render_t": m["t"] if m else None,
                         "offset_ms": round(off * 1000) if off is not None else None,
                         "matched": off is not None and abs(off) <= SOUND["event_match_s"]})
        if rows:
            share = sum(r["matched"] for r in rows) / len(rows)
            bad = [r for r in rows if not r["matched"]][:4]
            R.add("sound.events_matched", "sound", round(share, 3), 0.9, None,
                  lambda d, dist: "; ".join(
                      f"source {r['class']} at {r['t']:.2f}s " + (
                          "has no render counterpart" if r["render_t"] is None else
                          f"lands {abs(r['offset_ms'])} ms {'late' if r['offset_ms'] > 0 else 'early'}") for r in bad),
                  why="share of source effects matched by class within 100 ms", detail={"events": rows})


# ---------------------------------------------------------------- sheets

def pick_beats(beat_rows, energy, ds, dr, mode, n_max):
    cands = []
    if energy:
        for d in energy["divergences"][:2]:
            cands.append({"kind": "divergence", "t_s": d["t_source"], "t_r": d["t_render"], "u": d["u_source"],
                          "note": f"render {d['render_is']} here"})
    for r in beat_rows:
        off = 0.25 if r["kind"] == "cut" else 0.0
        t_s = min(r["t"] + off, ds - 0.05)
        if r.get("render_t") is not None and r["matched"]:
            t_r = r["render_t"] + off
        else:
            t_r = map_u(r["u"], energy, mode) * dr + off
        cands.append({"kind": r["kind"], "t_s": t_s, "t_r": min(t_r, dr - 0.05), "u": r["u"],
                      "note": "matched" if r["matched"] else "unmatched in render"})
    chosen = cands[:2] if energy else []
    rest = [c for c in cands if c not in chosen]
    while rest and len(chosen) < n_max:
        best = max(rest, key=lambda c: min([abs(c["u"] - x["u"]) for x in chosen] or [1.0]))
        rest.remove(best)
        if all(abs(best["t_s"] - x["t_s"]) >= 0.3 for x in chosen):
            chosen.append(best)
    k = 1
    while len(chosen) < min(6, n_max):
        u = k / 8
        chosen.append({"kind": "even", "t_s": u * ds, "t_r": map_u(u, energy, mode) * dr, "u": u,
                       "note": "evenly spaced fill"})
        k += 1
    chosen.sort(key=lambda c: c["t_s"])
    for i, c in enumerate(chosen):
        c["id"] = f"B{i + 1}"
        c["t_s"], c["t_r"] = round(max(0.0, c["t_s"]), 3), round(max(0.0, c["t_r"]), 3)
    return chosen


def grab(video, t, path):
    subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=w=720:h=720:force_original_aspect_ratio=decrease", str(path)], check=True)
    return path


def font(size):
    from PIL import ImageFont
    for p in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/SFNS.ttf",
              "/Library/Fonts/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def sheets(beats, src_video, ren_video, out):
    from PIL import Image, ImageDraw
    fdir, sdir = out / "frames", out / "sheets"
    fdir.mkdir(parents=True, exist_ok=True)
    sdir.mkdir(parents=True, exist_ok=True)
    pairs = []
    for b in beats:
        a = Image.open(grab(src_video, b["t_s"], fdir / f"{b['id']}-source.png")).convert("RGB")
        r = Image.open(grab(ren_video, b["t_r"], fdir / f"{b['id']}-render.png")).convert("RGB")
        h = 640
        a = a.resize((max(1, round(a.width * h / a.height)), h))
        r = r.resize((max(1, round(r.width * h / r.height)), h))
        head, gap, pad = 74, 12, 16
        W = pad + a.width + gap + r.width + pad
        panel = Image.new("RGB", (W, head + h + pad), (17, 17, 19))
        d = ImageDraw.Draw(panel)
        d.text((pad, 12), f"{b['id']}  {b['kind']}  u {b['u']:.2f}  {b['note']}", fill=(235, 235, 235), font=font(22))
        d.text((pad, 44), f"source {b['t_s']:.2f}s", fill=(160, 160, 165), font=font(18))
        d.text((pad + a.width + gap, 44), f"render {b['t_r']:.2f}s", fill=(160, 160, 165), font=font(18))
        panel.paste(a, (pad, head))
        panel.paste(r, (pad + a.width + gap, head))
        pairs.append(panel)
    portrait = pairs and pairs[0].width < 1100
    cols, rows = (2, 2) if portrait else (1, 3)
    per = cols * rows
    paths = []
    for s in range(0, len(pairs), per):
        group = pairs[s:s + per]
        cw = max(p.width for p in group)
        ch = max(p.height for p in group)
        nrows = math.ceil(len(group) / cols)
        sheet = Image.new("RGB", (cw * min(cols, len(group)), ch * nrows), (10, 10, 12))
        for k, p in enumerate(group):
            sheet.paste(p, ((k % cols) * cw, (k // cols) * ch))
        path = sdir / f"sheet-{s // per + 1:02d}.png"
        sheet.save(path)
        paths.append(str(path))
    return paths


# ---------------------------------------------------------------- report

def write_report(R, a, ds, dr, beats, sheet_paths, curve_rows, out):
    scored = [m for m in R.metrics if m["status"] != "skipped"]
    fails = sorted([m for m in scored if m["status"] == "fail"], key=lambda m: -(m.get("norm_distance") or 0))
    ok = not fails
    data = {"verdict": "pass" if ok else "fail", "mode": a.mode, "source": a.source_fp, "render": a.render_fp,
            "durations": {"source": ds, "render": dr}, "counts": {"scored": len(scored), "failed": len(fails),
            "skipped": len(R.metrics) - len(scored)}, "blocking": [m["id"] for m in fails],
            "metrics": R.metrics, "beats": beats, "sheets": sheet_paths}
    (out / "report.json").write_text(json.dumps(data, indent=1, default=float))

    def line(m):
        band = (f"{f2(m['lo'], 3)} to {f2(m['hi'], 3)}" if m["lo"] is not None and m["hi"] is not None else
                (f"at least {f2(m['lo'], 3)}" if m["lo"] is not None else f"at most {f2(m['hi'], 3)}"))
        src = f", source {f2(m['source'], 3)}" if num(m.get("source")) else ""
        return f"{m['id']} {f2(m['value'], 3)} (band {band}{src})"

    get_m = {m["id"]: m for m in R.metrics}
    name = lambda p: Path(p).resolve().parent.name + "/" + Path(p).name
    L = [f"# Compare: {name(a.render_fp)} against {name(a.source_fp)}", ""]
    L.append(f"{'PASS' if ok else 'FAIL'} in {a.mode} mode: {len(scored) - len(fails)} of {len(scored)} metrics pass, "
             f"{len(fails)} block. Source {f2(ds)}s, render {f2(dr)}s.")
    head = []
    for k, label in (("energy_shape", "energy shape"), ("palette_de", "palette dE"), ("curve_match_share", "curves matched"),
                     ("shot_ks", "shot KS"), ("beat_alignment", "beats aligned")):
        if k in get_m and get_m[k]["status"] != "skipped":
            head.append(f"{label} {f2(get_m[k]['value'])}")
    if head:
        L.append(", ".join(head) + ".")
    L.append("")
    if fails:
        L.append("## Blocking, worst first")
        L.append("")
        for i, m in enumerate(fails, 1):
            L.append(f"{i}. {line(m)}. {m['fix']}.")
        L.append("")
    en = get_m.get("energy_shape")
    if en and en.get("detail"):
        L.append("## Energy shape")
        L.append("")
        L.append(f"DTW similarity {f2(en['value'])} with a {en['detail']['dtw_band'] * 100:.0f}% warp window, "
                 f"unwarped Pearson {f2(en['detail']['pearson_unwarped'])}. The curves diverge most at:")
        L.append("")
        for d in en["detail"]["divergences"]:
            L.append(f"- source {d['t_source']}s against render {d['t_render']}s, render {d['render_is']} "
                     f"(gap {d['gap']}, warp {d['warp']:+.2f} of the piece)")
        L.append("")
    if curve_rows:
        L.append("## Curves")
        L.append("")
        for r in curve_rows:
            if r.get("match_t0") is None and not r["pass"]:
                L.append(f"- fail, source {r['label']} at {f2(r['t0'])}s: {r['fix']}")
            else:
                L.append(f"- {'pass' if r['pass'] else 'fail'}, source {r['label']} at {f2(r['t0'])}s against render "
                         f"{f2(r['match_t0'])}s: bezier distance {r['bezier_dist']}, duration ratio {r['duration_ratio']}, "
                         f"overshoot delta {r['overshoot_delta']}" + (f". {r['fix']}" if r.get("fix") else ""))
        L.append("")
    snd = [m for m in R.metrics if m["layer"] == "sound"]
    if snd:
        L.append("## Sound")
        L.append("")
        for m in snd:
            if m["status"] == "skipped":
                L.append(f"- skipped {m['id']}: {m['reason']}")
            else:
                L.append(f"- {m['status']} {line(m)}" + (f". {m['fix']}" if m.get("fix") else ""))
        L.append("")
    if sheet_paths:
        L.append("## Beat-matched sheets")
        L.append("")
        for b in beats:
            L.append(f"- {b['id']} {b['kind']}: source {b['t_s']}s, render {b['t_r']}s ({b['note']})")
        L.append("")
        for p in sheet_paths:
            L.append(f"- {p}")
        L.append("")
    L.append("## Passing")
    L.append("")
    for m in scored:
        if m["status"] == "pass" and m["layer"] != "sound":
            L.append(f"- {line(m)}")
    sk = [m for m in R.metrics if m["status"] == "skipped" and m["layer"] != "sound"]
    if sk:
        L.append("")
        L.append("## Skipped")
        L.append("")
        for m in sk:
            L.append(f"- {m['id']}: {m['reason']}")
    (out / "report.md").write_text("\n".join(L) + "\n")
    return ok


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source_fp")
    ap.add_argument("render_fp")
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["novel", "replica"], default="novel")
    ap.add_argument("--source-video")
    ap.add_argument("--render-video")
    ap.add_argument("--render-words", help="tts.py words.json for the render's VO")
    ap.add_argument("--source-words", help="word timings for the source's VO, if not in its fingerprint")
    ap.add_argument("--beats", type=int, default=8, help="beats on the sheets (6 to 10)")
    a = ap.parse_args()

    S = json.loads(Path(a.source_fp).read_text())
    T = json.loads(Path(a.render_fp).read_text())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ds, dr = duration_of(S, a.source_video), duration_of(T, a.render_video)
    tol = S.get("tolerance") or {}
    th = {k: v for k, v in DERIVED[a.mode].items()}
    for k in th:
        t = tol.get(f"compare.{k}")
        if t:
            th[k] = (t.get("lo"), t.get("hi"))

    R = Report(a.mode)
    covered = score_tolerances(R, S, T, tol, a.mode)
    if "look.luma_hist" not in covered and get(S, "look.luma_hist") and get(T, "look.luma_hist"):
        d = emd_hist(get(S, "look.luma_hist"), get(T, "look.luma_hist"))
        if d is not None:
            lo, hi = th["luma_emd"]
            R.add("look.luma_hist", "look", round(d, 4), lo, hi,
                  lambda dr_, ds_: luma_fix(get(S, "look.luma_hist"), get(T, "look.luma_hist")),
                  src=0.0, why="luminance histogram distance (EMD, built-in band)")
    energy = energy_block(R, S, T, ds, dr, a.mode, th) if ds and dr else None
    palette_block(R, S, T, th)
    curve_rows = curves_block(R, S, T, ds, dr, a.mode)
    shots_block(R, S, T, th)
    beat_rows = beats_block(R, S, T, ds, dr, energy, a.mode, th) if ds and dr else []
    if a.mode == "replica" and ds and dr:
        replica_cuts_block(R, S, T, ds, dr, th)
    vo_block(R, S, T, a)
    sound_block(R, S, T, ds, dr, a.mode, covered)

    beats, sheet_paths = [], []
    if a.source_video and a.render_video and ds and dr:
        beats = pick_beats(beat_rows, energy, ds, dr, a.mode, max(6, min(10, a.beats)))
        sheet_paths = sheets(beats, a.source_video, a.render_video, out)
    ok = write_report(R, a, ds, dr, beats, sheet_paths, curve_rows, out)
    fails = [m for m in R.metrics if m["status"] == "fail"]
    print(f"{'PASS' if ok else 'FAIL'} {a.mode}: {len(fails)} blocking -> {out / 'report.md'}")
    for m in sorted(fails, key=lambda m: -(m.get("norm_distance") or 0))[:5]:
        print(f"  {m['id']}: {m['fix']}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
