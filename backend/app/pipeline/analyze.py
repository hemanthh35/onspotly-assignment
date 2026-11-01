"""Per-video analysis, done once per asset and cached.

Produces:
- metadata (ffprobe), scenes (PySceneDetect)
- quality signals sampled at QUALITY_FPS: sharpness, brightness, stability
- CLIP image embeddings sampled at CLIP_FPS
- speech transcript with word timestamps
Heavy arrays go to <cache>/analysis/<asset_id>.npz; small JSON goes to Asset.analysis.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image

from app.core.config import FFPROBE, settings

Progress = Callable[[float, str], None]


def cache_path(asset_id: str) -> Path:
    p = settings.cache_dir / "analysis"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{asset_id}.npz"


def probe(path: Path) -> dict:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    info = json.loads(out)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if v is None:
        raise ValueError("no video stream")
    num, den = (v.get("avg_frame_rate") or "30/1").split("/")
    return {
        "duration": float(info["format"].get("duration") or v.get("duration") or 0),
        "width": int(v["width"]), "height": int(v["height"]),
        "fps": round(float(num) / float(den or 1), 3) if float(den or 1) else 30.0,
        "has_audio": any(s["codec_type"] == "audio" for s in info["streams"]),
    }


def detect_scenes(path: Path, duration: float) -> list[list[float]]:
    from scenedetect import AdaptiveDetector, detect

    scenes = [[round(a.seconds, 3), round(b.seconds, 3)] for a, b in detect(str(path), AdaptiveDetector())]
    return scenes or [[0.0, round(duration, 3)]]


# ---------------------------------------------------------------- quality signals
def _sharpness_score(lap_var: float) -> float:
    # Laplacian variance on a 320px-wide grey frame: ~15 is very soft, >=250 crisp.
    return float(np.clip((np.log10(max(lap_var, 1.0)) - np.log10(15)) / (np.log10(250) - np.log10(15)), 0, 1))


def _brightness_score(mean: float) -> float:
    if mean < 0.30:
        return float(np.clip((mean - 0.06) / 0.24, 0, 1))
    if mean > 0.80:
        return float(np.clip(1 - (mean - 0.80) / 0.2, 0, 1))
    return 1.0


def _scan_frames(path: Path, duration: float, progress: Progress) -> dict:
    """One sequential decode pass: quality at QUALITY_FPS, CLIP frames at CLIP_FPS."""
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    q_step = max(1, round(fps / settings.quality_fps))
    c_step = max(1, round(fps / settings.clip_fps))
    t_q, sharp, bright, shift = [], [], [], []
    t_c, clip_frames = [], []
    prev_small = None
    idx = 0
    total = max(1, int(duration * fps))
    while True:
        ok = cap.grab()
        if not ok:
            break
        need_q, need_c = idx % q_step == 0, idx % c_step == 0
        if need_q or need_c:
            ok, frame = cap.retrieve()
            if not ok:
                break
            t = idx / fps
            if need_q:
                h, w = frame.shape[:2]
                grey = cv2.cvtColor(cv2.resize(frame, (320, int(320 * h / w))), cv2.COLOR_BGR2GRAY)
                sharp.append(cv2.Laplacian(grey, cv2.CV_64F).var())
                bright.append(grey.mean() / 255.0)
                small = np.float32(cv2.resize(grey, (160, int(160 * h / w))))
                if prev_small is not None:
                    (dx, dy), _ = cv2.phaseCorrelate(prev_small, small)
                    shift.append((dx, dy))
                else:
                    shift.append((0.0, 0.0))
                prev_small = small
                t_q.append(t)
            if need_c:
                h, w = frame.shape[:2]
                scale = 224 / min(h, w)  # CLIP input size; keeps memory small
                rgb = cv2.cvtColor(cv2.resize(frame, (round(w * scale), round(h * scale)),
                                              interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
                clip_frames.append(Image.fromarray(rgb))
                t_c.append(t)
        idx += 1
        if idx % 300 == 0:
            progress(min(0.35, 0.35 * idx / total), "Reading frames")
    cap.release()

    shift_a = np.array(shift or [(0, 0)], dtype=np.float32)
    # Shake = frame-to-frame change in camera motion (smooth pans are fine, jitter is not).
    jerk = np.linalg.norm(np.diff(shift_a, axis=0, prepend=shift_a[:1]), axis=1)
    jerk = np.convolve(jerk, np.ones(3) / 3, mode="same")
    stab = np.exp(-jerk / 3.5)
    return {
        "t_q": np.array(t_q, np.float32),
        "sharpness": np.array([_sharpness_score(v) for v in sharp], np.float32),
        "brightness": np.array([_brightness_score(v) for v in bright], np.float32),
        "brightness_raw": np.array(bright, np.float32),
        "stability": stab.astype(np.float32),
        "t_c": np.array(t_c, np.float32),
        "frames": clip_frames,
    }


def overall_quality(sharp: float, bright: float, stab: float) -> float:
    return round(0.45 * sharp + 0.35 * bright + 0.20 * stab, 3)


def analyze_video(asset_id: str, path: Path, progress: Progress, with_speech: bool = True) -> dict:
    """Run the full analysis for one file. Returns the JSON summary to store on the Asset."""
    from app.providers import speech
    from app.providers.vision import get_clip

    meta = probe(path)
    progress(0.02, "Detecting scenes")
    scenes = detect_scenes(path, meta["duration"])
    progress(0.08, "Scoring quality")
    scan = _scan_frames(path, meta["duration"], progress)

    progress(0.4, "Embedding frames with CLIP")
    clip = get_clip()
    emb = clip.encode_images(scan.pop("frames"))
    progress(0.75, "Transcribing speech")
    transcript = {"language": None, "segments": []}
    if with_speech and meta["has_audio"]:
        transcript = speech.transcribe(path)

    np.savez_compressed(
        cache_path(asset_id), emb=emb.astype(np.float16),
        **{k: v for k, v in scan.items()},
    )
    q = scan
    scene_summ = []
    for a, b in scenes:
        m = (q["t_q"] >= a) & (q["t_q"] < b)
        if not m.any():
            m = np.ones_like(q["t_q"], bool)
        s, br, st = float(q["sharpness"][m].mean()), float(q["brightness"][m].mean()), float(q["stability"][m].mean())
        scene_summ.append({"start": a, "end": b, "sharpness": round(s, 3), "brightness": round(br, 3),
                           "stability": round(st, 3), "overall": overall_quality(s, br, st)})
    progress(1.0, "Analysis complete")
    return {**meta, "scenes": scene_summ, "transcript": transcript,
            "models": {"vision": clip.name, "speech": speech.model_name() if with_speech else None}}


def load_arrays(asset_id: str) -> dict | None:
    p = cache_path(asset_id)
    if not p.exists():
        return None
    d = np.load(p)
    return {k: d[k] for k in d.files}
