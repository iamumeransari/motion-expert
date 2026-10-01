"""Imagery: the photographic look of every shot, and the style's look profile.

Shots. Boundaries come from a fingerprint (timing.cuts and timing.dissolves), a
cuts.json from cuts.py (cuts and dissolves), or, with `--cuts none`, from running
cuts.py here. Soft-transition spans are excluded from the shot on either side, and
shots under 0.3 s are skipped. The whole video is decoded once at a long side of
480 px in grey; per frame, sharpness is the variance of the Laplacian and motion is
the mean absolute grey difference to the previous frame. The representative clean
frame of a shot is the one, inside the middle 70 % of the shot, that maximises
log(sharpness) - 2 log(1 + motion), so it is in focus and between moves. That frame
is decoded again at source resolution and saved as frames/shot-NN.jpg; every number
below is measured on the decoded pixels, never the jpeg.

Every image is measured by measure_image() at a long side of 1920 px, so a
generated still and a video frame are read by identical code at an identical scale.

Profiles. `look` aggregates the shots named by --group (every photo shot when no
group is given) as a median and a p10 to p90 band per feature, widened to a floor;
`looks` holds each named group, so a film with a studio family and a city family
yields one profile for each. --regroup rebuilds the profiles from an existing
imagery.json without decoding again.

Kind. A frame is "graphic" (a type card, UI, a flat colour field) when, after a
sigma-2 blur at 240 px, the three most common 16-level colours cover over half the
frame or flat pixels cover over 70 %; otherwise it is "photo". The look profile
aggregates photo frames only.

Grade. CIE Lab from sRGB (D65). Tone: black point and white point are the 1st and
99th percentiles of Rec.709 luma (0 to 255), contrast is the luma standard
deviation over 255, mean_L is mean Lab lightness. Split toning is the mean a* and
b* of shadows (L < 33), midtones (33 to 66) and highlights (L > 66). The cast is
the mean a* and b* of near-neutral pixels (chroma under 12), which is white balance
read off what should be grey. Curves are the 1, 5, 10, 25, 50, 75, 90, 95 and 99th
percentiles of each of R, G and B and of Lab L (L_pcts, aggregated as L_curve); curve offsets subtract the luma percentile, so a
neutral grade reads 0 everywhere. Saturation is mean and 90th percentile Lab chroma.

Grain. The grey frame minus its sigma-2 Gaussian blur, taken over flat pixels
(blurred gradient under 3 levels per px, luma 20 to 235). Amount is the robust
standard deviation (1.4826 MAD) in grey levels; size is the lag in px at which the
residual's autocorrelation falls to 0.5, interpolated, so fine 35 mm grain reads
near 1 and clumpy or upscaled grain reads higher; chroma is the same robust
deviation on a* and b* relative to the luma one. Source grain is what survived the
source's encode, which is why `toolkit/imagery.py grade` calibrates its own grain
through an encode round trip.

Focus and depth of field. On a 12 x 7 grid at 480 px, each tile's sharpness is the
Laplacian variance after a light blur that removes grain. focus_share is the share
of tiles above a quarter of the 95th percentile tile; dof is "shallow" under 0.35
and "deep" over 0.7. acutance is the median of the sharpest tenth of tiles.

Composition. Faces come from OpenCV's YuNet (vendor/face_detection_yunet_2023mar.onnx)
at 640 px. With a face, the subject is the largest face and headroom is the gap from
the frame top to the estimated top of the head (face top minus a quarter of the face
height); shot scale reads from face height: extreme-close over 0.5 of the frame height,
close over 0.32, medium over 0.12, wide over 0.04, else extreme-wide. Without a
face, the subject is the sharpness-weighted centroid and bounding box of in-focus
tiles and the scale reads from that box's area: close over 0.45, medium over 0.15,
else wide. Positions are frame fractions from the top left.

Lighting. Key is high when mean L is over 62 with under 10 % deep shadow (L < 25),
low when mean L is under 38 or deep shadow is over 40 %, else mid. Direction comes
from the inner face box when there is a face (so hair and background do not vote),
else from the focus box: the normalised lightness difference right minus left,
called frontal under 0.06. Above or below is only called on a face-free region
when the vertical difference is over 0.12 and 1.5 times the horizontal one,
because on a portrait dark hair above and a lit neck below fake it. subject_contrast is the 90th minus 10th percentile L over the
same probe region (skin only on a face), a hard-light proxy. Vignette is the mean L of the four corner boxes
(15 % each side) over the mean L of the central 40 % box.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from common import analysis_size, emit, frames_at_times, load_frames, probe, sha256  # noqa: E402

cv2.setNumThreads(2)

VERSION = 1
YUNET = Path(__file__).resolve().parent.parent / "vendor" / "face_detection_yunet_2023mar.onnx"
PCTS = [1, 5, 10, 25, 50, 75, 90, 95, 99]

# Scored features, their weight in the look distance and the smallest half-band
# (in the feature's own units) so a profile measured off near-identical frames
# still tolerates measurement noise.
FEATURES = {
    "grade.shadows_a": (1.0, 2.0), "grade.shadows_b": (1.0, 2.0),
    "grade.mids_a": (1.5, 2.0), "grade.mids_b": (1.5, 2.0),
    "grade.highlights_a": (1.5, 2.0), "grade.highlights_b": (1.5, 2.0),
    "grade.cast_a": (1.0, 1.5), "grade.cast_b": (1.0, 1.5),
    "tone.black_point": (1.0, 4.0), "tone.white_point": (1.0, 5.0),
    "tone.contrast": (1.5, 0.02), "tone.mean_L": (0.5, 5.0),
    "sat.chroma_mean": (1.5, 2.0), "sat.chroma_p90": (0.5, 3.0),
    "grain.amount": (1.0, 0.15), "grain.size": (0.5, 0.2),
    "vignette": (0.25, 0.08),
    "focus.focus_share": (0.5, 0.1),
    "comp.x": (0.5, 0.06), "comp.y": (0.5, 0.06), "comp.headroom": (0.5, 0.04),
}
COMPOSITION = {"comp.x", "comp.y", "comp.headroom"}


# ------------------------------------------------------------------ colour

def to_lab(rgb_u8: np.ndarray) -> np.ndarray:
    """sRGB uint8 -> Lab float32 (L 0-100, a/b roughly -128..127), D65."""
    return cv2.cvtColor(rgb_u8.astype(np.float32) / 255.0, cv2.COLOR_RGB2Lab)


def luma(rgb_u8: np.ndarray) -> np.ndarray:
    f = rgb_u8.astype(np.float32)
    return 0.2126 * f[..., 0] + 0.7152 * f[..., 1] + 0.0722 * f[..., 2]


def standard(rgb_u8: np.ndarray, long_side: int = 1920) -> np.ndarray:
    h, w = rgb_u8.shape[:2]
    if max(h, w) == long_side:
        return rgb_u8
    s = long_side / max(h, w)
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC
    return cv2.resize(rgb_u8, (int(round(w * s)), int(round(h * s))), interpolation=interp)


def resize_long(img, long_side, interp=cv2.INTER_AREA):
    h, w = img.shape[:2]
    s = long_side / max(h, w)
    return cv2.resize(img, (max(2, int(round(w * s))), max(2, int(round(h * s)))), interpolation=interp)


# ------------------------------------------------------------------ pieces

def kind_of(rgb):
    small = resize_long(rgb, 240)
    b = cv2.GaussianBlur(small, (0, 0), 2)
    q = (b // 16).astype(np.int32)
    code = q[..., 0] * 256 + q[..., 1] * 16 + q[..., 2]
    counts = np.bincount(code.ravel())
    top3 = float(np.sort(counts)[::-1][:3].sum() / code.size)
    g = cv2.cvtColor(b, cv2.COLOR_RGB2GRAY).astype(np.float32)
    gm = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
    flat = float((gm < 1.5).mean())
    kind = "graphic" if (top3 > 0.5 or flat > 0.7) else "photo"
    return kind, {"top3_share": top3, "flat_share": flat}


def grain_of(rgb, lab):
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    blur = cv2.GaussianBlur(g, (0, 0), 2)
    resid = g - blur
    gm = np.hypot(cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3) / 8, cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3) / 8)
    flat = (gm < 3) & (g > 20) & (g < 235)
    flat = cv2.erode(flat.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    if flat.sum() < 2000:
        return {"amount": None, "size": None, "chroma": None, "flat_share": float(flat.mean())}

    def rstd(x):
        return float(1.4826 * np.median(np.abs(x - np.median(x))))
    amount = rstd(resid[flat])
    var = float(np.mean(resid[flat] ** 2)) or 1e-6
    ac = [1.0]
    for lag in (1, 2, 3, 4):
        vals = []
        for (dy, dx) in ((0, lag), (lag, 0)):
            a = resid[: resid.shape[0] - dy, : resid.shape[1] - dx]
            b = resid[dy:, dx:]
            m = flat[: flat.shape[0] - dy, : flat.shape[1] - dx] & flat[dy:, dx:]
            if m.sum() > 1000:
                vals.append(float(np.mean(a[m] * b[m])) / var)
        ac.append(float(np.mean(vals)) if vals else 0.0)
    size = 4.0
    for lag in range(1, len(ac)):
        if ac[lag] <= 0.5:
            size = (lag - 1) + (ac[lag - 1] - 0.5) / max(1e-6, ac[lag - 1] - ac[lag])
            break
    ca = lab[..., 1] - cv2.GaussianBlur(lab[..., 1], (0, 0), 2)
    cb = lab[..., 2] - cv2.GaussianBlur(lab[..., 2], (0, 0), 2)
    # Lab a/b are in different units from grey levels; express chroma grain as
    # their robust deviation over luma grain in L units (L 0-100 vs grey 0-255).
    l_amount = amount * 100 / 255
    chroma = (rstd(ca[flat]) + rstd(cb[flat])) / 2 / max(1e-3, l_amount)
    return {"amount": amount, "size": size, "chroma": chroma, "flat_share": float(flat.mean()),
            "autocorr": ac}


def focus_of(rgb):
    small = resize_long(rgb, 480)
    g = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY).astype(np.float32), (0, 0), 0.8)
    lap = cv2.Laplacian(g, cv2.CV_32F)
    H, W = g.shape
    nx, ny = 12, 7
    tiles = np.zeros((ny, nx))
    for j in range(ny):
        for i in range(nx):
            t = lap[j * H // ny:(j + 1) * H // ny, i * W // nx:(i + 1) * W // nx]
            tiles[j, i] = float(t.var())
    p95 = float(np.percentile(tiles, 95)) or 1e-6
    sharp = tiles > 0.25 * p95
    share = float(sharp.mean())
    acut = float(np.median(np.sort(tiles.ravel())[::-1][: max(1, tiles.size // 10)]))
    ys, xs = np.nonzero(sharp)
    w = tiles[sharp]
    cx = float(((xs + 0.5) / nx * w).sum() / w.sum())
    cy = float(((ys + 0.5) / ny * w).sum() / w.sum())
    box = [float(xs.min() / nx), float(ys.min() / ny), float((xs.max() + 1) / nx), float((ys.max() + 1) / ny)]
    dof = "shallow" if share < 0.35 else ("deep" if share > 0.7 else "moderate")
    return {"focus_share": share, "acutance": acut, "dof": dof, "centroid": [cx, cy], "box": box}


_detector = None


def faces_of(rgb):
    global _detector
    small = resize_long(rgb, 640)
    h, w = small.shape[:2]
    if _detector is None:
        if not YUNET.exists():
            return []
        _detector = cv2.FaceDetectorYN.create(str(YUNET), "", (w, h), 0.75, 0.3, 5000)
    _detector.setInputSize((w, h))
    _, found = _detector.detect(cv2.cvtColor(small, cv2.COLOR_RGB2BGR))
    out = []
    if found is not None:
        for f in found:
            x, y, fw, fh = [float(v) for v in f[:4]]
            out.append({"box": [x / w, y / h, (x + fw) / w, (y + fh) / h], "score": float(f[-1])})
    out.sort(key=lambda f: -(f["box"][2] - f["box"][0]) * (f["box"][3] - f["box"][1]))
    return out


def region_mean(L, box):
    H, W = L.shape
    x0, y0, x1, y1 = box
    x0, x1 = int(max(0, x0) * W), int(min(1, x1) * W)
    y0, y1 = int(max(0, y0) * H), int(min(1, y1) * H)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    return L[y0:y1, x0:x1]


def measure_image(rgb_in: np.ndarray) -> dict:
    """Every look metric for one RGB uint8 image, measured at a 1920 long side."""
    rgb = standard(rgb_in)
    H, W = rgb.shape[:2]
    lab = to_lab(rgb)
    L, A, B = lab[..., 0], lab[..., 1], lab[..., 2]
    Y = luma(rgb)
    C = np.hypot(A, B)
    kind, kind_feat = kind_of(rgb)

    yp = np.percentile(Y, PCTS)
    curves = {ch: np.percentile(rgb[..., k], PCTS).tolist() for k, ch in enumerate("rgb")}
    offsets = {ch: (np.array(curves[ch]) - yp).tolist() for ch in "rgb"}
    tone = {
        "black_point": float(yp[0]), "white_point": float(yp[-1]),
        "p5": float(yp[1]), "p50": float(yp[4]), "p95": float(yp[7]),
        "contrast": float(Y.std() / 255), "mean_L": float(L.mean()),
        "shadow_share": float((L < 25).mean()), "highlight_share": float((L > 80).mean()),
        "L_pcts": np.percentile(L, PCTS).tolist(),
    }
    grade = {}
    for zone, m in (("shadows", L < 33), ("mids", (L >= 33) & (L <= 66)), ("highlights", L > 66)):
        ok = m.mean() > 0.01
        grade[f"{zone}_a"] = float(A[m].mean()) if ok else None
        grade[f"{zone}_b"] = float(B[m].mean()) if ok else None
        grade[f"{zone}_share"] = float(m.mean())
    neutral = C < 12
    grade["cast_a"] = float(A[neutral].mean()) if neutral.mean() > 0.01 else None
    grade["cast_b"] = float(B[neutral].mean()) if neutral.mean() > 0.01 else None
    means = rgb.reshape(-1, 3).astype(np.float64).mean(0)
    grade["r_over_g"] = float(means[0] / max(1e-6, means[1]))
    grade["b_over_g"] = float(means[2] / max(1e-6, means[1]))
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    sat = {"chroma_mean": float(C.mean()), "chroma_p90": float(np.percentile(C, 90)),
           "hsv_s_mean": float(hsv[..., 1].mean() / 255)}

    grain = grain_of(rgb, lab)
    focus = focus_of(rgb)
    faces = faces_of(rgb)

    if faces:
        f = faces[0]["box"]
        fh = f[3] - f[1]
        fw = f[2] - f[0]
        head_top = f[1] - 0.25 * fh
        scale = ("extreme-close" if fh > 0.5 else "close" if fh > 0.32 else "medium" if fh > 0.12
                 else "wide" if fh > 0.04 else "extreme-wide")
        comp = {"basis": "face", "x": (f[0] + f[2]) / 2, "y": (f[1] + f[3]) / 2,
                "headroom": max(0.0, head_top), "face_h": fh, "box": f, "scale": scale}
        region = [f[0] - 0.3 * fw, f[1] - 0.3 * fh, f[2] + 0.3 * fw, f[3] + 0.3 * fh]
    else:
        bx = focus["box"]
        area = (bx[2] - bx[0]) * (bx[3] - bx[1])
        scale = "close" if area > 0.45 else "medium" if area > 0.15 else "wide"
        comp = {"basis": "focus", "x": focus["centroid"][0], "y": focus["centroid"][1],
                "headroom": bx[1], "face_h": None, "box": bx, "scale": scale, "box_area": area}
        region = bx
    comp["thirds_dist"] = float(min(math.hypot(comp["x"] - tx, comp["y"] - ty)
                                    for tx in (1 / 3, 2 / 3) for ty in (1 / 3, 2 / 3)))

    sub = region_mean(L, region)
    if sub is None:
        sub = L
    # Direction reads off the face itself when there is one (its inner box, so
    # hair and background do not vote), and off the subject region otherwise.
    # Vertical direction is only called on a face-free region and when strong,
    # since hair above and a lit neck below fake it on every portrait.
    probe_reg = sub
    if faces:
        f = faces[0]["box"]
        fw_, fh_ = f[2] - f[0], f[3] - f[1]
        inner = region_mean(L, [f[0] + 0.15 * fw_, f[1] + 0.2 * fh_, f[2] - 0.15 * fw_, f[3] - 0.1 * fh_])
        if inner is not None:
            probe_reg = inner
    sh, sw = probe_reg.shape
    dx = float((probe_reg[:, sw // 2:].mean() - probe_reg[:, : sw // 2].mean()) / max(1.0, probe_reg.mean()))
    dy = float((probe_reg[sh // 2:, :].mean() - probe_reg[: sh // 2, :].mean()) / max(1.0, probe_reg.mean()))
    if not faces and abs(dy) > max(0.12, 1.5 * abs(dx)):
        direction = "from below" if dy > 0 else "from above"
    elif abs(dx) < 0.06:
        direction = "frontal"
    else:
        direction = "from right" if dx > 0 else "from left"
    mL = tone["mean_L"]
    key = ("high" if mL > 62 and tone["shadow_share"] < 0.10 else
           "low" if (mL < 38 or tone["shadow_share"] > 0.40) else "mid")
    light = {"key": key, "direction": direction, "dx": dx, "dy": dy,
             "subject_contrast": float(np.percentile(probe_reg, 90) - np.percentile(probe_reg, 10))}

    cw, ch_ = int(W * 0.15), int(H * 0.15)
    corners = np.concatenate([L[:ch_, :cw].ravel(), L[:ch_, -cw:].ravel(), L[-ch_:, :cw].ravel(), L[-ch_:, -cw:].ravel()])
    centre = L[int(H * 0.3):int(H * 0.7), int(W * 0.3):int(W * 0.7)]
    vignette = float(corners.mean() / max(1.0, centre.mean()))

    return {
        "kind": kind, "kind_features": kind_feat, "size": [W, H],
        "tone": tone, "grade": grade, "curves": curves, "curve_offsets": offsets, "sat": sat,
        "grain": grain, "focus": focus, "faces": faces[:3], "comp": comp, "light": light,
        "vignette": vignette,
    }


def flat(m: dict) -> dict:
    """The scored features of one measure_image() result, as a flat dict."""
    out = {}
    for key in FEATURES:
        if key == "vignette":
            out[key] = m.get("vignette")
            continue
        group, name = key.split(".", 1)
        out[key] = (m.get(group) or {}).get(name)
    return out


def palette(rgbs, k=6):
    """Dominant colours across images, k-means in Lab via look.py."""
    import look  # noqa: E402  (same directory)
    X = np.concatenate([look.srgb_to_lab(resize_long(r, 120)).reshape(-1, 3) for r in rgbs])
    Cc, share = look.kmeans_lab(X, k, 7)
    order = sorted(range(k), key=lambda j: -share[j])
    return [{"hex": look.lab_to_hex(Cc[j]), "lab": [float(v) for v in Cc[j]], "share": float(share[j])}
            for j in order if share[j] > 0]


# ------------------------------------------------------------------ profile

def aggregate(entries: list[dict]) -> dict:
    """Profile from a list of measure_image() results (photo frames)."""
    feats = [flat(e) for e in entries]
    stats = {}
    for key, (weight, floor) in FEATURES.items():
        vals = np.array([f[key] for f in feats if f.get(key) is not None], dtype=float)
        if vals.size == 0:
            continue
        med = float(np.median(vals))
        p10, p90 = (float(np.percentile(vals, 10)), float(np.percentile(vals, 90))) if vals.size > 2 else (med, med)
        lo, hi = min(p10, med - floor), max(p90, med + floor)
        stats[key] = {"median": med, "p10": p10, "p90": p90, "band": [lo, hi], "n": int(vals.size),
                      "weight": weight}
    scales = {}
    for e in entries:
        scales.setdefault(e["comp"]["scale"], []).append(e)
    by_scale = {}
    for s, es in scales.items():
        by_scale[s] = {
            "count": len(es),
            "x": float(np.median([e["comp"]["x"] for e in es])),
            "y": float(np.median([e["comp"]["y"] for e in es])),
            "headroom": float(np.median([e["comp"]["headroom"] for e in es])),
            "focus_share": float(np.median([e["focus"]["focus_share"] for e in es])),
            "light_direction": max(set(e["light"]["direction"] for e in es),
                                   key=lambda d: sum(e["light"]["direction"] == d for e in es)),
        }
    curves = {ch: np.median([e["curves"][ch] for e in entries], axis=0).tolist() for ch in "rgb"}
    L_curve = np.median([e["tone"]["L_pcts"] for e in entries], axis=0).tolist()
    offsets = {ch: np.median([e["curve_offsets"][ch] for e in entries], axis=0).tolist() for ch in "rgb"}
    keys = [e["light"]["key"] for e in entries]
    dirs = [e["light"]["direction"] for e in entries]
    dofs = [e["focus"]["dof"] for e in entries]
    count = lambda xs: {x: xs.count(x) for x in sorted(set(xs))}  # noqa: E731
    return {
        "n": len(entries),
        "features": stats,
        "curves": curves, "curve_offsets": offsets, "L_curve": L_curve, "percentiles": PCTS,
        "grain_chroma": float(np.median([e["grain"]["chroma"] for e in entries if e["grain"].get("chroma") is not None]
                                        or [0])),
        "shot_scales": count([e["comp"]["scale"] for e in entries]),
        "by_scale": by_scale,
        "light_keys": count(keys), "light_directions": count(dirs), "dof": count(dofs),
        "faces_share": float(np.mean([1.0 if e["faces"] else 0.0 for e in entries])),
    }


def distance(m: dict, profile: dict, composition: bool = True, scale: str | None = None) -> dict:
    """Weighted distance of one measurement to a profile. Each feature's z is how
    far outside its band it sits, in half-band units (0 inside the band). The
    composition targets switch to the named scale's medians when given."""
    f = flat(m)
    feats = profile["features"]
    per, total, wsum = {}, 0.0, 0.0
    for key, st in feats.items():
        if key in COMPOSITION and not composition:
            continue
        v = f.get(key)
        if v is None:
            continue
        lo, hi = st["band"]
        med = st["median"]
        if scale and key in COMPOSITION and scale in profile.get("by_scale", {}):
            med = profile["by_scale"][scale][key.split(".")[1]]
            half = (hi - lo) / 2
            lo, hi = med - half, med + half
        half = max(1e-6, (hi - lo) / 2)
        z = 0.0 if lo <= v <= hi else (lo - v) / half if v < lo else (v - hi) / half
        per[key] = {"value": v, "target": med, "band": [lo, hi], "z": z, "inside": z == 0.0}
        total += st["weight"] * z
        wsum += st["weight"]
    inside = sum(1 for p in per.values() if p["inside"])
    return {"distance": total / max(1e-6, wsum), "inside": inside, "of": len(per), "features": per}


