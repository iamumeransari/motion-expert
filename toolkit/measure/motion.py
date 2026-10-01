"""Motion: optical-flow energy curve and per-move curve fits.

Energy. Farneback flow runs between consecutive frames decoded at the source rate
with a long side of 320 px. Per frame the raw energy is the mean flow magnitude in
frame long-sides per second, so it does not depend on resolution or frame rate.
Hard-cut frames are replaced by their neighbours (flow across a cut is meaningless).
The curve is averaged into 10 Hz bins; `values` is that curve divided by its peak,
`raw` keeps the unnormalised numbers, and energy_stats.mean / p90 are raw.

Moves. A pixel is moving when its flow exceeds 0.6 px per frame at analysis scale.
Masks are max-pooled to a 4 px grid, closed by one frame in time, and labelled as
3-D connected components (x, y, t) with frames inside soft transitions and cuts
blanked, so a transition is never reported as a move. Components shorter than four
frames or covering under 0.3 % of the frame are dropped, and a component whose
activity falls below 15 % of its peak for three frames is split there.

For each move the flow inside its mask is fitted per frame with an affine field
(translation, uniform scale, rotation), integrated over time, and compared with the
intensity change across the move's bounding box. The dominant property is the one
that moved the element's edge furthest, unless the affine fit explains under 55 % of
the flow (rigidity), in which case it is "organic" (faces, hands, footage) and never
high confidence; when no geometric change clears 1.5 % of
the frame but the region's pixels changed, it is opacity, or mask-wipe when the
per-pixel switch times line up along an axis. Progress for that property is
normalised to end at 1, and a CSS cubic-bezier [x1, y1, x2, y2] is fitted by
bounded least squares from five deterministic starts. Overshoot is how far progress
passes 1 before settling. fit_error is the RMS residual in progress units, and
confidence is high only when the fit is tight, the move spans at least eight
samples, the property is unambiguous and the progress curve is not noisy. Each move
also carries keyframes: start (progress leaves 0), peak (fastest frame) and land
(first arrival at the end value, which is the impact frame under overshoot), so
sound effects and VO words can bind to them.
"""
from __future__ import annotations

import argparse
import math
import sys

import cv2
import numpy as np
from scipy import ndimage
from scipy.optimize import least_squares

sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import analysis_size, emit, load_frames, pct, probe  # noqa: E402

cv2.setNumThreads(1)

P = {
    "long_side": 320,
    "flow_thr": 0.6,        # px/frame at analysis scale counted as moving
    "pool": 4,
    "min_frames": 4,
    "min_area": 0.003,      # share of the frame (max over the move's frames)
    "split_frac": 0.15,
    "split_run": 3,
    "geom_min": 0.015,      # frame fraction an edge must move to call it geometric
    "fit_samples_min": 8,
    "rigid_min": 0.55,      # affine R^2 below this = non-rigid (organic) motion
    "min_w": 0.03, "min_h": 0.02,  # smallest region kept, frame fractions
}

FARNEBACK = dict(pyr_scale=0.5, levels=4, winsize=21, iterations=3, poly_n=7, poly_sigma=1.5, flags=0)


def bezier_eval(params, tau):
    """CSS cubic-bezier y(x) at x = tau; x1, x2 in [0, 1] so x(s) is monotone."""
    x1, y1, x2, y2 = params
    s = np.clip(np.asarray(tau, dtype=float), 0, 1).copy()
    for _ in range(8):  # Newton on x(s) - tau, then bisection fallback
        xs = 3 * (1 - s) ** 2 * s * x1 + 3 * (1 - s) * s ** 2 * x2 + s ** 3
        dx = 3 * (1 - s) ** 2 * x1 + 6 * (1 - s) * s * (x2 - x1) + 3 * s ** 2 * (1 - x2)
        ok = np.abs(dx) > 1e-6
        s = np.where(ok, np.clip(s - (xs - tau) / np.where(ok, dx, 1), 0, 1), s)
    lo, hi = np.zeros_like(s), np.ones_like(s)
    for _ in range(30):
        xs = 3 * (1 - s) ** 2 * s * x1 + 3 * (1 - s) * s ** 2 * x2 + s ** 3
        bad = np.abs(xs - tau) > 1e-5
        if not bad.any():
            break
        hi = np.where(bad & (xs > tau), s, hi)
        lo = np.where(bad & (xs <= tau), s, lo)
        s = np.where(bad, (lo + hi) / 2, s)
    return 3 * (1 - s) ** 2 * s * y1 + 3 * (1 - s) * s ** 2 * y2 + s ** 3


