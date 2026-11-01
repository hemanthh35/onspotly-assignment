"""Speech-to-text with word timestamps (faster-whisper, CPU int8)."""
from __future__ import annotations

import threading
from pathlib import Path

from app.core.config import settings

_lock = threading.Lock()
_model = None


def _get():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel

            _model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
        return _model


def model_name() -> str:
    return f"faster-whisper {settings.whisper_model} (int8, CPU)"


def transcribe(path: Path) -> dict:
    """Returns {language, segments: [{start, end, text, confidence, words: [{w, start, end, p}]}]}."""
    segments, info = _get().transcribe(str(path), word_timestamps=True, vad_filter=True)
    out = []
    for s in segments:
        # Drop hallucinated segments on music / ambience.
        if s.no_speech_prob > 0.6 and s.avg_logprob < -0.8:
            continue
        out.append({
            "start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
            "confidence": round(float(2.718281828 ** s.avg_logprob), 3),
            "no_speech_prob": round(s.no_speech_prob, 3),
            "words": [{"w": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2),
                       "p": round(w.probability, 3)} for w in (s.words or [])],
        })
    return {"language": info.language, "language_probability": round(info.language_probability, 3),
            "segments": out}