# ------------------------------------------------------------------ shots

def load_bounds(cuts_arg: str | None, video: str):
    if not cuts_arg or cuts_arg == "none":
        import cuts as cuts_mod
        res = cuts_mod.measure(video)
        return res["cuts"], res["dissolves"]
    d = json.loads(Path(cuts_arg).read_text())
    t = d.get("timing", d)
    cuts = []
    for c in t.get("cuts", []) or []:
        cuts.append(float(c["t"] if isinstance(c, dict) else c))
    return cuts, t.get("dissolves", []) or []


def shots_from(cuts, dissolves, dur):
    """Shots as [t0, t1] spans, transition spans removed."""
    marks = [(c, c) for c in cuts] + [(float(d["t0"]), float(d["t1"])) for d in dissolves]
    marks.sort()
    spans, t = [], 0.0
    for a, b in marks:
        if a > t:
            spans.append([t, a])
        t = max(t, b)
    if dur > t:
        spans.append([t, dur])
    return spans


def measure_video(video: str, cuts_arg: str | None, frames_dir: Path, base: Path | None = None, min_len=0.3) -> dict:
    """base is the folder imagery.json lives in; frame paths are written relative to it."""
    pr = probe(video)
    fps, W, H, dur = pr["fps"], pr["width"], pr["height"], pr["duration"]
    cuts, dissolves = load_bounds(cuts_arg, video)
    spans = shots_from(cuts, dissolves, dur)

    G = load_frames(video, fps, analysis_size(W, H, 480), gray=True)
    n = len(G)
    sharp = np.array([cv2.Laplacian(g.astype(np.float32), cv2.CV_32F).var() for g in G])
    motion = np.zeros(n)
    motion[1:] = np.abs(np.diff(G.astype(np.int16), axis=0)).mean(axis=(1, 2))
    motion[0] = motion[1] if n > 1 else 0
    score = np.log(sharp + 1e-6) - 2 * np.log1p(motion)

    picks = []
    for k, (t0, t1) in enumerate(spans):
        if t1 - t0 < min_len:
            continue
        pad = 0.15 * (t1 - t0)
        i0 = int(math.ceil((t0 + pad) * fps))
        i1 = int(math.floor((t1 - pad) * fps))
        i1 = min(i1, n - 1)
        if i1 < i0:
            i0 = i1 = min(n - 1, int((t0 + t1) / 2 * fps))
        best = i0 + int(np.argmax(score[i0:i1 + 1]))
        picks.append((k, t0, t1, best))

    times = [(b + 0.5) / fps for _, _, _, b in picks]
    full = frames_at_times(video, times, (W, H), gray=False, fps=fps)
    frames_dir.mkdir(parents=True, exist_ok=True)
    shots = []
    for (k, t0, t1, b), t, rgb in zip(picks, times, full):
        name = f"shot-{len(shots) + 1:02d}.jpg"
        cv2.imwrite(str(frames_dir / name), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 94])
        m = measure_image(rgb)
        rel = os.path.relpath(frames_dir / name, base or frames_dir.parent)
        shots.append({"index": len(shots) + 1, "t0": t0, "t1": t1, "frame_t": t, "frame": rel,
                      "motion_at_frame": float(motion[b]), **m})

    res = {
        "version": VERSION,
        "source": {"path": pr["path"], "sha256": sha256(video), "width": W, "height": H, "fps": fps, "duration": dur},
        "cuts_from": cuts_arg or "none",
        "shots": shots,
    }
    return res