def fit_bezier(tau, prog):
    starts = [(0.25, 0.1, 0.25, 1.0), (0.0, 0.0, 0.58, 1.0), (0.42, 0.0, 0.58, 1.0),
              (0.33, 0.33, 0.67, 0.67), (0.34, 1.56, 0.64, 1.0)]
    best = None
    for st in starts:
        r = least_squares(lambda p: bezier_eval(p, tau) - prog, st,
                          bounds=([0, -1.0, 0, -1.0], [1, 2.0, 1, 2.5]), method="trf",
                          xtol=1e-10, ftol=1e-10, max_nfev=400)
        cost = float(np.sqrt(np.mean(r.fun ** 2)))
        if best is None or cost < best[1] - 1e-9:
            best = (r.x, cost)
    return [float(v) for v in best[0]], best[1]


def affine_flow(u, v, mask, cx, cy):
    """Fit u, v = affine(x, y). Returns translation, divergence, curl and rigidity (R^2
    of the fit). Scale and rotation are only trusted when the moving pixels span at
    least 6 px on both axes; otherwise only translation is returned."""
    ys, xs = np.nonzero(mask)
    if len(xs) < 12:
        return None
    uu, vv = u[ys, xs].astype(float), v[ys, xs].astype(float)
    if xs.std() < 6 or ys.std() < 6:
        tx, ty = float(uu.mean()), float(vv.mean())
        res = ((uu - tx) ** 2 + (vv - ty) ** 2).sum()
        tot = (uu ** 2 + vv ** 2).sum() + 1e-9
        return tx, ty, 0.0, 0.0, float(1 - res / tot)
    X = np.stack([np.ones_like(xs, dtype=float), xs - cx, ys - cy], 1)
    cu, *_ = np.linalg.lstsq(X, uu, rcond=None)
    cv_, *_ = np.linalg.lstsq(X, vv, rcond=None)
    res = ((X @ cu - uu) ** 2 + (X @ cv_ - vv) ** 2).sum()
    tot = (uu ** 2 + vv ** 2).sum() + 1e-9
    tx, ty = cu[0], cv_[0]
    div = (cu[1] + cv_[2]) / 2
    curl = (cv_[1] - cu[2]) / 2
    return tx, ty, div, curl, float(1 - res / tot)


