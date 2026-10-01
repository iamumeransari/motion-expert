"""Edit timing: hard cuts, soft transitions (dissolve / wipe / motion), shot
lengths, cuts per 10 s, holds and hold share.

Method. Frames are decoded at the source rate at a long side of 160 px and blurred
lightly. Per frame t the change signal is the share of pixels whose grey level moved
more than 20 levels since frame t-1.

A hard cut is an isolated spike: the change at t clears an absolute floor and is
several times the change on both neighbouring frames, and the new picture persists
(frame t+2 still differs from t-1). Isolation is what keeps motion-graphics wipes and
fast moves from firing, since those raise the change signal over several frames.

A soft transition is a burst of consecutive changing frames in which, at its peak, a
large share of the frame is in flux, lasting at most 1.5 s, whose first and last
frames differ over most of the picture (the content was replaced rather than an
element moving over a stable scene). Its kind is a dissolve when the middle frame is
well explained as a blend of the end frames, a wipe when per-pixel switch times line
up along an axis, a flash when a frame inside the burst is at least 20 grey levels
brighter than the brighter end (dip-to-black for the mirror case), and motion otherwise (push, zoom-blur, whip). A burst also
counts as a transition without replacing most of the picture when at least two of
its frames have 60 % of pixels in flux, which catches flash transitions between two
scenes sharing a background.

Shots are bounded by hard cuts and by the midpoint of each soft transition.
cuts_per_10s counts every shot boundary (hard and soft) per 10 s of runtime;
hard_cut_share says how many of those boundaries were hard.

A hold is a stretch of at least 0.3 s in which under 0.4 % of pixels change by more
than 12 levels per frame (single-frame blips such as a caption swap are ignored).
"""
from __future__ import annotations

import argparse
import sys

import cv2
import numpy as np

sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import analysis_size, emit, load_frames, pct, probe  # noqa: E402

P = {
    "long_side": 160,
    "pix_thr": 20,          # grey levels counted as "changed" for cut / transition
    "cut_floor": 0.10,      # min share of pixels changed for a hard cut
    "cut_ratio": 3.0,       # spike must be this many times both neighbours
    "cut_persist": 0.5,     # diff(t-1, t+2) must keep this share of diff(t-1, t)
    "gap_frames": 2,        # quiet frames tolerated inside one burst
    "big_frac": 0.5,        # frames at >= this share of the burst peak count as "big"
    "burst_on": 0.08,       # per-frame change that starts a burst
    "trans_peak": 0.25,     # burst peak needed to be a scene-level transition
    "trans_replace": 0.45,  # share of pixels differing first vs last frame of burst
    "trans_max_s": 1.5,
    "flux_share": 0.6,      # a frame where this share of pixels changes is "in flux"
    "settle_step": 1.5,     # grey levels per frame; a flash ends when the mean moves less
    "flash_dev": 20,        # mid-burst mean grey must pass the brighter (or darker) end by this much
    "hold_thr": 12,
    "hold_share": 0.004,
    "hold_min_s": 0.3,
}


def change_share(a, b, thr):
    return float((np.abs(a.astype(np.int16) - b.astype(np.int16)) > thr).mean())


def classify_transition(G, a, b):
    """G: grey frames. a = last frame before the burst, b = last frame of the burst."""
    S, E = G[a].astype(np.float32), G[b].astype(np.float32)
    diff = E - S
    mask = np.abs(diff) > P["pix_thr"]
    if mask.sum() < 20 or b - a < 2:
        return "motion", None
    m = (a + b) // 2
    M = G[m].astype(np.float32)
    # dissolve: M ~ S + alpha (E - S) with one alpha for every pixel
    d = diff[mask]
    alpha = float(np.clip(((M - S)[mask] * d).sum() / (d * d).sum(), 0, 1))
    resid = np.abs((M - S)[mask] - alpha * d).mean() / (np.abs(d).mean() + 1e-6)
    # wipe: time each pixel crosses halfway, correlated with position
    seg = G[a:b + 1].astype(np.float32)
    prog = (seg - S) / np.where(np.abs(diff) < 1, 1, diff)
    crossed = prog >= 0.5
    tcross = np.argmax(crossed, axis=0).astype(np.float32)
    ys, xs = np.nonzero(mask)
    tc = tcross[ys, xs]
    best_r = 0.0
    if tc.std() > 0.3:
        for coord in (xs.astype(np.float32), ys.astype(np.float32), (xs + ys).astype(np.float32),
                      (xs - ys).astype(np.float32)):
            if coord.std() > 0:
                r = abs(float(np.corrcoef(coord, tc)[0, 1]))
                best_r = max(best_r, r)
    if 0.1 < alpha < 0.9 and resid < 0.3:
        return "dissolve", {"blend_residual": resid, "alpha_mid": alpha}
    if best_r > 0.6:
        return "wipe", {"axis_corr": best_r}
    return "motion", {"blend_residual": resid, "axis_corr": best_r}


