"""Main entry point for the FastAPI application."""

import os
from contextlib import asynccontextmanager

os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/Ultralytics")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes import api_router as api_v1_router
from app.core.config import settings
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager to handle startup and shutdown events."""
    # Ensure database tables exist on startup
    init_db()
    yield


def create_application() -> FastAPI:
    """Factory function to configure and return the FastAPI application instance."""
    app = FastAPI(
        title="Side-Scan Sonar Marine Intelligence Backend",
        description="REST API for Side-Scan Sonar quality assessment, preprocessing, and AI detection.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routers
    app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

    @app.get("/", tags=["root"])
    async def root():
        """Root API endpoint providing service metadata."""
        return {
            "name": settings.APP_NAME,
            "version": "1.0.0",
            "documentation": "/docs",
            "health": f"{settings.API_V1_PREFIX}/health",
        }

    return app


app = create_application()

if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.environ.get("PORT", settings.PORT))
    host = os.environ.get("HOST", settings.HOST)

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=settings.DEBUG,
    )
