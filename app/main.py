"""
Raahi AI Assistant API

A voice-enabled AI assistant for truck drivers with:
- Intent classification using Vertex AI Gemini
- Duty/trip search using Typesense
- Nearby fuel station search (geo-based)
- Profile verification assistance
- TTS with Google Cloud Chirp 3 HD (Aoede voice)
- Audio caching with Redis
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.services import get_cache_service
from config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting Raahi Assistant API...")
    yield
    # Cleanup
    logger.info("Shutting down Raahi Assistant API...")
    cache = get_cache_service()
    await cache.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Raahi AI Assistant",
        description=__doc__,
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware for Flutter app
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(router)

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": "raahi-assistant"}

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
