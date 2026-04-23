"""ONNX-based vehicle detector supporting YOLOv8 and RT-DETR models.

Auto-detects model format from output tensor shape:
  YOLOv8:  [1, 84, 8400]  — transposed to [8400, 84]
  RT-DETR: [1, N,  6]     — columns: cx, cy, w, h, score, class_id
"""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# COCO class indices → vehicle type string
_VEHICLE_CLASSES: Dict[int, str] = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float = 0.45) -> List[int]:
    """Greedy NMS. boxes: [N,4] (x1,y1,x2,y2), scores: [N]."""
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.maximum(x2 - x1, 0) * np.maximum(y2 - y1, 0)
    order = scores.argsort()[::-1]
    keep: List[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        union = areas[i] + areas[order[1:]] - inter
        iou = np.where(union > 0, inter / union, 0.0)
        order = order[np.where(iou <= iou_threshold)[0] + 1]
    return keep


class OnnxDetector:
    """Wraps an ONNX vehicle detector (YOLOv8 or RT-DETR).

    Parameters
    ----------
    model_path:
        Path to the .onnx model file.
    confidence_threshold:
        Minimum detection confidence (default 0.3).
    nms_threshold:
        IoU threshold for NMS (default 0.45).
    device:
        ``"auto"`` tries CUDA then CPU.  ``"cpu"`` forces CPU.
    """

    def __init__(
        self,
        model_path: str,
        confidence_threshold: float = 0.3,
        nms_threshold: float = 0.45,
        device: str = "auto",
    ) -> None:
        import onnxruntime as ort

        providers = self._providers(device)
        logger.info("Loading detector %s  providers=%s", model_path, providers)
        self._sess = ort.InferenceSession(model_path, providers=providers)
        self._input_name: str = self._sess.get_inputs()[0].name
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold

        # If the model was exported with a fixed batch size > 1 (e.g. b16),
        # we need to tile the single frame to fill the batch, then take [0].
        in_shape = self._sess.get_inputs()[0].shape
        b = in_shape[0]
        self._fixed_batch: int = int(b) if isinstance(b, int) and b > 1 else 1

        out_shape = self._sess.get_outputs()[0].shape
        # Determine model format from output tensor shape:
        #   YOLOv8 / YOLOv11 / YOLOv11-seg: [1, F, N]  where N >> F
        #     e.g. [1, 84, 8400]  or  [1, 116, 8400] (seg — extra mask cols)
        #   RT-DETR:                  [1, N, 6]  where d2=6
        if len(out_shape) == 3:
            d1, d2 = out_shape[1], out_shape[2]
            if isinstance(d2, int) and d2 == 6:
                self._fmt = "rtdetr"
            elif isinstance(d1, int) and isinstance(d2, int) and d2 > d1:
                # proposals dim (8400) > features dim (84 or 116) → yolo
                self._fmt = "yolov8"
            else:
                self._fmt = "rtdetr"
        else:
            self._fmt = "yolov8"

        # For RT-DETR models, probe the coordinate format once with a dummy pass.
        # Different exports use different conventions:
        #   'xyxy_pixel'   — x1,y1,x2,y2 in 640px space  (dynamic export)
        #   'cxcywh_pixel' — cx,cy,w,h  in 640px space
        #   'cxcywh_norm'  — cx,cy,w,h  normalised [0,1]
        self._rtdetr_coord_fmt: str = "cxcywh_pixel"
        if self._fmt == "rtdetr":
            self._rtdetr_coord_fmt = self._probe_rtdetr_format()

        if self._fixed_batch > 1:
            logger.warning(
                "Model has fixed batch=%d — each inference tiles the frame %d times. "
                "Use a dynamic-batch model (e.g. rtdetr-l-dynamic.onnx) for full speed.",
                self._fixed_batch, self._fixed_batch,
            )
        logger.info(
            "Model format: %s  coord_fmt: %s  output_shape=%s  batch=%d",
            self._fmt, self._rtdetr_coord_fmt, out_shape, self._fixed_batch,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray) -> List[Dict]:
        """Run detection on a BGR frame.

        Returns a list of dicts with keys:
          bbox (x1,y1,x2,y2 ints), confidence, vehicle_type, class_id
        """
        h, w = frame.shape[:2]
        inp = self._preprocess(frame)
        if self._fixed_batch > 1:
            inp = np.tile(inp, (self._fixed_batch, 1, 1, 1))
        raw = self._sess.run(None, {self._input_name: inp})[0]
        if self._fmt == "yolov8":
            return self._post_yolov8(raw, w, h)
        return self._post_rtdetr(raw, w, h)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _probe_rtdetr_format(self) -> str:
        """Run a dummy inference to determine RT-DETR coordinate convention.

        Returns one of:
          'xyxy_pixel'   — col0-3 are x1,y1,x2,y2 in 640-px space
          'cxcywh_pixel' — col0-3 are cx,cy,w,h   in 640-px space
          'cxcywh_norm'  — col0-3 are cx,cy,w,h   normalised [0,1]
        """
        try:
            dummy = np.random.randn(1, 3, 640, 640).astype(np.float32)
            if self._fixed_batch > 1:
                dummy = np.tile(dummy, (self._fixed_batch, 1, 1, 1))
            r = self._sess.run(None, {self._input_name: dummy})[0][0]  # [N, 6]
            all_vals = r[:, :4]
            max_val = float(np.abs(all_vals).max())
            if max_val <= 1.5:
                return "cxcywh_norm"
            # In pixel space: for xyxy, col2 (x2) > col0 (x1) in the vast majority
            # of rows. For cxcywh, col0 is cx (~320) and col2 is w (~variable) so
            # no consistent ordering.
            frac = float((r[:, 2] > r[:, 0]).mean())
            fmt = "xyxy_pixel" if frac > 0.65 else "cxcywh_pixel"
            logger.info("RT-DETR coord probe: max_val=%.1f  xyxy_frac=%.2f  → %s", max_val, frac, fmt)
            return fmt
        except Exception as exc:
            logger.warning("RT-DETR coord probe failed (%s), defaulting to cxcywh_pixel", exc)
            return "cxcywh_pixel"

    @staticmethod
    def _providers(device: str) -> List[str]:
        """Build an ORT provider priority list.

        Priority order
        --------------
        ``cuda``  — NVIDIA CUDA  (requires ``onnxruntime-gpu``)
        ``dml``   — DirectML, works on **AMD Radeon, Intel, NVIDIA** via DX12
                    (requires ``onnxruntime-directml`` on Windows)
        ``cpu``   — always available fallback

        With ``device="auto"`` the first available GPU path wins.
        """
        import onnxruntime as ort
        avail = ort.get_available_providers()

        if device == "cpu":
            return ["CPUExecutionProvider"]

        if device == "cuda":
            if "CUDAExecutionProvider" in avail:
                return ["CUDAExecutionProvider", "CPUExecutionProvider"]
            logger.warning("CUDAExecutionProvider not available; falling back to CPU")
            return ["CPUExecutionProvider"]

        if device == "dml":
            if "DmlExecutionProvider" in avail:
                return ["DmlExecutionProvider", "CPUExecutionProvider"]
            logger.warning("DmlExecutionProvider not available; falling back to CPU. "
                           "Install onnxruntime-directml for AMD/Intel/NVIDIA DX12 acceleration.")
            return ["CPUExecutionProvider"]

        # device == "auto": prefer CUDA > DML > CPU
        if "CUDAExecutionProvider" in avail:
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        if "DmlExecutionProvider" in avail:
            return ["DmlExecutionProvider", "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    @staticmethod
    def _preprocess(frame: np.ndarray) -> np.ndarray:
        img = cv2.resize(frame, (640, 640))
        img = img[:, :, ::-1].astype(np.float32) / 255.0  # BGR→RGB, [0,1]
        return np.transpose(img, (2, 0, 1))[np.newaxis]   # NCHW

    def _post_yolov8(self, raw: np.ndarray, orig_w: int, orig_h: int) -> List[Dict]:
        preds = raw[0].T            # [8400, 84+]  (seg models have extra cols)
        boxes = preds[:, :4]        # cx, cy, w, h  (640px space)
        cls_scores = preds[:, 4:84] # [8400, 80]  — clamp to COCO 80 classes

        class_ids = np.argmax(cls_scores, axis=1)
        scores = cls_scores[np.arange(len(class_ids)), class_ids]

        veh_mask = np.isin(class_ids, list(_VEHICLE_CLASSES.keys()))
        conf_mask = scores >= self.confidence_threshold
        mask = veh_mask & conf_mask
        if not mask.any():
            return []

        fb = boxes[mask]
        fs = scores[mask]
        fc = class_ids[mask]

        sx, sy = orig_w / 640, orig_h / 640
        x1 = (fb[:, 0] - fb[:, 2] / 2) * sx
        y1 = (fb[:, 1] - fb[:, 3] / 2) * sy
        x2 = (fb[:, 0] + fb[:, 2] / 2) * sx
        y2 = (fb[:, 1] + fb[:, 3] / 2) * sy
        xyxy = np.stack([x1, y1, x2, y2], axis=1)

        keep = _nms(xyxy, fs, self.nms_threshold)
        return [
            {
                "bbox": (int(xyxy[i, 0]), int(xyxy[i, 1]), int(xyxy[i, 2]), int(xyxy[i, 3])),
                "confidence": float(fs[i]),
                "class_id": int(fc[i]),
                "vehicle_type": _VEHICLE_CLASSES[int(fc[i])],
            }
            for i in keep
        ]

    def _post_rtdetr(self, raw: np.ndarray, orig_w: int, orig_h: int) -> List[Dict]:
        preds = raw[0]              # [N, 6]
        scores = preds[:, 4]
        class_ids = preds[:, 5].astype(int)

        veh_mask = np.isin(class_ids, list(_VEHICLE_CLASSES.keys()))
        conf_mask = scores >= self.confidence_threshold
        mask = veh_mask & conf_mask
        if not mask.any():
            return []

        fb = preds[mask, :4]
        fs = scores[mask]
        fc = class_ids[mask]

        fmt = self._rtdetr_coord_fmt
        sx, sy = orig_w / 640, orig_h / 640

        if fmt == "xyxy_pixel":
            # col0-3 = x1, y1, x2, y2 in 640-px space
            x1, y1, x2, y2 = fb[:, 0] * sx, fb[:, 1] * sy, fb[:, 2] * sx, fb[:, 3] * sy
        elif fmt == "cxcywh_norm":
            # col0-3 = cx, cy, w, h  normalised [0,1]
            cx, cy, wb, hb = fb[:, 0] * orig_w, fb[:, 1] * orig_h, fb[:, 2] * orig_w, fb[:, 3] * orig_h
            x1, y1, x2, y2 = cx - wb / 2, cy - hb / 2, cx + wb / 2, cy + hb / 2
        else:
            # cxcywh_pixel: col0-3 = cx, cy, w, h  in 640-px space
            cx, cy, wb, hb = fb[:, 0] * sx, fb[:, 1] * sy, fb[:, 2] * sx, fb[:, 3] * sy
            x1, y1, x2, y2 = cx - wb / 2, cy - hb / 2, cx + wb / 2, cy + hb / 2

        xyxy = np.stack([x1, y1, x2, y2], axis=1)

        keep = _nms(xyxy, fs, self.nms_threshold)
        return [
            {
                "bbox": (int(xyxy[i, 0]), int(xyxy[i, 1]), int(xyxy[i, 2]), int(xyxy[i, 3])),
                "confidence": float(fs[i]),
                "class_id": int(fc[i]),
                "vehicle_type": _VEHICLE_CLASSES.get(int(fc[i]), "car"),
            }
            for i in keep
        ]
