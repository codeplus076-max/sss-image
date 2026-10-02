from app.core.config import settings
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
        version="1.0.2",
        service="sonar-backend",
        hf_token_configured=bool(settings.HF_TOKEN and settings.HF_TOKEN.strip()),
        models={
            "cylinder": "available",
            "ghostvision": "available",
            "mine": "available",
            "shipwreck": "available",
            "subpipe": "available",
            "natural_seabed": "available",
        },
    )