def parse_ranges(spec: str) -> list[int]:
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def build_looks(res: dict, groups: list[str], frames_root: Path) -> dict:
    """Profiles over the shots. With no groups, one profile over every photo shot.
    A group is name=ranges of shot indices ("editorial=12-21,23-25"), chosen by the
    capturing agent after looking at the frames, because a classifier cannot tell an
    intro montage from the body of a film. `look` is the union of all groups and
    `looks` holds each group on its own."""
    by_index = {s["index"]: s for s in res["shots"]}
    parsed = {}
    for g in groups:
        name, _, spec = g.partition("=")
        parsed[name.strip()] = [i for i in parse_ranges(spec) if i in by_index]
    if not parsed:
        parsed = {"all": [s["index"] for s in res["shots"] if s["kind"] == "photo"]}

    def prof(idx):
        es = [by_index[i] for i in idx]
        if not es:
            return None
        p = aggregate(es)
        rgbs = []
        for s in es:
            img = cv2.imread(str(frames_root / s["frame"]))
            if img is not None:
                rgbs.append(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if rgbs:
            p["palette"] = palette(rgbs)
        p["shots"] = idx
        return p
    union = sorted(set(i for v in parsed.values() for i in v))
    res["groups"] = {k: v for k, v in parsed.items()}
    res["look"] = prof(union)
    res["looks"] = {k: prof(v) for k, v in parsed.items()}
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("--cuts", default="none", help="fingerprint.json, cuts.json, or none to run cuts.py")
    ap.add_argument("--out", required=True, help="imagery.json; frames go in a frames/ folder beside it")
    ap.add_argument("--frames", help="frames folder (default: <out dir>/frames)")
    ap.add_argument("--group", action="append", default=[],
                    help="name=ranges of shot indices forming one look, e.g. editorial=12-21,23-25 (repeatable)")
    ap.add_argument("--regroup", action="store_true",
                    help="reuse the shots already measured in --out and only rebuild the profiles")
    a = ap.parse_args()
    out = Path(a.out)
    frames_dir = Path(a.frames) if a.frames else out.parent / "frames"
    if a.regroup:
        res = json.loads(out.read_text())
    else:
        res = measure_video(a.video, a.cuts, frames_dir, out.parent)
    res = build_looks(res, a.group, out.parent)
    emit(res, str(out))
    lk = res["look"]
    print(f"{len(res['shots'])} shots, {sum(s['kind'] == 'photo' for s in res['shots'])} read as photo, "
          f"{lk['n'] if lk else 0} in the profile; frames in {frames_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
