"""Look: palette, luminance histogram, safe margins, density, sharpness, grain, aspect.

Frames. 32 frames are sampled at evenly spaced times (the centre of 32 equal slices
of the runtime), decoded at a long side of 360 px, so every number is resolution
independent and the sample set is fixed for a given file.

Palette is k-means (k = 8) in CIE Lab (D65, from sRGB) over every pixel of the
sampled frames downscaled to a long side of 120 px, initialised deterministically
by k-means++ with a fixed seed, and reported as hex, Lab and pixel share, largest
share first. The luminance histogram is 16 equal bins of Rec.709 luma, normalised to
sum to 1.

Margins say how deep an empty band each edge keeps. A pixel holds content when its
Sobel edge strength passes 40 (dilated by one pixel), so text, UI and footage count
while flat fills and blurred backgrounds do not. Per frame, each margin is the depth
(as a share of that frame dimension) from the edge to the first row or column with
over 3 % content pixels, and the reported margin is the median over the sampled
frames, so full-bleed footage reads as 0.

Density is the mean share of Canny edge pixels per frame, a proxy for how much text
and graphic detail a frame carries. Sharpness is the variance of the Laplacian on
the 360 px frames, and grain is the robust (MAD) standard deviation of the
high-pass residual (minus a 5 px Gaussian) in flat regions, trimmed at the 99th
percentile, both in grey levels.
"""
from __future__ import annotations

import argparse
import sys

import cv2
import numpy as np

sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import analysis_size, emit, frames_at_times, probe  # noqa: E402

N_FRAMES = 32
K = 8
SEED = 7


def srgb_to_lab(rgb_u8: np.ndarray) -> np.ndarray:
    c = rgb_u8.astype(np.float64) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], -1)


def lab_to_hex(lab) -> str:
    L, a, b = lab
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200
    d = 6 / 29

    def finv(t):
        return t ** 3 if t > d else 3 * d * d * (t - 4 / 29)
    xyz = np.array([finv(fx) * 0.95047, finv(fy), finv(fz) * 1.08883])
    Mi = np.array([[3.2404542, -1.5371385, -0.4985314],
                   [-0.9692660, 1.8760108, 0.0415560],
                   [0.0556434, -0.2040259, 1.0572252]])
    rgb = Mi @ xyz
    rgb = np.where(rgb <= 0.0031308, 12.92 * rgb, 1.055 * np.power(np.clip(rgb, 0, None), 1 / 2.4) - 0.055)
    rgb = np.clip(np.round(rgb * 255), 0, 255).astype(int)
    return "#%02x%02x%02x" % tuple(rgb)


def kmeans_lab(X: np.ndarray, k: int, seed: int, iters: int = 30):
    rng = np.random.default_rng(seed)
    # subsample for init + iterations (deterministic), then assign every pixel
    idx = rng.choice(len(X), size=min(len(X), 60000), replace=False)
    idx.sort()
    S = X[idx]
    centers = [S[rng.integers(len(S))]]
    d2 = ((S - centers[0]) ** 2).sum(1)
    for _ in range(1, k):
        probs = d2 / d2.sum() if d2.sum() > 0 else np.full(len(S), 1 / len(S))
        c = S[rng.choice(len(S), p=probs)]
        centers.append(c)
        d2 = np.minimum(d2, ((S - c) ** 2).sum(1))
    C = np.array(centers)
    for _ in range(iters):
        lab = np.argmin(((S[:, None, :] - C[None]) ** 2).sum(2), 1)
        newC = np.array([S[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
        if np.allclose(newC, C, atol=1e-4):
            C = newC
            break
        C = newC
    assign = np.empty(len(X), np.int64)
    for s in range(0, len(X), 200000):
        assign[s:s + 200000] = np.argmin(((X[s:s + 200000, None, :] - C[None]) ** 2).sum(2), 1)
    share = np.bincount(assign, minlength=k) / len(X)
    C = np.array([X[assign == j].mean(0) if share[j] > 0 else C[j] for j in range(k)])
    return C, share


def measure(path: str) -> dict:
    pr = probe(path)
    W, H, dur = pr["width"], pr["height"], pr["duration"]
    times = [dur * (i + 0.5) / N_FRAMES for i in range(N_FRAMES)]
    size = analysis_size(W, H, 360)
    frames = frames_at_times(path, times, size, gray=False, fps=pr["fps"])

    small = [cv2.resize(f, analysis_size(W, H, 120), interpolation=cv2.INTER_AREA) for f in frames]
    X = srgb_to_lab(np.concatenate([s.reshape(-1, 3) for s in small]))
    C, share = kmeans_lab(X, K, SEED)
    order = sorted(range(K), key=lambda j: (-round(float(share[j]), 6), tuple(np.round(C[j], 3))))
    palette = [{"hex": lab_to_hex(C[j]), "lab": [float(v) for v in C[j]], "share": float(share[j])}
               for j in order if share[j] > 0]

    lumas, dens, sharp, grain, margins_f = [], [], [], [], []

    def depth(profile):
        idx = np.nonzero(profile > 0.03)[0]
        return (idx[0] / len(profile)) if len(idx) else 0.5
    for f in frames:
        g = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY)
        y = 0.2126 * f[..., 0] + 0.7152 * f[..., 1] + 0.0722 * f[..., 2]
        lumas.append(y.ravel())
        e = cv2.Canny(g, 60, 160)
        dens.append(float((e > 0).mean()))
        lap = cv2.Laplacian(g, cv2.CV_64F)
        sharp.append(float(lap.var()))
        gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
        gm = np.hypot(gx, gy)
        flat = gm < 8
        resid = g.astype(np.float32) - cv2.GaussianBlur(g, (5, 5), 0).astype(np.float32)
        if flat.sum() > 500:
            r = resid[flat]
            r = r[np.abs(r) <= np.percentile(np.abs(r), 99)]
            grain.append(float(np.sqrt(np.mean(r * r))))
        c = cv2.dilate((gm > 40).astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        margins_f.append({"top": depth(c.mean(1)), "bottom": depth(c.mean(1)[::-1]),
                          "left": depth(c.mean(0)), "right": depth(c.mean(0)[::-1])})
    hist, _ = np.histogram(np.concatenate(lumas), bins=16, range=(0, 256))
    hist = hist / hist.sum()

    margins = {k: float(np.median([m[k] for m in margins_f])) for k in ("top", "right", "bottom", "left")}

    from math import gcd
    g_ = gcd(W, H)
    return {
        "palette": palette,
        "luma_hist": hist.tolist(),
        "margins": margins,
        "density": float(np.mean(dens)),
        "sharpness": float(np.median(sharp)),
        "grain": float(np.median(grain)) if grain else None,
        "aspect": W / H,
        "aspect_label": f"{W // g_}:{H // g_}",
        "sample_times": times,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("--out")
    a = ap.parse_args()
    emit(measure(a.video), a.out)


if __name__ == "__main__":
    main()
