"""OCR backends for media text extraction."""

from typing import Dict, List, Tuple, Optional
import os
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

try:
    from paddleocr import PaddleOCR
except ImportError:  # pragma: no cover - optional dependency
    PaddleOCR = None

try:
    import pytesseract
except ImportError:  # pragma: no cover - optional dependency
    pytesseract = None


class OCRService:
    """Extract text from sampled frames using PaddleOCR or Tesseract."""

    def __init__(self, sample_limit: int = 6, backend_order: Optional[List[str]] = None):
        self.sample_limit = sample_limit
        self.backend_order = backend_order or ["paddle", "tesseract"]
        self._paddle_instance = None

    def _select_frames(self, frames: List[np.ndarray]) -> List[Tuple[int, np.ndarray]]:
        if not frames:
            return []
        if len(frames) <= self.sample_limit:
            return list(enumerate(frames))

        indices = np.linspace(0, len(frames) - 1, self.sample_limit, dtype=int)
        return [(int(idx), frames[int(idx)]) for idx in indices]

    def _tesseract_available(self) -> bool:
        if pytesseract is None:
            return False

        if shutil.which("tesseract"):
            return True

        candidates = [
            os.environ.get("TESSERACT_PATH"),
            os.environ.get("TESSERACT_CMD"),
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract",
        ]

        for candidate in candidates:
            if candidate and Path(candidate).exists():
                pytesseract.pytesseract.tesseract_cmd = candidate
                return True

        return False

    def _get_available_backend(self) -> Optional[str]:
        for backend in self.backend_order:
            if backend == "paddle" and PaddleOCR is not None:
                return backend
            if backend == "tesseract" and self._tesseract_available():
                return backend
        return None

    def _get_paddle(self):
        if self._paddle_instance is None:
            self._paddle_instance = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        return self._paddle_instance

    def _extract_with_paddle(self, image: Image.Image) -> str:
        ocr = self._get_paddle()
        result = ocr.ocr(np.array(image), cls=True)
        lines = []
        for page in result or []:
            for item in page or []:
                if len(item) > 1 and item[1]:
                    lines.append(item[1][0])
        return " ".join(lines).strip()

    def _extract_with_tesseract(self, image: Image.Image) -> str:
        return pytesseract.image_to_string(image).strip()

    def extract_text(self, frames: List[np.ndarray]) -> Dict:
        backend = self._get_available_backend()
        if backend is None:
            return {
                "enabled": True,
                "available": False,
                "backend": None,
                "sampled_frames": 0,
                "extracted_text": [],
                "reason": "No OCR backend installed",
            }

        extracted_text = []
        sampled_frames = self._select_frames(frames)
        extractor = self._extract_with_paddle if backend == "paddle" else self._extract_with_tesseract

        for frame_idx, frame in sampled_frames:
            try:
                text = extractor(Image.fromarray(frame.astype("uint8")))
            except Exception as exc:
                extracted_text.append({"frame_idx": frame_idx, "text": "", "error": str(exc)})
                continue

            if text:
                extracted_text.append({"frame_idx": frame_idx, "text": text[:500]})

        return {
            "enabled": True,
            "available": True,
            "backend": backend,
            "sampled_frames": len(sampled_frames),
            "extracted_text": extracted_text,
        }
