"""
Audio configuration service for dynamic audio URL management.

Loads audio URLs from config/audio_urls.json file.
Works with uvicorn --reload for automatic updates when JSON file changes.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict

from app.models import IntentType

logger = logging.getLogger(__name__)


class AudioConfigService:
    """Simple JSON-based audio URL configuration service."""

    def __init__(self, config_path: str = "config/audio_urls.json"):
        """
        Initialize audio config service.
        
        Args:
            config_path: Path to JSON configuration file
        """
        self._config_path = Path(config_path)
        self._config: Dict[str, Optional[str]] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load audio URLs from JSON file."""
        try:
            if not self._config_path.exists():
                logger.warning(
                    f"Audio config file not found: {self._config_path}. "
                    "All intents will generate TTS audio."
                )
                self._config = {}
                return

            with open(self._config_path, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
            
            logger.info(
                f"Loaded audio configuration from {self._config_path}: "
                f"{len(self._config)} intent mappings"
            )
            
            # Log which intents have URLs vs TTS generation
            has_url = [k for k, v in self._config.items() if v is not None]
            will_generate_tts = [k for k, v in self._config.items() if v is None]
            
            if has_url:
                logger.info(f"Intents with audio URLs: {', '.join(has_url)}")
            if will_generate_tts:
                logger.info(f"Intents that will generate TTS: {', '.join(will_generate_tts)}")

        except json.JSONDecodeError as e:
            logger.error(
                f"Invalid JSON in audio config file {self._config_path}: {e}. "
                "All intents will generate TTS audio."
            )
            self._config = {}
        except Exception as e:
            logger.error(
                f"Failed to load audio config from {self._config_path}: {e}. "
                "All intents will generate TTS audio."
            )
            self._config = {}

    def get_url(self, intent: IntentType, interaction_count: Optional[int] = None) -> Optional[str]:
        """
        Get audio URL for a specific intent, with interaction count awareness.
        
        For intents with short versions (e.g., 'entry' and 'entry_short'):
        - If interaction_count >= 5 and a '_short' version exists, return the short version
        - Otherwise return the regular version
        
        Args:
            intent: The intent type to get audio URL for
            interaction_count: Number of user interactions (optional)
            
        Returns:
            Audio URL string if configured, None if should generate TTS
        """
        intent_key = intent.value
        
        # If interaction_count >= 5, try to use the short version first
        if interaction_count is not None and interaction_count >= 5:
            short_key = f"{intent_key}_short"
            short_url = self._config.get(short_key)
            
            if short_url is not None:
                logger.debug(
                    f"Using short audio for intent '{intent_key}' "
                    f"(interaction_count={interaction_count})"
                )
                return short_url
            else:
                logger.debug(
                    f"Short audio not configured for '{intent_key}', "
                    f"using regular version"
                )
        
        # Fall back to regular version
        url = self._config.get(intent_key)
        
        if url is None:
            logger.debug(f"No audio URL for intent '{intent_key}', will generate TTS")
        
        return url

    def has_url(self, intent: IntentType) -> bool:
        """
        Check if an intent has a configured audio URL.
        
        Args:
            intent: The intent type to check
            
        Returns:
            True if intent has a non-null URL configured
        """
        return self._config.get(intent.value) is not None

    def reload(self) -> None:
        """
        Manually reload configuration from file.
        
        Note: With uvicorn --reload, this is called automatically
        when the JSON file changes (server restarts).
        """
        logger.info("Reloading audio configuration...")
        self._load_config()


# Singleton instance
_audio_config_service: Optional[AudioConfigService] = None


def get_audio_config_service() -> AudioConfigService:
    """
    Get or create the audio config service singleton.
    
    Returns:
        AudioConfigService instance
    """
    global _audio_config_service
    if _audio_config_service is None:
        _audio_config_service = AudioConfigService()
    return _audio_config_service