def measure(path: str) -> dict:
    pr = probe(path)
    fps, dur = pr["fps"], pr["duration"]
    size = analysis_size(pr["width"], pr["height"], P["long_side"])
    G = load_frames(path, fps, size, gray=True)
    G = np.stack([cv2.GaussianBlur(g, (3, 3), 0) for g in G])
    n = len(G)
    dur = min(dur, n / fps) if dur else n / fps
    d = np.zeros(n)
    dh = np.zeros(n)
    for t in range(1, n):
        diff = np.abs(G[t].astype(np.int16) - G[t - 1].astype(np.int16))
        d[t] = (diff > P["pix_thr"]).mean()
        dh[t] = (diff > P["hold_thr"]).mean()

    # Group changing frames into bursts, tolerating short quiet gaps so transitions
    # rendered at a stepped rate (duplicate frames) stay one event.
    active = d >= P["burst_on"]
    bursts = []
    t = 1
    while t < n:
        if active[t]:
            a = b = t
            while True:
                nxt = [k for k in range(b + 1, min(n, b + 2 + P["gap_frames"])) if active[k]]
                if not nxt:
                    break
                b = nxt[0]
            bursts.append((a, b))
            t = b + 1
        else:
            t += 1

    cuts, trans = [], []
    for a, b in bursts:
        seg = d[a:b + 1]
        peak = float(seg.max())
        big = np.nonzero(seg >= P["big_frac"] * peak)[0]
        if len(big) == 1:
            k = a + int(big[0])
            nb = max(d[k - 1] if k - 1 >= 1 else 0.0, d[k + 1] if k + 1 < n else 0.0)
            if d[k] >= P["cut_floor"] and d[k] >= P["cut_ratio"] * max(nb, 0.01):
                if k + 2 >= n or change_share(G[k - 1], G[min(k + 2, n - 1)], P["pix_thr"]) >= P["cut_persist"] * d[k]:
                    cuts.append(k)
            continue
        if (b - a + 1) / fps > P["trans_max_s"] or peak < P["trans_peak"]:
            continue  # sustained motion inside a scene, not an edit
        rep = change_share(G[a - 1], G[b], P["pix_thr"])
        in_flux = int((seg >= P["flux_share"]).sum())
        if rep < P["trans_replace"] and in_flux < 2:
            continue  # an element moved over a stable scene
        e0, e1 = float(G[a - 1].mean()), float(G[b].mean())
        mids = [float(G[k].mean()) for k in range(a, b + 1)]
        over = max(mids) - max(e0, e1)    # dip to white: brighter than both ends
        under = min(e0, e1) - min(mids)   # dip to black: darker than both ends
        kind = None
        if over > P["flash_dev"]:
            kind = "flash"
        elif under > P["flash_dev"]:
            kind = "dip-to-black"
        if kind:
            # the flash decays slowly after the content has swapped; the transition
            # lasts until mean brightness settles, or motion reads the decay as a move
            lim = min(n - 1, b + int(P["trans_max_s"] * fps))
            while b < lim and abs(float(G[b + 1].mean()) - float(G[b].mean())) > P["settle_step"]:
                b += 1
        else:
            kind, _ = classify_transition(G, a - 1, b)
        trans.append({"t0": (a - 1) / fps, "t1": b / fps, "kind": kind,
                      "duration": (b - a + 1) / fps, "replaced": rep, "peak_change": peak})

    bounds = sorted([c / fps for c in cuts] + [(x["t0"] + x["t1"]) / 2 for x in trans])
    edges = [0.0] + bounds + [dur]
    shots = [b - a for a, b in zip(edges[:-1], edges[1:]) if b - a > 1e-6]

    # holds
    still = dh < P["hold_share"]
    still[0] = still[1] if n > 1 else True
    # ignore single-frame blips inside stillness
    for i in range(1, n - 1):
        if not still[i] and still[i - 1] and still[i + 1]:
            still[i] = True
    holds = []
    i = 0
    min_len = int(np.ceil(P["hold_min_s"] * fps))
    while i < n:
        if still[i]:
            j = i
            while j + 1 < n and still[j + 1]:
                j += 1
            if j - i + 1 >= min_len:
                holds.append({"t0": i / fps, "t1": (j + 1) / fps})
            i = j + 1
        else:
            i += 1
    hold_time = sum(h["t1"] - h["t0"] for h in holds)
    n_bound = len(bounds)
    return {
        "cuts": [c / fps for c in cuts],
        "dissolves": trans,
        "shot_lengths": shots,
        "shot_length": {"median": pct(shots, 50), "p10": pct(shots, 10), "p90": pct(shots, 90),
                        "count": len(shots)},
        "cuts_per_10s": n_bound / dur * 10 if dur else 0.0,
        "hard_cut_share": (len(cuts) / n_bound) if n_bound else None,
        "holds": holds,
        "hold_share": hold_time / dur if dur else 0.0,
        "_change_signal": d,  # private, used by motion.py and frames.py; stripped on output
    }


def public(res: dict) -> dict:
    return {k: v for k, v in res.items() if not k.startswith("_")}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("--out")
    a = ap.parse_args()
    emit(public(measure(a.video)), a.out)


if __name__ == "__main__":
    main()
