"""Main entry point for the FastAPI application."""

import os
from contextlib import asynccontextmanager

os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/Ultralytics")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("TORCH_NUM_THREADS", "1")

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.core.anonymous_session import initialize_session
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
    enable_docs = settings.DEBUG or os.getenv("ENABLE_API_DOCS", "false").lower() in ("true", "1")
    app = FastAPI(
        title="Side-Scan Sonar Marine Intelligence Backend",
        description="REST API for Side-Scan Sonar quality assessment, preprocessing, and AI detection.",
        version="1.0.0",
        docs_url="/docs" if enable_docs else None,
        redoc_url="/redoc" if enable_docs else None,
        openapi_url="/openapi.json" if enable_docs else None,
        lifespan=lifespan,
    )

    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def protect_private_responses(request: Request, call_next):
        private = request.url.path.startswith(f"{settings.API_V1_PREFIX}/analysis") or request.url.path == f"{settings.API_V1_PREFIX}/session"
        origin = request.headers.get("origin")
        if private and request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin not in settings.CORS_ORIGINS:
            return JSONResponse({"detail": "Origin not allowed"}, status_code=403, headers={"Cache-Control": "no-store"})
        response = await call_next(request)
        if private:
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Vary"] = "Cookie, Origin"
        return response

    app.add_api_route(f"{settings.API_V1_PREFIX}/session", initialize_session, methods=["POST"])

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
