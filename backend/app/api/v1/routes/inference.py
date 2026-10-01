"""Inference route handler for API v1."""

import io
import logging
from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from PIL import Image

from app.core.model_registry import (
    ModelDefinition,
    ModelNotFoundError,
    get_model_definition,
    list_registered_models,
)
from app.schemas.inference import (
    PredictDetectionItem,
    PredictImageInfo,
    PredictModelInfo,
    PredictResponse,
)
import gc
from app.services.inference import inference_service
from app.services.model_loader import ModelLoadError, unload_model

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/tiff",
    "image/tif",
    "image/bmp",
    "image/webp",
    "image/x-png",
}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


@router.post(
    "/predict",
    response_model=PredictResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute Model Inference on a Sonar Image",
    description="Uploads a sonar image, validates input, executes specified model, and returns normalized detection results.",
)
def predict_image(
    image: UploadFile = File(..., description="Uploaded sonar image file (JPEG, PNG, TIFF, BMP, WebP)"),
    model: str = Form(..., description="Model identifier (e.g. cylinder, ghostvision, mine, shipwreck, subpipe)"),
    confidence: Optional[float] = Form(
        None, description="Optional detection confidence cutoff [0.0 - 1.0]. Default is 0.25."
    ),
    iou: Optional[float] = Form(
        None, description="Optional NMS IoU threshold [0.0 - 1.0]. Default is 0.70."
    ),
) -> PredictResponse:
    """Run detection inference on an uploaded sonar image."""

    # 1. Validate Model Identifier
    if not model or not model.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Model parameter is required.",
        )

    try:
        model_def: ModelDefinition = get_model_definition(model)
    except ModelNotFoundError:
        available = ", ".join(m.key for m in list_registered_models())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown model '{model}'. Available models: {available}.",
        )

    # 2. Validate Confidence & IoU Parameters
    if confidence is not None and not (0.0 <= confidence <= 1.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confidence threshold must be between 0.0 and 1.0.",
        )

    if iou is not None and not (0.0 <= iou <= 1.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="IoU threshold must be between 0.0 and 1.0.",
        )

    # 3. Validate Uploaded File Presence & Format
    filename = (image.filename or "").lower()
    has_valid_ext = any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS)
    has_valid_mime = image.content_type in ALLOWED_MIME_TYPES or image.content_type == "application/octet-stream"

    if not (has_valid_ext or has_valid_mime):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported image format '{image.content_type}'. "
                "Supported formats: JPEG, PNG, TIFF, BMP, WebP."
            ),
        )

    # 4. Read & Decode Image Data
    try:
        image_bytes = image.file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded image data.",
        )

    if not image_bytes or len(image_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image file is empty.",
        )

    try:
        pil_image = Image.open(io.BytesIO(image_bytes))
        # Verify image integrity and convert to RGB
        pil_image.verify()
        # Re-open after verify (PIL design requirement)
        pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        logger.warning(f"Corrupted or invalid image uploaded: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image file is corrupted or could not be decoded.",
        )

    # 5. Execute Prediction
    try:
        inference_result = inference_service.predict(
            name_or_key=model_def.key,
            image=pil_image,
            confidence=confidence,
            iou=iou,
        )
    except ModelLoadError as e:
        logger.error(f"Model load error for '{model_def.name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model '{model_def.name}' could not be loaded on the server.",
        )
    except Exception as e:
        logger.error(f"Unexpected inference error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during model inference.",
        )
    finally:
        unload_model(model_def.key)
        gc.collect()

    # 6. Map to Public Response Structure
    detection_items = [
        PredictDetectionItem(
            class_id=d.class_id,
            raw_class_name=d.raw_class_name,
            display_name=d.semantic_class_name,
            confidence=d.confidence,
            bounding_box=d.bounding_box,
        )
        for d in inference_result.detections
    ]

    return PredictResponse(
        success=True,
        model=PredictModelInfo(
            id=model_def.key,
            name=model_def.name,
        ),
        image=PredictImageInfo(
            width=inference_result.image_width,
            height=inference_result.image_height,
        ),
        detections=detection_items,
        count=len(detection_items),
    )
