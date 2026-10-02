"""Health check response schema."""

from typing import Dict
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response containing service state and model availability."""

    status: str = Field(default="ok", description="Operational status of backend service")
    version: str = Field(default="1.0.3", description="Backend build version")
    service: str = Field(default="sonar-backend", description="Backend service identifier")
    hf_token_configured: bool = Field(default=False, description="Whether HF_TOKEN is configured in environment")
    models: Dict[str, str] = Field(
        default_factory=lambda: {
            "cylinder": "available",
            "ghostvision": "available",
            "mine": "available",
            "shipwreck": "available",
            "subpipe": "available",
            "natural_seabed": "available",
        },
        description="Availability status of each Side-Scan Sonar detection model",
    )
