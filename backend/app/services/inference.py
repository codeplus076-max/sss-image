"""Inference Service Module.

Provides a unified prediction interface across all registered Side-Scan Sonar
models, normalizing outputs into consistent Pydantic structures with raw and
semantic class labels, bounding boxes, and metadata.
"""

import gc
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import torch
from PIL import Image

from app.core.config import settings
from app.core.model_registry import (
    ModelDefinition,
    get_model_definition,
)
from app.schemas.inference import (
    BoundingBox,
    DetectionResult,
    InferenceResponse,
    TriageClassificationResult,
)
from app.services.model_loader import load_model

logger = logging.getLogger(__name__)

_hf_client = None


def _get_hf_client():
    global _hf_client
    if _hf_client is None:
        try:
            from gradio_client import Client
            token = settings.HF_TOKEN.strip() if settings.HF_TOKEN else None
            try:
                _hf_client = Client(settings.HF_SPACE_ID, token=token)
            except TypeError:
                _hf_client = Client(settings.HF_SPACE_ID, hf_token=token)
            logger.info(f"Connected to remote Hugging Face ZeroGPU engine: {settings.HF_SPACE_ID}")
        except Exception as e:
            logger.warning(f"Could not connect to HF Space {settings.HF_SPACE_ID}: {e}")
            _hf_client = False
    return _hf_client if _hf_client is not False else None


def _normalize_image_input(image: Union[np.ndarray, Image.Image, str, Path]) -> Tuple[Any, int, int]:
    """Inspect and normalize input image, returning (image_for_yolo, width, height)."""
    if isinstance(image, (str, Path)):
        img_path = Path(image)
        if not img_path.exists():
            raise FileNotFoundError(f"Image file not found: {img_path}")
        with Image.open(img_path) as pil_img:
            w, h = pil_img.size
        return str(img_path), w, h

    elif isinstance(image, Image.Image):
        w, h = image.size
        # Convert PIL to RGB numpy array for reliable Ultralytics processing
        return np.array(image.convert("RGB")), w, h

    elif isinstance(image, np.ndarray):
        h, w = image.shape[:2]
        return image, w, h

    else:
        raise ValueError(
            f"Unsupported image type: {type(image)}. Expected numpy array, PIL Image, or file path."
        )


