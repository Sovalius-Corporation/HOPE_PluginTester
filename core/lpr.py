"""Optional ONNX-based License Plate Recognition.

Two-stage pipeline:
  1. Plate detector  (License_platebest.onnx or similar YOLOv8-style model)
  2. Plate OCR       (LPRNet / PaddleOCR rec model)

Load only when ``lpr_enabled=True`` in the scenario.  If the OCR model is
omitted only detection is performed (plate text returned as ``"??"``).
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Character set used by LPRNet / PaddleOCR-rec  (matches python_lpr.py)
_LPR_CHARS = "0123456789abcdefghijklmnpqrstuvwxyz"
_LPR_BLANK = len(_LPR_CHARS)  # CTC blank token index


def _ctc_greedy_decode(indices, confidences=None) -> Tuple[str, float]:
    """Collapse CTC duplicates and blanks, return (text, avg_confidence)."""
    prev = -1
    chars: List[str] = []
    confs: List[float] = []
    for i, idx in enumerate(indices):
        idx = int(idx)
        if idx == prev:
            continue
        prev = idx
        if idx < 0 or idx >= len(_LPR_CHARS):
            continue  # blank or out-of-range
        chars.append(_LPR_CHARS[idx])
        if confidences is not None and i < len(confidences):
            confs.append(float(confidences[i]))
    text = "".join(chars).upper()
    avg_conf = sum(confs) / len(confs) if confs else 0.8
    return text, avg_conf


class OnnxLPR:
    """Runs plate detection + OCR entirely via ONNX Runtime."""

    def __init__(
        self,
        plate_model_path: str,
        ocr_model_path: Optional[str] = None,
        confidence_threshold: float = 0.45,
        device: str = "auto",
    ) -> None:
        import onnxruntime as ort

        providers = self._providers(device)
        logger.info("LPR plate detector: %s", plate_model_path)
        self._plate_sess = ort.InferenceSession(plate_model_path, providers=providers)
        self._plate_input: str = self._plate_sess.get_inputs()[0].name
        self.confidence_threshold = confidence_threshold

        self._ocr_sess = None
        self._ocr_input: str = ""
        if ocr_model_path:
            logger.info("LPR OCR model: %s", ocr_model_path)
            self._ocr_sess = ort.InferenceSession(ocr_model_path, providers=providers)
            self._ocr_input = self._ocr_sess.get_inputs()[0].name

    # ------------------------------------------------------------------

    def process(
        self,
        frame: np.ndarray,
        vehicle_bbox: Tuple[int, int, int, int],
    ) -> Tuple[Optional[str], float]:
        """Return ``(plate_text, confidence)`` or ``(None, 0.0)`` if not found."""
        x1, y1, x2, y2 = vehicle_bbox
        h, w = frame.shape[:2]
        py = int((y2 - y1) * 0.1)
        px = int((x2 - x1) * 0.1)
        crop = frame[max(0, y1 - py): min(h, y2 + py),
                     max(0, x1 - px): min(w, x2 + px)]
        if crop.size == 0:
            return None, 0.0

        plate_crop = self._detect_plate(crop)
        if plate_crop is None:
            return None, 0.0

        if self._ocr_sess is None:
            return "??", 0.5

        return self._ocr_plate(plate_crop)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _providers(device: str) -> List[str]:
        import onnxruntime as ort
        avail = ort.get_available_providers()
        if device != "cpu" and "CUDAExecutionProvider" in avail:
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    def _detect_plate(self, vehicle_crop: np.ndarray) -> Optional[np.ndarray]:
        try:
            inp = cv2.resize(vehicle_crop, (640, 640))
            inp = inp[:, :, ::-1].astype(np.float32) / 255.0
            inp = np.transpose(inp, (2, 0, 1))[np.newaxis]
            out = self._plate_sess.run(None, {self._plate_input: inp})[0]

            # Support YOLOv8 output [1, 5, N] or [1, N, 5]
            preds = out[0]
            if preds.shape[0] < preds.shape[-1]:   # [5, N] → transpose
                preds = preds.T
            # columns: cx, cy, w, h, score
            if preds.shape[1] < 5:
                return None
            scores = preds[:, 4]
            best = int(scores.argmax())
            if scores[best] < self.confidence_threshold:
                return None

            h, w = vehicle_crop.shape[:2]
            sx, sy = w / 640, h / 640
            cx, cy, bw, bh = preds[best, :4]
            x1 = int(max(0, (cx - bw / 2) * sx))
            y1 = int(max(0, (cy - bh / 2) * sy))
            x2 = int(min(w, (cx + bw / 2) * sx))
            y2 = int(min(h, (cy + bh / 2) * sy))
            if x2 <= x1 or y2 <= y1:
                return None
            return vehicle_crop[y1:y2, x1:x2]
        except Exception as exc:
            logger.debug("Plate detect failed: %s", exc)
            return None

    def _ocr_plate(self, plate_crop: np.ndarray) -> Tuple[Optional[str], float]:
        try:
            ocr_in = cv2.resize(plate_crop, (94, 24))
            ocr_in = ocr_in[:, :, ::-1].astype(np.float32) / 255.0
            ocr_in = np.transpose(ocr_in, (2, 0, 1))[np.newaxis]
            out = self._ocr_sess.run(None, {self._ocr_input: ocr_in})[0]
            # out: [1, seq_len, num_chars]
            if out.ndim == 3:
                indices = out[0].argmax(axis=-1)
                confs = out[0].max(axis=-1)
            else:
                indices = out.argmax(axis=-1)
                confs = None
            text, conf = _ctc_greedy_decode(indices, confs)
            return (text, conf) if len(text) >= 2 else (None, 0.0)
        except Exception as exc:
            logger.debug("OCR failed: %s", exc)
            return None, 0.0
