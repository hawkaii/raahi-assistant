"""
Audio caching service using Redis.
Caches TTS audio to avoid regenerating for similar responses.
"""

import logging
from typing import Optional

import redis.asyncio as redis

from config import get_settings

logger = logging.getLogger(__name__)


class AudioCacheService:
    """Service for caching TTS audio in Redis."""

    def __init__(self):
        settings = get_settings()
        self.redis = redis.from_url(settings.redis_url)
        self.ttl = settings.audio_cache_ttl

    async def get(self, cache_key: str) -> Optional[bytes]:
        """
        Get cached audio by key.
        
        Args:
            cache_key: The cache key (from TTS service)
            
        Returns:
            Cached audio bytes or None if not found
        """
        try:
            data = await self.redis.get(cache_key)
            if data:
                logger.debug(f"Cache hit for key: {cache_key}")
            return data
        except Exception as e:
            logger.error(f"Error getting from cache: {e}")
            return None

    async def set(self, cache_key: str, audio_data: bytes) -> bool:
        """
        Cache audio data.
        
        Args:
            cache_key: The cache key
            audio_data: Audio bytes to cache
            
        Returns:
            True if cached successfully
        """
        try:
            await self.redis.setex(cache_key, self.ttl, audio_data)
            logger.debug(f"Cached audio for key: {cache_key}")
            return True
        except Exception as e:
            logger.error(f"Error setting cache: {e}")
            return False

    async def exists(self, cache_key: str) -> bool:
        """Check if a cache key exists."""
        try:
            return await self.redis.exists(cache_key) > 0
        except Exception as e:
            logger.error(f"Error checking cache existence: {e}")
            return False

    async def close(self):
        """Close Redis connection."""
        await self.redis.close()


# Singleton instance
_cache_service: Optional[AudioCacheService] = None


def get_cache_service() -> AudioCacheService:
    """Get or create the cache service singleton."""
    global _cache_service
    if _cache_service is None:
        _cache_service = AudioCacheService()
    return _cache_service
