"""Image-text embedding model (OpenCLIP). Loaded lazily, once per process."""
from __future__ import annotations

import threading

import numpy as np

from app.core.config import settings


class ClipModel:
    def __init__(self, model_name: str, pretrained: str):
        import open_clip
        import torch

        torch.set_num_threads(max(1, (torch.get_num_threads() or 4)))
        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained)
        self.model.eval().to(self.device)
        self.tokenizer = open_clip.get_tokenizer(model_name)
        gpu = f", {torch.cuda.get_device_name(0)}" if self.device == "cuda" else ""
        self.name = f"OpenCLIP {model_name} ({pretrained}, {self.device}{gpu})"

    def encode_images(self, images, batch_size: int = 32) -> np.ndarray:
        """images: list of PIL images -> (N, D) L2-normalised float32."""
        out = []
        with self.torch.no_grad():
            for i in range(0, len(images), batch_size):
                batch = self.torch.stack([self.preprocess(im) for im in images[i:i + batch_size]]).to(self.device)
                feats = self.model.encode_image(batch)
                out.append(self.torch.nn.functional.normalize(feats, dim=-1).cpu().numpy())
        return np.concatenate(out) if out else np.zeros((0, 512), np.float32)

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        with self.torch.no_grad():
            feats = self.model.encode_text(self.tokenizer(texts).to(self.device))
            return self.torch.nn.functional.normalize(feats, dim=-1).cpu().numpy()


_lock = threading.Lock()
_model: ClipModel | None = None


def get_clip() -> ClipModel:
    global _model
    with _lock:
        if _model is None:
            _model = ClipModel(settings.clip_model, settings.clip_pretrained)
        return _model