def measure(path: str, timing: dict | None = None) -> dict:
    pr = probe(path)
    fps = pr["fps"]
    size = analysis_size(pr["width"], pr["height"], P["long_side"])
    W, H = size
    long_side = max(W, H)
    G = load_frames(path, fps, size, gray=True)
    n = len(G)
    dur = n / fps

    blank = np.zeros(n, bool)
    cut_frames = set()
    if timing:
        for c in timing.get("cuts", []):
            k = int(round(c * fps))
            cut_frames.add(k)
            blank[max(0, k - 1):min(n, k + 2)] = True
        for tr in timing.get("dissolves", []):
            blank[max(0, int(math.floor(tr["t0"] * fps))):min(n, int(math.ceil(tr["t1"] * fps)) + 2)] = True

    # flow
    U = np.zeros((n, H, W), np.float32)
    V = np.zeros((n, H, W), np.float32)
    raw = np.zeros(n)
    for t in range(1, n):
        f = cv2.calcOpticalFlowFarneback(G[t - 1], G[t], None, **FARNEBACK)
        U[t], V[t] = f[..., 0], f[..., 1]
        raw[t] = float(np.hypot(f[..., 0], f[..., 1]).mean()) / long_side * fps
    raw[0] = raw[1] if n > 1 else 0.0
    for k in sorted(cut_frames):
        if 0 < k < n:
            nb = [raw[j] for j in (k - 2, k + 2) if 0 <= j < n and j not in cut_frames]
            raw[k] = float(np.mean(nb)) if nb else 0.0
            if k + 1 < n:
                raw[k + 1] = raw[k]

    # energy at 10 Hz
    nb = int(math.ceil(dur * 10 - 1e-9))
    bins = np.zeros(nb)
    for b in range(nb):
        lo, hi = int(math.floor(b / 10 * fps)), int(math.floor((b + 1) / 10 * fps))
        seg = raw[lo:max(hi, lo + 1)]
        bins[b] = seg.mean() if len(seg) else 0.0
    peak = bins.max() if nb else 0.0
    norm = bins / peak if peak > 0 else bins
    peak_times = []
    order = np.argsort(-bins, kind="stable")
    for i in order:
        if bins[i] <= 0 or len(peak_times) >= 5:
            break
        if 0 < i < nb - 1 and not (bins[i] >= bins[i - 1] and bins[i] >= bins[i + 1]):
            continue
        if all(abs(i / 10 - p) >= 1.0 for p in peak_times):
            peak_times.append(i / 10)

    # move segmentation
    mag = np.hypot(U, V)
    m = mag > P["flow_thr"]
    m[blank] = False
    m[0] = False
    pp = P["pool"]
    gh, gw = H // pp, W // pp
    pooled = m[:, :gh * pp, :gw * pp].reshape(n, gh, pp, gw, pp).max(axis=(2, 4))
    pooled = ndimage.binary_closing(pooled, structure=np.ones((3, 1, 1), bool))
    pooled[blank] = False
    lab, nlab = ndimage.label(pooled, structure=ndimage.generate_binary_structure(3, 3))
    objs = ndimage.find_objects(lab)
    segments = []
    for li, sl in enumerate(objs, start=1):
        if sl is None:
            continue
        comp = lab[sl] == li
        area_t = comp.sum(axis=(1, 2)).astype(float)
        t_base = sl[0].start
        # split where activity collapses
        thr = P["split_frac"] * area_t.max()
        low = area_t < thr
        start = 0
        k = 0
        pieces = []
        while k < len(area_t):
            if low[k]:
                j = k
                while j < len(area_t) and low[j]:
                    j += 1
                if j - k >= P["split_run"]:
                    if k > start:
                        pieces.append((start, k))
                    start = j
                k = j
            else:
                k += 1
        if start < len(area_t):
            pieces.append((start, len(area_t)))
        for a, b in pieces:
            sub = comp[a:b]
            if b - a < P["min_frames"]:
                continue
            if sub.sum(axis=(1, 2)).max() / (gh * gw) < P["min_area"]:
                continue
            ys, xs = np.nonzero(sub.any(axis=0))
            y0, y1 = (ys.min() + sl[1].start) * pp, (ys.max() + 1 + sl[1].start) * pp
            x0, x1 = (xs.min() + sl[2].start) * pp, (xs.max() + 1 + sl[2].start) * pp
            if (x1 - x0) / W < P["min_w"] or (y1 - y0) / H < P["min_h"]:
                continue
            full = np.zeros((b - a, H, W), bool)
            up = np.repeat(np.repeat(sub, pp, 1), pp, 2)
            full[:, sl[1].start * pp:sl[1].start * pp + up.shape[1],
                 sl[2].start * pp:sl[2].start * pp + up.shape[2]] = up
            segments.append((t_base + a, t_base + b - 1, x0, y0, x1, y1, full))
    segments.sort(key=lambda s: (s[0], s[3], s[2], s[1]))

    moves = []
    for f0, f1, x0, y0, x1, y1, full in segments:
        moves.append(analyse_move(G, U, V, mag, f0, f1, x0, y0, x1, y1, full, fps, W, H))

    dur_list = [mv["duration"] for mv in moves]
    hi_conf = [mv for mv in moves if mv["confidence"] == "high"]
    return {
        "energy": {"hz": 10, "values": norm.tolist(), "raw": bins.tolist(),
                   "unit": "frame_long_sides_per_s", "peak_raw": float(peak)},
        "energy_stats": {"mean": float(bins.mean()) if nb else 0.0,
                         "p90": pct(bins, 90) if nb else 0.0,
                         "mean_norm": float(norm.mean()) if nb else 0.0,
                         "peak_times": sorted(peak_times)},
        "moves": moves,
        "move_stats": {
            "count": len(moves),
            "per_10s": len(moves) / dur * 10 if dur else 0.0,
            "high_confidence": len(hi_conf),
            "duration_median": pct(dur_list, 50),
            # start-to-land of rigid moves fitted at medium confidence or better: the
            # segment extent is threshold bound (faster moves stay above the flow
            # threshold longer) and the high-only set changes with frame drops
            "fitted_duration_median": pct([mv["active_duration"] for mv in moves
                                           if mv["confidence"] != "low" and mv["property"] != "organic"], 50),
            "overshoot_share": (sum(1 for mv in hi_conf if mv["overshoot"] > 0.02) / len(hi_conf))
            if hi_conf else None,
        },
    }


