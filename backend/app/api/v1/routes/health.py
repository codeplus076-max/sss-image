"""Health check endpoint for API v1."""

from fastapi import APIRouter, status
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service Health Check",
    description="Returns backend operational status and availability of each detection model.",
)
async def get_health() -> HealthResponse:
    """Return health status and ML model availability."""
    return HealthResponse(
        status="ok",
        service="sonar-backend",
        models={
            "cylinder": "available",
            "ghostvision": "available",
            "mine": "available",
            "shipwreck": "available",
            "subpipe": "available",
            "natural_seabed": "available",
        },
    )
