"""Edit timing: hard cuts, soft transitions (dissolve / wipe / motion), shot
lengths, cuts per 10 s, holds and hold share.

Method. Frames are decoded at the source rate at a long side of 160 px and blurred
lightly. Per frame t the change signal is the share of pixels whose grey level moved
more than 20 levels since frame t-1.

Changing frames are grouped into bursts (runs of frames whose change clears a low
bar, tolerating two quiet frames so stepped animation stays one event), and hard cuts
are found in two tiers.

Tier 1 is an isolated spike: the only big frame in its burst, clearing an absolute
floor, several times the change on both neighbouring frames, and persisting (frame
t+2 still differs from t-1). Isolation is what keeps motion-graphics wipes and fast
moves from firing, since those raise the change signal over several frames.

Tier 2 finds a cut that sits inside other activity, such as next to a camera move, a
stepped punch-in on twos, a card scaling down, or a second cut a few frames away,
which tier 1 cannot see because the burst holds more than one big frame or the
neighbours are busy. Each candidate pair of frames is first aligned for scale and
shift (a small scale search plus phase correlation), and the step is scored by the
share of pixels that still differ after alignment, so a camera move or a card
resizing scores near zero while new content scores high. A tier-2 cut must replace
at least half the picture after alignment, change the colour distribution (an HSV
histogram distance, which rejects a stepped zoom of the same plate), stand at least
1.3 times above every other aligned step within three frames (a single-frame step,
not one step of a stepped ramp, morph or two-frame dissolve), and persist.

A soft transition is a burst of consecutive changing frames in which, at its peak, a
large share of the frame is in flux, lasting at most 1.5 s, whose first and last
frames differ over most of the picture (the content was replaced rather than an
element moving over a stable scene). Its kind is a dissolve when the middle frame is
well explained as a blend of the end frames, a wipe when per-pixel switch times line
up along an axis, a flash when a frame inside the burst is at least 20 grey levels
brighter than the brighter end (dip-to-black for the mirror case) and the burst
lasts at most 0.6 s before it settles (a pulse, not the bright passage of a morph),
and motion otherwise (push, zoom-blur, whip). A burst is split at
the cuts it contains and each remaining piece is judged on its own, except that a
burst which is as a whole a flash or a dip stays one transition, since the flash is
hiding the content swap and the steps into and out of it are not cuts. A burst also
counts as a transition without replacing most of the picture when at least two of
its frames have 60 % of pixels in flux, which catches flash transitions between two
scenes sharing a background.

A piece that starts and ends on a cut is a whole shot, so nothing in it is a
transition. A transition that runs straight into or out of a cut inside the same burst
(a word rushing through camera before the cut lands, a card that shrinks, swaps its
content on a cut and grows back) is kept with "joins_cut" set to that cut's time.

Shots are bounded by hard cuts and by the midpoint of each soft transition that does
not join a cut, since the cut already marks that boundary.
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
from common import analysis_size, emit, iter_frames, load_frames, pct, probe  # noqa: E402

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
    "flash_max_s": 0.6,     # ...within a burst piece this short (a pulse, not a bright passage)
    # tier-2 cuts inside other activity
    "step_resid": 0.5,      # share of pixels still changed after scale + shift alignment
    "step_hist": 0.35,      # HSV histogram Bhattacharyya distance across the step
    "step_dominance": 1.3,  # must beat every other aligned step within step_window frames by this
    "step_window": 3,
    "step_scan": 0.3,       # raw change a frame needs before tier 2 looks at it
    "align_scales": (0.8, 0.85, 0.9, 0.94, 0.97, 1.0, 1.03, 1.06, 1.11, 1.18, 1.25),
    "hold_thr": 12,
    "hold_share": 0.004,
    "hold_min_s": 0.3,
}


def change_share(a, b, thr):
    return float((np.abs(a.astype(np.int16) - b.astype(np.int16)) > thr).mean())


def aligned_change(G, a, b, thr):
    """Share of pixels differing by more than thr between frames a and b after the
    best scale (from align_scales, about the centre) and shift (phase correlation)
    that maps a onto b, measured over the overlap. Never more than the unaligned
    change, so a static frame pair scores exactly as change_share does."""
    A, B = G[a].astype(np.float32), G[b].astype(np.float32)
    h, w = A.shape
    best = change_share(G[a], G[b], thr)
    ones = np.ones_like(A)
    for s in P["align_scales"]:
        M = cv2.getRotationMatrix2D((w / 2, h / 2), 0, s)
        As = cv2.warpAffine(A, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        valid = cv2.warpAffine(ones, M, (w, h), flags=cv2.INTER_NEAREST) > 0.5
        if not valid.any():
            continue
        (dx, dy), _ = cv2.phaseCorrelate(np.where(valid, As, float(As[valid].mean())), B)
        if abs(dx) > w / 3 or abs(dy) > h / 3:
            dx = dy = 0.0
        T = np.float32([[1, 0, dx], [0, 1, dy]])
        A2 = cv2.warpAffine(As, T, (w, h), flags=cv2.INTER_LINEAR)
        v2 = cv2.warpAffine(valid.astype(np.uint8), T, (w, h), flags=cv2.INTER_NEAREST) > 0
        if v2.mean() < 0.4:
            continue
        best = min(best, float((np.abs(A2 - B)[v2] > thr).mean()))
    return best


def colour_hists(path, fps, size):
    """Normalised 12x4x4 HSV histogram of every frame, streamed so long videos do not
    hold colour frames in memory."""
    out = []
    for _, f in iter_frames(path, fps, size, gray=False):
        hsv = cv2.cvtColor(f, cv2.COLOR_RGB2HSV)
        hh = cv2.calcHist([hsv], [0, 1, 2], None, [12, 4, 4], [0, 180, 0, 256, 0, 256])
        out.append((hh / max(float(hh.sum()), 1.0)).astype(np.float32))
    return out


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

    hists = None  # colour histograms, decoded only when tier 2 has a candidate
    resid = {}

    def r_at(k):
        """Aligned step score of frame k (k-1 to k), cached; quiet frames keep d."""
        if k < 1 or k >= n:
            return 0.0
        if d[k] < P["burst_on"]:
            return float(d[k])
        if k not in resid:
            resid[k] = aligned_change(G, k - 1, k, P["pix_thr"])
        return resid[k]

    def tier2(a, b):
        nonlocal hists
        found = []
        W = P["step_window"]
        for k in range(a, b + 1):
            if d[k] < P["step_scan"] or r_at(k) < P["step_resid"]:
                continue
            ctx = max([r_at(j) for j in range(k - W, k + W + 1) if j != k] + [0.01])
            if r_at(k) < P["step_dominance"] * ctx:
                continue
            if hists is None:
                hists = colour_hists(path, fps, size)
            if k >= len(hists) or cv2.compareHist(hists[k - 1], hists[k], cv2.HISTCMP_BHATTACHARYYA) < P["step_hist"]:
                continue
            if k + 2 < n and aligned_change(G, k - 1, k + 2, P["pix_thr"]) < P["cut_persist"] * r_at(k):
                continue
            found.append(k)
        return found

    def transition(a, b, stop):
        """Judge frames a..b (a-1 is the last frame before) as a soft transition;
        stop is the last frame a flash may settle into (the frame before the next cut)."""
        seg = d[a:b + 1]
        peak = float(seg.max())
        if (b - a + 1) / fps > P["trans_max_s"] or peak < P["trans_peak"]:
            return None  # sustained motion inside a scene, not an edit
        rep = change_share(G[a - 1], G[b], P["pix_thr"])
        in_flux = int((seg >= P["flux_share"]).sum())
        if rep < P["trans_replace"] and in_flux < 2:
            return None  # an element moved over a stable scene
        e0, e1 = float(G[a - 1].mean()), float(G[b].mean())
        mids = [float(G[k].mean()) for k in range(a, b + 1)]
        over = max(mids) - max(e0, e1)    # dip to white: brighter than both ends
        under = min(e0, e1) - min(mids)   # dip to black: darker than both ends
        kind = None
        if (b - a + 1) / fps <= P["flash_max_s"]:
            if over > P["flash_dev"]:
                kind = "flash"
            elif under > P["flash_dev"]:
                kind = "dip-to-black"
        if kind:
            # the flash decays slowly after the content has swapped; the transition
            # lasts until mean brightness settles, or motion reads the decay as a move
            lim = min(stop, b + int(P["trans_max_s"] * fps))
            while b < lim and abs(float(G[b + 1].mean()) - float(G[b].mean())) > P["settle_step"]:
                b += 1
        else:
            kind, _ = classify_transition(G, a - 1, b)
        return {"t0": (a - 1) / fps, "t1": b / fps, "kind": kind,
                "duration": (b - a + 1) / fps, "replaced": rep, "peak_change": peak}

    cuts, trans = [], []
    for a, b in bursts:
        seg = d[a:b + 1]
        peak = float(seg.max())
        big = np.nonzero(seg >= P["big_frac"] * peak)[0]
        if len(big) == 1:
            # tier 1, then tier 2 for a cut beside busy neighbours; one big frame is a
            # cut or nothing, never a transition
            k = a + int(big[0])
            nb = max(d[k - 1] if k - 1 >= 1 else 0.0, d[k + 1] if k + 1 < n else 0.0)
            if (d[k] >= P["cut_floor"] and d[k] >= P["cut_ratio"] * max(nb, 0.01)
                    and (k + 2 >= n or change_share(G[k - 1], G[min(k + 2, n - 1)], P["pix_thr"]) >= P["cut_persist"] * d[k])):
                cuts.append(k)
            else:
                cuts += tier2(a, b)
            continue
        whole = transition(a, b, n - 1)
        if whole and whole["kind"] in ("flash", "dip-to-black"):
            trans.append(whole)  # the flash hides the content swap; steps inside it are not cuts
            continue
        here = tier2(a, b)
        if not here:
            if whole:
                trans.append(whole)
            continue
        cuts += here
        # split the burst at its cuts and judge each piece between them
        edges = [a - 1] + here + [b + 1]
        for lo, hi in zip(edges[:-1], edges[1:]):
            if lo >= a and hi <= b:
                continue  # starts and ends on a cut: a whole shot, so a move, not a transition
            s0, s1 = lo + 1, hi - 1
            while s0 <= s1 and d[s0] < P["burst_on"]:
                s0 += 1
            while s1 >= s0 and d[s1] < P["burst_on"]:
                s1 -= 1
            if s0 > s1:
                continue
            x = transition(s0, s1, (hi - 1) if hi <= b else n - 1)
            if x:
                # a transition running straight into or out of a cut is one edit with
                # it (a card wipe around a cut inside the card); the cut is the boundary
                joined = [c for c in (lo, hi) if a <= c <= b]
                if joined:
                    x["joins_cut"] = joined[0] / fps
                trans.append(x)
    cuts.sort()

    bounds = sorted([c / fps for c in cuts] + [(x["t0"] + x["t1"]) / 2 for x in trans if "joins_cut" not in x])
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
