from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Google Cloud
    gcp_project_id: str
    gcp_location: str = "us-central1"

    # Vertex AI / Gemini
    gemini_model: str = "gemini-1.5-flash"

    # TTS - Chirp 3 HD (Hindi voice)
    tts_voice_name: str = "hi-IN-Chirp3-HD-Shilpa"  # Hindi female voice
    tts_language_code: str = "hi-IN"  # Hindi (India)

    # Typesense
    typesense_host: str = "localhost"
    typesense_port: int = 8108
    typesense_protocol: str = "http"
    typesense_api_key: str

    # Typesense Collections
    duties_collection: str = "duties"
    fuel_stations_collection: str = "fuel_stations"
    trips_collection: str = "trips"
    leads_collection: str = "bwi-cabswalle-leads"

    # Google Maps API
    google_maps_api_key: str

    # Redis for caching
    redis_url: str = "redis://localhost:6379"
    audio_cache_ttl: int = 86400 * 7  # 7 days

    # Firebase (for analytics logging)
    firebase_credentials_path: str = ""
    enable_analytics_logging: bool = True

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