def analyse_move(G, U, V, mag, f0, f1, x0, y0, x1, y1, full, fps, W, H):
    long_side = max(W, H)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    R = math.sqrt(max(1, (x1 - x0) * (y1 - y0)))
    k = f1 - f0 + 1
    tx = np.zeros(k); ty = np.zeros(k); dv = np.zeros(k); cl = np.zeros(k)
    rig_w = []
    for i, t in enumerate(range(f0, f1 + 1)):
        mk = full[i] & (mag[t] > P["flow_thr"])
        r = affine_flow(U[t], V[t], mk, cx, cy)
        if r:
            tx[i], ty[i], dv[i], cl[i], rg = r
            rig_w.append((rg, float(mag[t][mk].sum())))
    rigidity = (sum(a * b for a, b in rig_w) / max(1e-9, sum(b for _, b in rig_w))) if rig_w else 0.0
    dv = np.clip(dv, -0.1, 0.1)
    cl = np.clip(cl, -0.1, 0.1)
    X, Y = np.cumsum(tx), np.cumsum(ty)
    LS = np.clip(np.cumsum(np.log1p(dv)), -3, 3)
    TH = np.cumsum(cl)
    # edge displacement in px for each property (peak over the path, so go-and-return counts)
    disp = np.hypot(X, Y)
    trans_px = float(disp.max())
    scale_px = float(np.abs(np.expm1(LS)).max() * R / 2)
    rot_px = float(np.abs(TH).max() * R / 2)
    # intensity change over the bbox: frame before vs last frame
    pre = G[max(0, f0 - 1), y0:y1, x0:x1].astype(np.float32)
    post = G[f1, y0:y1, x0:x1].astype(np.float32)
    seq = G[max(0, f0 - 1):f1 + 1, y0:y1, x0:x1].astype(np.float32)
    dI = post - pre
    changed = np.abs(dI) > 20
    chg_share = float(changed.mean()) if changed.size else 0.0

    cand = {"translate": trans_px, "scale": scale_px, "rotate": rot_px}
    order = sorted(cand, key=lambda p: (-cand[p], p))
    geom_thr = P["geom_min"] * long_side
    ambiguous = False
    if cand[order[0]] >= geom_thr and rigidity < P["rigid_min"]:
        prop = "organic"  # non-rigid flow: footage, hands, faces, smoke; no clean curve
        ambiguous = True
    elif cand[order[0]] >= geom_thr:
        prop = order[0]
        ambiguous = cand[order[1]] > 0.6 * cand[order[0]]
    elif chg_share > 0.05:
        # opacity vs mask-wipe from per-pixel switch timing
        prog = (seq - pre) / np.where(np.abs(dI) < 1, 1, dI)
        tcross = np.argmax(prog >= 0.5, axis=0).astype(np.float32)
        ys, xs = np.nonzero(changed)
        tc = tcross[ys, xs]
        r_best = 0.0
        if tc.std() > 0.5 and len(tc) > 20:
            for coord in (xs, ys, xs + ys, xs - ys):
                coord = coord.astype(np.float32)
                if coord.std() > 0:
                    r_best = max(r_best, abs(float(np.corrcoef(coord, tc)[0, 1])))
        prop = "mask-wipe" if r_best > 0.6 else "opacity"
    else:
        prop = order[0]
        ambiguous = True

    # progress curve, sample 0 = frame before the move (progress 0)
    if prop in ("translate", "organic"):
        end = np.array([X[-1], Y[-1]])
        nrm = float(np.hypot(*end))
        if nrm < 1e-6:
            idx = int(np.argmax(disp))
            end = np.array([X[idx], Y[idx]]); nrm = float(np.hypot(*end)) or 1.0
        p = (X * end[0] + Y * end[1]) / (nrm * nrm)
        dxf, dyf = float(X[-1]) / W, float(Y[-1]) / H
        travel = math.hypot(dxf, dyf)
        amount = {"dx": dxf, "dy": dyf, "angle_deg": math.degrees(math.atan2(Y[-1], X[-1]))}
    elif prop == "scale":
        p = LS / (LS[-1] if abs(LS[-1]) > 1e-6 else (LS[np.argmax(np.abs(LS))] or 1.0))
        travel = scale_px / long_side
        amount = {"scale_ratio": float(math.exp(LS[-1]))}
    elif prop == "rotate":
        p = TH / (TH[-1] if abs(TH[-1]) > 1e-6 else (TH[np.argmax(np.abs(TH))] or 1.0))
        travel = rot_px / long_side
        amount = {"degrees": float(math.degrees(TH[-1]))}
    elif prop == "opacity":
        den = float((dI * dI).sum()) or 1.0
        p = np.array([float(((s - pre) * dI).sum()) / den for s in seq[1:]])
        travel = 0.0
        amount = {"luma_delta": float(dI.mean()) / 255}
    else:  # mask-wipe
        crossed = ((seq[1:] - pre) / np.where(np.abs(dI) < 1, 1, dI) >= 0.5) & changed
        p = crossed.reshape(len(crossed), -1).sum(1) / max(1, changed.sum())
        travel = math.hypot((x1 - x0) / W, (y1 - y0) / H)
        amount = {"changed_share": chg_share}

    p = np.concatenate([[0.0], np.asarray(p, float)])
    tau = np.linspace(0, 1, len(p))
    end_val = float(np.mean(p[-2:])) if len(p) > 2 else 1.0
    if abs(end_val) > 1e-6:
        p = p / end_val
    overshoot = max(0.0, float(p.max()) - 1.0)
    bez, err = fit_bezier(tau, p)
    tv = float(np.abs(np.diff(p)).sum())
    noisy = tv > 1 + 2 * overshoot + 0.35
    # keyframes for binding sound and VO: start (progress leaves 0), peak (fastest
    # sample), land (first arrival at the end value, the impact under overshoot)
    ts = (f0 - 1 + np.arange(len(p))) / fps
    vel = np.abs(np.diff(p))
    i_start = int(np.argmax(p > 0.05)) if (p > 0.05).any() else 0
    i_peak = int(np.argmax(vel)) + 1 if len(vel) else 0
    i_land = int(np.argmax(p >= 0.98)) if (p >= 0.98).any() else len(p) - 1
    keyframes = {"start": float(ts[max(0, i_start - 1)]), "peak": float(ts[i_peak] - 0.5 / fps),
                 "land": float(ts[i_land])}
    n_s = len(p)
    if err <= 0.035 and n_s >= P["fit_samples_min"] and not ambiguous and not noisy and prop != "organic":
        conf = "high"
    elif err <= 0.08 and n_s >= 5 and not noisy:
        conf = "medium"
    else:
        conf = "low"
    t0 = (f0 - 1) / fps
    t1 = f1 / fps
    return {
        "t0": t0, "t1": t1, "duration": t1 - t0,
        "region": {"x": x0 / W, "y": y0 / H, "w": (x1 - x0) / W, "h": (y1 - y0) / H},
        "property": prop,
        "property_scores": {"translate": trans_px / long_side, "scale": scale_px / long_side,
                            "rotate": rot_px / long_side, "pixel_change": chg_share},
        "travel": travel, "amount": amount,
        "bezier": bez, "overshoot": overshoot, "fit_error": err, "confidence": conf,
        "samples": n_s, "keyframes": keyframes, "rigidity": rigidity,
        "active_duration": max(keyframes["land"] - keyframes["start"], 1 / fps),
        "flags": [f for f, on in (("ambiguous_property", ambiguous), ("noisy_progress", noisy),
                                  ("few_samples", n_s < P["fit_samples_min"])) if on],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("--out")
    ap.add_argument("--no-timing", action="store_true", help="skip cut detection (moves may include transitions)")
    a = ap.parse_args()
    timing = None
    if not a.no_timing:
        import cuts
        timing = cuts.public(cuts.measure(a.video))
    emit(measure(a.video, timing), a.out)


if __name__ == "__main__":
    main()
