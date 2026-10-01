"""Run every measure on one video and write a single deterministic fingerprint.json.

  fingerprint.py <video> --out fingerprint.json [--bands style-bands.json]
                 [--model ggml-medium.en.bin] [--no-delivery] [--no-sound]
                 [--sound-device cpu|mps|auto]

When toolkit/measure/sound.py exists it runs after motion, with the moves (and their
start / peak / land keyframes) and cuts written to fingerprint-moves.json beside the
output as its anchors; its result goes under "sound", and its clean clips land in
clips/ beside the output. Without sound.py, "sound" is null.

Top-level keys: version, source, timing, motion, look, delivery, sound, tolerance.
The tolerance block turns bands.json (plus sound-bands.json when present, plus any
--bands override) into absolute lo/hi bounds around this source's own values: the
"same hand" envelope a new piece about a different subject must land in.

Output is deterministic: fixed seeds, floats rounded to 4 dp, keys sorted. The same
file always writes the same bytes.
"""
from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cuts as cuts_mod  # noqa: E402
import delivery as delivery_mod  # noqa: E402
import look as look_mod  # noqa: E402
import motion as motion_mod  # noqa: E402
from common import dumps, probe, sha256  # noqa: E402


def get(d, path):
    cur = d
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def load_bands(extra: str | None) -> dict:
    def read(p):
        data = json.loads(Path(p).read_text())
        return data.get("bands", data) if isinstance(data, dict) else {}
    bands = dict(read(HERE / "bands.json"))
    if (HERE / "sound-bands.json").exists():
        bands.update({k: v for k, v in read(HERE / "sound-bands.json").items() if isinstance(v, dict)})
    if extra:
        bands.update({k: v for k, v in read(extra).items() if isinstance(v, dict)})
    return bands


def tolerance(fp: dict, bands: dict) -> dict:
    out = {}
    for path, spec in sorted(bands.items()):
        if not isinstance(spec, dict) or path.startswith(("version", "about")):
            continue
        why = spec.get("why", "")
        if spec.get("fixed") or ("rel" not in spec and "abs" not in spec and ("lo" in spec or "hi" in spec)):
            if path.split(".")[0] in fp and fp.get(path.split(".")[0]) is None:
                continue  # whole layer absent (e.g. no speech)
            out[path] = {"lo": spec.get("lo"), "hi": spec.get("hi"), "kind": "absolute", "why": why}
            continue
        v = get(fp, path)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        if "rel" in spec:
            w = max(abs(v) * float(spec["rel"]), float(spec.get("abs_min", 0.0)))
        else:
            w = float(spec["abs"])
        lo, hi = v - w, v + w
        if spec.get("floor") is not None:
            lo = max(lo, spec["floor"])
        out[path] = {"lo": lo, "hi": hi, "kind": "absolute", "why": why}
    return out


def run_sound(video: str, motion: dict | None, timing: dict | None, delivery: dict | None, src: dict,
              out_dir: Path, device: str = "cpu"):
    """Call toolkit/measure/sound.py when it exists. Its analyse() takes a moves file
    (moves with keyframes, plus cuts as anchors), an output path that decides where
    clean clips are written, a stems cache and a device; cpu is the default because
    Demucs on mps is not bit-reproducible."""
    p = HERE / "sound.py"
    if not p.exists():
        return None, "sound.py not present"
    try:
        spec = importlib.util.spec_from_file_location("sound", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = next((getattr(mod, n) for n in ("analyse", "measure", "analyze", "run")
                   if callable(getattr(mod, n, None))), None)
        if fn is None:
            return None, "sound.py has no analyse() entry point"
        out_dir.mkdir(parents=True, exist_ok=True)
        moves_file = out_dir / "fingerprint-moves.json"
        moves_file.write_text(dumps({"moves": (motion or {}).get("moves", []),
                                     "cuts": (timing or {}).get("cuts", []),
                                     "dissolves": (timing or {}).get("dissolves", [])}))
        avail = {"moves_path": str(moves_file), "out": str(out_dir / "sound.json"),
                 "stems_dir": str(HERE.parent.parent / "work" / "stems"), "device": device, "plot": None,
                 "moves": (motion or {}).get("moves", []), "motion": motion, "timing": timing,
                 "delivery": delivery, "source": src}
        params = inspect.signature(fn).parameters
        takes_kw = any(pp.kind == pp.VAR_KEYWORD for pp in params.values())
        kwargs = {k: v for k, v in avail.items() if (k in params or takes_kw) and k != "video"}
        res = fn(video, **kwargs)
        if isinstance(res, tuple):
            res = res[0]
        if isinstance(res, dict) and set(res) == {"sound"}:
            res = res["sound"]
        return res, None
    except Exception as e:  # never let a sound failure lose the rest of the fingerprint
        return None, f"sound.py failed: {type(e).__name__}: {e}"


def build(video: str, bands_path=None, model=delivery_mod.DEFAULT_MODEL, do_delivery=True, do_sound=True,
          out_dir: Path | None = None, sound_device: str = "cpu") -> dict:
    pr = probe(video)
    notes = []
    src = {"path": pr["path"], "sha256": sha256(video), "duration": pr["duration"], "fps": pr["fps"],
           "width": pr["width"], "height": pr["height"], "has_audio": pr["has_audio"]}
    timing = motion = look = None
    if pr["has_video"]:
        timing = cuts_mod.public(cuts_mod.measure(video))
        motion = motion_mod.measure(video, timing)
        look = look_mod.measure(video)
    else:
        notes.append("no video stream: timing, motion and look are null")
    delivery = None
    if do_delivery:
        delivery, reason = delivery_mod.measure(video, model)
        if delivery is None:
            notes.append(f"delivery null: {reason}")
    else:
        notes.append("delivery skipped (--no-delivery)")
    sound = None
    if do_sound:
        sound, why = run_sound(video, motion, timing, delivery, src, out_dir or Path.cwd(), sound_device)
        if why:
            notes.append(f"sound null: {why}")
    if notes:
        src["notes"] = notes
    fp = {"version": 1, "source": src, "timing": timing, "motion": motion, "look": look,
          "delivery": delivery, "sound": sound}
    # round first so bands are computed from the exact numbers written
    fp = json.loads(dumps(fp))
    fp["tolerance"] = tolerance(fp, load_bands(bands_path))
    return fp


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bands", help="JSON of band overrides, same shape as bands.json")
    ap.add_argument("--model", default=delivery_mod.DEFAULT_MODEL)
    ap.add_argument("--no-delivery", action="store_true")
    ap.add_argument("--no-sound", action="store_true")
    ap.add_argument("--sound-device", default="cpu", choices=["cpu", "mps", "auto"],
                    help="Demucs device for sound.py; cpu keeps the output byte-identical")
    a = ap.parse_args()
    fp = build(a.video, a.bands, a.model, not a.no_delivery, not a.no_sound,
               Path(a.out).resolve().parent, a.sound_device)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(dumps(fp))
    print(a.out)


if __name__ == "__main__":
    main()
