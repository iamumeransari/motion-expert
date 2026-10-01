"""Shared helpers for the measure scripts: probing, deterministic frame decoding,
rounding and JSON output. Every script decodes through ffmpeg into raw frames at a
fixed analysis size so results do not depend on the source resolution or on the
OpenCV backend, and so the same file always yields the same bytes."""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(path: str | Path) -> dict:
    """Duration, fps, size, codecs and has_audio from ffprobe."""
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    info = json.loads(out)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    dur = float(info.get("format", {}).get("duration") or 0.0)
    res = {
        "path": str(Path(path).resolve()),
        "duration": dur,
        "has_video": v is not None,
        "has_audio": a is not None,
        "video_codec": v.get("codec_name") if v else None,
        "audio_codec": a.get("codec_name") if a else None,
        "fps": None, "width": None, "height": None,
    }
    if v:
        rate = v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1"
        try:
            fps = float(Fraction(rate))
        except (ZeroDivisionError, ValueError):
            fps = 0.0
        if not fps:
            fps = float(Fraction(v.get("r_frame_rate", "30/1")))
        w, h = int(v["width"]), int(v["height"])
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(sd["rotation"])
        if abs(rot) in (90, 270):
            w, h = h, w
        res.update(fps=fps, width=w, height=h)
    return res


def analysis_size(w: int, h: int, long_side: int) -> tuple[int, int]:
    """Scale so the long side equals long_side, both dims even."""
    s = long_side / max(w, h)
    aw = max(2, int(round(w * s / 2)) * 2)
    ah = max(2, int(round(h * s / 2)) * 2)
    return aw, ah


def iter_frames(path, fps: float, size: tuple[int, int], gray: bool = True, start: float | None = None,
                end: float | None = None):
    """Yield (index, frame) decoded by ffmpeg at a constant rate `fps` (forces CFR so
    frame index * 1/fps is the timestamp) and scaled to `size` with bicubic."""
    w, h = size
    pix = "gray" if gray else "rgb24"
    ch = 1 if gray else 3
    cmd = [FFMPEG, "-v", "error", "-nostdin"]
    if start is not None:
        cmd += ["-ss", f"{max(0.0, start):.6f}"]
    cmd += ["-i", str(path)]
    if end is not None:
        cmd += ["-t", f"{max(0.0, end - (start or 0.0)):.6f}"]
    cmd += ["-an", "-vf", f"fps={fps:.6f},scale={w}:{h}:flags=bicubic", "-pix_fmt", pix,
            "-f", "rawvideo", "-"]
    # stderr is dropped because closing the pipe early (we stop at the last frame we
    # need) makes ffmpeg report a broken pipe; a decode failure shows up as no frames.
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = w * h * ch
    i = 0
    try:
        while True:
            buf = proc.stdout.read(n)
            if len(buf) < n:
                break
            arr = np.frombuffer(buf, np.uint8)
            yield i, (arr.reshape(h, w) if gray else arr.reshape(h, w, 3))
            i += 1
    finally:
        proc.stdout.close()
        proc.wait()


def load_frames(path, fps, size, gray=True, start=None, end=None) -> np.ndarray:
    frames = [f.copy() for _, f in iter_frames(path, fps, size, gray, start, end)]
    if not frames:
        raise RuntimeError(f"no frames decoded from {path}")
    return np.stack(frames)


def frames_at_times(path, times, size, gray=False, fps=None):
    """Return frames nearest to each timestamp (sequential decode, one pass)."""
    if fps is None:
        fps = probe(path)["fps"]
    want = {}
    for t in times:
        want.setdefault(int(math.floor(max(0.0, t) * fps + 1e-6)), []).append(t)
    out = {}
    last = None
    maxi = max(want) if want else -1
    for i, f in iter_frames(path, fps, size, gray):
        last = f
        if i in want:
            for t in want[i]:
                out[t] = f.copy()
        if i >= maxi:
            break
    for t in times:  # timestamps past the end get the last frame
        if t not in out and last is not None:
            out[t] = last.copy()
    return [out[t] for t in times]


def r4(x):
    """Round floats to 4 dp recursively, normalise numpy types, -0.0 -> 0.0."""
    if isinstance(x, dict):
        return {str(k): r4(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [r4(v) for v in x]
    if isinstance(x, (np.floating, float)):
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        v = round(v, 4)
        return 0.0 if v == 0 else v
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.ndarray):
        return r4(x.tolist())
    return x


def dumps(obj) -> str:
    return json.dumps(r4(obj), sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def emit(obj, out: str | None):
    s = dumps(obj)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(s)
    else:
        sys.stdout.write(s)


def is_audio_only(path) -> bool:
    if Path(path).suffix.lower() in AUDIO_EXTS:
        return True
    return not probe(path)["has_video"]


def pct(a, q):
    a = np.asarray(a, dtype=float)
    return float(np.percentile(a, q)) if a.size else None