class InferenceService:
    """Unified inference service for Side-Scan Sonar detection models."""

    @staticmethod
    def load_model(name_or_key: str):
        """Pre-load a model into memory."""
        return load_model(name_or_key)

    @staticmethod
    def _try_predict_remote(
        definition: ModelDefinition,
        image: Union[np.ndarray, Image.Image, str, Path],
        confidence: float,
        iou: float,
    ) -> Optional[InferenceResponse]:
        """Attempt GPU-accelerated inference via remote Hugging Face ZeroGPU Space."""
        client = _get_hf_client()
        if not client:
            return None

        temp_path = None
        try:
            from gradio_client import handle_file

            img_for_yolo, img_width, img_height = _normalize_image_input(image)
            if isinstance(image, (str, Path)):
                temp_path = str(image)
                cleanup = False
            else:
                if isinstance(img_for_yolo, np.ndarray):
                    pil_img = Image.fromarray(img_for_yolo)
                else:
                    pil_img = Image.open(img_for_yolo)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    pil_img.save(f.name, format="PNG")
                    temp_path = f.name
                cleanup = True

            start_t = time.perf_counter()
            _, result_json = client.predict(
                image=handle_file(temp_path),
                detector_choice=definition.key,
                conf_cutoff=float(confidence),
                api_name="/predict",
            )
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0

            if cleanup and temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

            if not isinstance(result_json, dict) or "detections" not in result_json:
                return None

            detections: List[DetectionResult] = []
            for d in result_json.get("detections", []):
                # Filter to requested model
                if d.get("model") != definition.key:
                    continue
                cid = int(d.get("class_id", 0))
                score = float(d.get("confidence", 0.0))
                b = d.get("bbox", {})
                x1 = float(b.get("x1", 0.0))
                y1 = float(b.get("y1", 0.0))
                x2 = float(b.get("x2", 0.0))
                y2 = float(b.get("y2", 0.0))
                bw = float(b.get("w", max(0.0, x2 - x1)))
                bh = float(b.get("h", max(0.0, y2 - y1)))

                safe_w = max(1, img_width)
                safe_h = max(1, img_height)

                bbox = BoundingBox(
                    x1=round(x1, 2),
                    y1=round(y1, 2),
                    x2=round(x2, 2),
                    y2=round(y2, 2),
                    width=round(bw, 2),
                    height=round(bh, 2),
                    norm_x1=round(max(0.0, min(1.0, x1 / safe_w)), 4),
                    norm_y1=round(max(0.0, min(1.0, y1 / safe_h)), 4),
                    norm_w=round(max(0.0, min(1.0, bw / safe_w)), 4),
                    norm_h=round(max(0.0, min(1.0, bh / safe_h)), 4),
                )

                raw_name = definition.get_raw_class_name(cid)
                semantic_label = definition.get_semantic_label(cid)

                detections.append(DetectionResult(
                    model_name=definition.key,
                    class_id=cid,
                    raw_class_name=raw_name,
                    semantic_class_name=semantic_label,
                    confidence=round(score, 4),
                    bounding_box=bbox,
                    image_width=img_width,
                    image_height=img_height,
                ))

            logger.info(
                f"[ZeroGPU Cloud] {definition.key}: {len(detections)} targets in {elapsed_ms:.1f}ms"
            )
            return InferenceResponse(
                model_name=definition.key,
                model_architecture=definition.architecture,
                detections_count=len(detections),
                detections=detections,
                image_width=img_width,
                image_height=img_height,
                inference_time_ms=round(elapsed_ms, 2),
                triage=result_json.get("triage"),
            )
        except Exception as e:
            global _hf_client
            if "ZeroGPU" in str(e) or "limit" in str(e).lower() or "quota" in str(e).lower() or "timed out" in str(e).lower():
                _hf_client = False
            logger.warning(
                f"Remote ZeroGPU inference failed on model '{definition.key}', falling back to local: {e}"
            )
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            return None

    @staticmethod
    def try_predict_all_remote(
        target_models: List[ModelDefinition],
        image: Union[np.ndarray, Image.Image, str, Path],
        confidence: float,
    ) -> Optional[Tuple[List[DetectionResult], Optional[Dict[str, Any]]]]:
        """Run all requested models in a single remote ZeroGPU inference pass (2-3s vs 60s)."""
        if not settings.USE_REMOTE_INFERENCE or not settings.HF_SPACE_ID:
            return None

        client = _get_hf_client()
        if not client:
            return None

        temp_path = None
        try:
            from gradio_client import handle_file

            img_for_yolo, img_width, img_height = _normalize_image_input(image)
            if isinstance(image, (str, Path)):
                temp_path = str(image)
                cleanup = False
            else:
                if isinstance(img_for_yolo, np.ndarray):
                    pil_img = Image.fromarray(img_for_yolo)
                else:
                    pil_img = Image.open(img_for_yolo)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    pil_img.save(f.name, format="PNG")
                    temp_path = f.name
                cleanup = True

            # If exactly 1 specific model requested, pass that key; otherwise 'all'
            detector_choice = target_models[0].key if len(target_models) == 1 else "all"

            start_t = time.perf_counter()
            _, result_json = client.predict(
                image=handle_file(temp_path),
                detector_choice=detector_choice,
                conf_cutoff=float(confidence),
                api_name="/predict",
            )
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0

            if cleanup and temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

            if not isinstance(result_json, dict) or "detections" not in result_json:
                return None

            model_map = {m.key: m for m in target_models}
            detections: List[DetectionResult] = []
            for d in result_json.get("detections", []):
                m_key = d.get("model")
                if m_key not in model_map:
                    continue
                definition = model_map[m_key]
                cid = int(d.get("class_id", 0))
                score = float(d.get("confidence", 0.0))
                b = d.get("bbox", {})
                x1 = float(b.get("x1", 0.0))
                y1 = float(b.get("y1", 0.0))
                x2 = float(b.get("x2", 0.0))
                y2 = float(b.get("y2", 0.0))
                bw = float(b.get("w", max(0.0, x2 - x1)))
                bh = float(b.get("h", max(0.0, y2 - y1)))

                safe_w = max(1, img_width)
                safe_h = max(1, img_height)

                bbox = BoundingBox(
                    x1=round(x1, 2),
                    y1=round(y1, 2),
                    x2=round(x2, 2),
                    y2=round(y2, 2),
                    width=round(bw, 2),
                    height=round(bh, 2),
                    norm_x1=round(max(0.0, min(1.0, x1 / safe_w)), 4),
                    norm_y1=round(max(0.0, min(1.0, y1 / safe_h)), 4),
                    norm_w=round(max(0.0, min(1.0, bw / safe_w)), 4),
                    norm_h=round(max(0.0, min(1.0, bh / safe_h)), 4),
                )

                raw_name = definition.get_raw_class_name(cid)
                semantic_label = definition.get_semantic_label(cid)

                detections.append(DetectionResult(
                    model_name=definition.key,
                    class_id=cid,
                    raw_class_name=raw_name,
                    semantic_class_name=semantic_label,
                    confidence=round(score, 4),
                    bounding_box=bbox,
                    image_width=img_width,
                    image_height=img_height,
                ))

            logger.info(
                f"[ZeroGPU Batch Pass] Executed {len(target_models)} models in {elapsed_ms:.1f}ms (found {len(detections)} contacts)"
            )
            return detections, result_json.get("triage")
        except Exception as e:
            global _hf_client
            if "ZeroGPU" in str(e) or "limit" in str(e).lower() or "quota" in str(e).lower() or "timed out" in str(e).lower():
                _hf_client = False
            logger.warning(f"Remote batch ZeroGPU pass failed, falling back to sequential: {e}")
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            return None

    @staticmethod
    def classify_seabed(
        image: Union[np.ndarray, Image.Image, str, Path],
        clean_threshold: float = 0.92,
    ) -> TriageClassificationResult:
        """Execute Natural Seabed classification and uncertainty triage on a sonar image swath.

        Args:
            image: Sonar image input.
            clean_threshold: Probability threshold above which the swath is conclusively clean seabed.
                            Default: 0.92.

        Returns:
            TriageClassificationResult with probabilities, classification decision, and bypass recommendations.
        """
        definition = get_model_definition("natural_seabed")
        img_for_yolo, _, _ = _normalize_image_input(image)
        model = load_model(definition.key)

        start_time = time.perf_counter()
        with torch.inference_mode():
            results = model.predict(
                source=img_for_yolo,
                imgsz=definition.input_size[0],
                verbose=False,
            )
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        p_clean = 0.50
        p_anomaly = 0.50
        if results and len(results) > 0 and hasattr(results[0], "probs") and results[0].probs is not None:
            probs = results[0].probs.data.cpu().numpy().tolist()
            if len(probs) >= 2:
                p_clean = float(probs[0])
                p_anomaly = float(probs[1])

        # Decision rule:
        # 1. P(clean) >= clean_threshold: Conclusively natural seabed -> BYPASS downstream detectors
        # 2. P(clean) < 0.50 (i.e. P(anomaly) >= 0.50): Confirmed anomaly -> ANOMALY_TRIGGERED
        # 3. 0.50 <= P(clean) < clean_threshold: Unsure / marginal -> UNSURE_FORWARDED (fall forward to detectors)
        if p_clean >= clean_threshold:
            decision = "BYPASS_CLEAN"
            is_clean = True
            anomaly_suspected = False
            is_uncertain = False
            downstream_skipped = True
            predicted_class = "clean_seabed"
        elif p_anomaly >= 0.50:
            decision = "ANOMALY_TRIGGERED"
            is_clean = False
            anomaly_suspected = True
            is_uncertain = False
            downstream_skipped = False
            predicted_class = "debris_anomaly"
        else:
            decision = "UNSURE_FORWARDED"
            is_clean = False
            anomaly_suspected = False
            is_uncertain = True
            downstream_skipped = False
            predicted_class = "debris_anomaly"

        return TriageClassificationResult(
            model_name="natural_seabed",
            predicted_class=predicted_class,
            is_clean=is_clean,
            anomaly_suspected=anomaly_suspected,
            is_uncertain=is_uncertain,
            clean_probability=round(p_clean, 4),
            anomaly_probability=round(p_anomaly, 4),
            decision=decision,
            threshold_used=float(clean_threshold),
            downstream_skipped=downstream_skipped,
            inference_time_ms=round(elapsed_ms, 2),
        )

    @staticmethod
    def classify_seabed_roi(
        roi: "np.ndarray",
        clean_threshold: float = 0.70,
    ) -> "TriageClassificationResult":
        """Classify a pre-cropped region-of-interest (ROI) against the natural seabed model.

        Unlike classify_seabed(), this method accepts a raw numpy crop directly
        (already extracted from the original swath) and is optimised for rapid
        per-detection re-verification without redundant preprocessing.

        Args:
            roi: Cropped numpy array (HWC, RGB) extracted from the detection bounding box.
            clean_threshold: Probability above which the ROI is considered conclusively
                             clean seabed and the parent detection should be suppressed.
                             Lower than the full-image threshold (default 0.70) to be
                             more aggressive about catching false positives.

        Returns:
            TriageClassificationResult with per-ROI decision.
        """
        import gc as _gc

        definition = get_model_definition("natural_seabed")
        model = load_model(definition.key)

        # Ensure ROI is valid and large enough to classify
        if roi is None or roi.size == 0 or roi.shape[0] < 8 or roi.shape[1] < 8:
            # If ROI is too small to meaningfully classify, pass-through (don't suppress)
            return TriageClassificationResult(
                model_name="natural_seabed",
                predicted_class="debris_anomaly",
                is_clean=False,
                anomaly_suspected=True,
                is_uncertain=True,
                clean_probability=0.0,
                anomaly_probability=1.0,
                decision="ROI_TOO_SMALL",
                threshold_used=float(clean_threshold),
                downstream_skipped=False,
                inference_time_ms=0.0,
            )

        start_time = time.perf_counter()
        try:
            with torch.inference_mode():
                results = model.predict(
                    source=roi,
                    imgsz=definition.input_size[0],
                    verbose=False,
                )
        except Exception as e:
            logger.warning(f"[ROI Re-verify] natural_seabed ROI classification failed: {e}")
            return TriageClassificationResult(
                model_name="natural_seabed",
                predicted_class="debris_anomaly",
                is_clean=False,
                anomaly_suspected=True,
                is_uncertain=True,
                clean_probability=0.0,
                anomaly_probability=1.0,
                decision="ROI_ERROR",
                threshold_used=float(clean_threshold),
                downstream_skipped=False,
                inference_time_ms=0.0,
            )
        finally:
            _gc.collect()

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        p_clean = 0.50
        p_anomaly = 0.50
        if results and len(results) > 0 and hasattr(results[0], "probs") and results[0].probs is not None:
            probs = results[0].probs.data.cpu().numpy().tolist()
            if len(probs) >= 2:
                p_clean = float(probs[0])
                p_anomaly = float(probs[1])

        if p_clean >= clean_threshold:
            decision = "ROI_BYPASS_CLEAN"
            is_clean = True
            anomaly_suspected = False
            is_uncertain = False
            predicted_class = "clean_seabed"
        elif p_anomaly >= 0.50:
            decision = "ROI_ANOMALY_CONFIRMED"
            is_clean = False
            anomaly_suspected = True
            is_uncertain = False
            predicted_class = "debris_anomaly"
        else:
            decision = "ROI_UNSURE_KEPT"
            is_clean = False
            anomaly_suspected = False
            is_uncertain = True
            predicted_class = "debris_anomaly"

        logger.debug(
            f"[ROI Re-verify] p_clean={p_clean:.3f} p_anomaly={p_anomaly:.3f} "
            f"threshold={clean_threshold} → {decision} ({elapsed_ms:.1f}ms)"
        )

        return TriageClassificationResult(
            model_name="natural_seabed",
            predicted_class=predicted_class,
            is_clean=is_clean,
            anomaly_suspected=anomaly_suspected,
            is_uncertain=is_uncertain,
            clean_probability=round(p_clean, 4),
            anomaly_probability=round(p_anomaly, 4),
            decision=decision,
            threshold_used=float(clean_threshold),
            downstream_skipped=is_clean,
            inference_time_ms=round(elapsed_ms, 2),
        )

    @staticmethod
    def predict(
        name_or_key: str,
        image: Union[np.ndarray, Image.Image, str, Path],
        confidence: Optional[float] = None,
        iou: Optional[float] = None,
    ) -> InferenceResponse:
        """Run object detection on an image using the specified model.

        Args:
            name_or_key: Registered model identifier (e.g. 'ghostvision', 'cylinder').
            image: Image as numpy array (HWC/HW), PIL Image, or file path.
            confidence: Optional confidence cutoff [0.0 - 1.0]. If None, uses model default.
            iou: Optional NMS IoU threshold [0.0 - 1.0]. If None, uses model default.

        Returns:
            InferenceResponse containing normalized detection results.
        """
        definition: ModelDefinition = get_model_definition(name_or_key)

        conf_threshold = confidence if confidence is not None else definition.default_conf
        iou_threshold = iou if iou is not None else definition.default_iou

        img_for_yolo, img_width, img_height = _normalize_image_input(image)

        # Handle classification tasks directly
        if definition.task == "classify":
            triage_res = InferenceService.classify_seabed(image=img_for_yolo, clean_threshold=conf_threshold)
            return InferenceResponse(
                model_name=definition.key,
                model_architecture=definition.architecture,
                detections_count=0,
                detections=[],
                image_width=img_width,
                image_height=img_height,
                inference_time_ms=triage_res.inference_time_ms,
                triage=triage_res.model_dump(),
            )

        # 1. First priority: Remote GPU-accelerated ZeroGPU inference
        if settings.USE_REMOTE_INFERENCE and settings.HF_SPACE_ID:
            remote_resp = InferenceService._try_predict_remote(
                definition=definition,
                image=image,
                confidence=conf_threshold,
                iou=iou_threshold,
            )
            if remote_resp is not None:
                return remote_resp

        # 2. Local execution fallback
        model = load_model(definition.key)

        # Native resolution required by this specific model (e.g. 1536 for Cylinder, 640 for others)
        native_imgsz = definition.input_size[0]

        # On CPU without CUDA, YOLO12 A2C2f area-attention scales quadratically O(N^2).
        # On free-tier containers with <=512MB RAM, 640px allocates >1.2 GB and triggers Linux OOM killer.
        # Native input size from model definition (e.g. 1536 for Cylinder, 640 for others)
        cpu_max_sz = int(os.getenv("CPU_MAX_IMAGE_SIZE", "1536"))
        if not torch.cuda.is_available() and native_imgsz > cpu_max_sz:
            exec_imgsz = cpu_max_sz
        else:
            exec_imgsz = native_imgsz

        start_time = time.perf_counter()
        results = None
        with torch.inference_mode():
            try:
                results = model.predict(
                    source=img_for_yolo,
                    imgsz=exec_imgsz,
                    conf=conf_threshold,
                    iou=iou_threshold,
                    verbose=False,
                )
            except Exception as e:
                # If memory is extremely constrained, retry at 320px or fall back gracefully
                try:
                    gc.collect()
                    results = model.predict(
                        source=img_for_yolo,
                        imgsz=320,
                        conf=conf_threshold,
                        iou=iou_threshold,
                        verbose=False,
                    )
                except Exception:
                    results = []
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        detections: List[DetectionResult] = []

        if results and len(results) > 0:
            first_result = results[0]
            boxes = first_result.boxes

            if boxes is not None and len(boxes) > 0:
                xyxy_coords = boxes.xyxy.cpu().numpy()
                confs = boxes.conf.cpu().numpy()
                cls_ids = boxes.cls.cpu().numpy().astype(int)

                for coord, score, cid in zip(xyxy_coords, confs, cls_ids):
                    x1, y1, x2, y2 = [float(v) for v in coord]
                    box_w = max(0.0, x2 - x1)
                    box_h = max(0.0, y2 - y1)

                    # Normalized coordinates [0.0 - 1.0] safe against zero division
                    safe_w = max(1, img_width)
                    safe_h = max(1, img_height)

                    norm_x1 = max(0.0, min(1.0, x1 / safe_w))
                    norm_y1 = max(0.0, min(1.0, y1 / safe_h))
                    norm_w = max(0.0, min(1.0, box_w / safe_w))
                    norm_h = max(0.0, min(1.0, box_h / safe_h))

                    bbox = BoundingBox(
                        x1=round(x1, 2),
                        y1=round(y1, 2),
                        x2=round(x2, 2),
                        y2=round(y2, 2),
                        width=round(box_w, 2),
                        height=round(box_h, 2),
                        norm_x1=round(norm_x1, 4),
                        norm_y1=round(norm_y1, 4),
                        norm_w=round(norm_w, 4),
                        norm_h=round(norm_h, 4),
                    )

                    raw_name = definition.get_raw_class_name(cid)
                    semantic_label = definition.get_semantic_label(cid)

                    detection = DetectionResult(
                        model_name=definition.key,
                        class_id=cid,
                        raw_class_name=raw_name,
                        semantic_class_name=semantic_label,
                        confidence=round(float(score), 4),
                        bounding_box=bbox,
                        image_width=img_width,
                        image_height=img_height,
                    )
                    detections.append(detection)

        del results
        gc.collect()

        return InferenceResponse(
            model_name=definition.key,
            model_architecture=definition.architecture,
            detections_count=len(detections),
            detections=detections,
            image_width=img_width,
            image_height=img_height,
            inference_time_ms=round(elapsed_ms, 2),
        )


inference_service = InferenceService()
