"""Model registry listing endpoint for API v1."""

from fastapi import APIRouter, status
from app.core.model_registry import list_registered_models
from app.schemas.models import ClassMappingItem, ModelDetail, ModelListResponse

router = APIRouter()


@router.get(
    "/models",
    response_model=ModelListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Registered Models",
    description="Returns metadata, native input resolutions, and exact class mappings for all registered models.",
)
async def list_models() -> ModelListResponse:
    """Return all verified detection models with their raw and semantic class mappings."""
    registered = list_registered_models()
    model_details = []

    for m in registered:
        mappings = [
            ClassMappingItem(
                class_id=cid,
                raw_class_name=raw_name,
                display_name=m.get_semantic_label(cid),
            )
            for cid, raw_name in sorted(m.raw_classes.items())
        ]

        model_details.append(
            ModelDetail(
                id=m.key,
                name=m.name,
                display_name=m.name,
                architecture=m.architecture,
                input_resolution=m.input_size,
                task=m.task,
                status="available",
                class_mappings=mappings,
                notes=m.notes,
            )
        )

    return ModelListResponse(
        models=model_details,
        total=len(model_details),
        unavailable_models=[],
    )
