"""
Text-to-Speech service using Google Cloud TTS with Chirp 3 HD voices.
Supports streaming audio generation and caching.
"""

import hashlib
import logging
from typing import AsyncIterator, Optional

from google.cloud import texttospeech_v1 as texttospeech

from config import get_settings

logger = logging.getLogger(__name__)


class TTSService:
    """Service for text-to-speech using Google Cloud TTS with Chirp 3 HD."""

    def __init__(self):
        settings = get_settings()
        self.client = texttospeech.TextToSpeechAsyncClient()
        self.voice_name = settings.tts_voice_name
        self.language_code = settings.tts_language_code

    def _get_cache_key(self, text: str) -> str:
        """Generate a cache key for the given text."""
        normalized = text.strip().lower()
        return f"tts:{hashlib.sha256(normalized.encode()).hexdigest()}"

    async def synthesize_speech(self, text: str) -> bytes:
        """
        Synthesize speech from text using Chirp 3 HD Aoede voice.
        
        Args:
            text: Text to convert to speech
            
        Returns:
            Audio content as bytes (MP3 format)
        """
        try:
            synthesis_input = texttospeech.SynthesisInput(text=text)

            # Use Chirp 3 HD voice (Aoede)
            voice = texttospeech.VoiceSelectionParams(
                language_code=self.language_code,
                name=self.voice_name,
            )

            # Use MP3 for smaller size and wide compatibility
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.0,
                pitch=0.0,
            )

            response = await self.client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config,
            )

            return response.audio_content

        except Exception as e:
            logger.error(f"Error synthesizing speech: {e}")
            raise

    async def synthesize_speech_streaming(
        self, text: str, chunk_size: int = 4096
    ) -> AsyncIterator[bytes]:
        """
        Synthesize speech and yield chunks for streaming.
        
        Note: Google TTS doesn't support true streaming for standard synthesis,
        so we synthesize the full audio and then stream it in chunks.
        For true streaming, use the streaming_synthesize method with v1beta1.
        
        Args:
            text: Text to convert to speech
            chunk_size: Size of each chunk in bytes
            
        Yields:
            Audio chunks
        """
        try:
            audio_content = await self.synthesize_speech(text)
            
            # Yield in chunks for streaming response
            for i in range(0, len(audio_content), chunk_size):
                yield audio_content[i:i + chunk_size]

        except Exception as e:
            logger.error(f"Error in streaming synthesis: {e}")
            raise

    def get_cache_key(self, text: str) -> str:
        """Get the cache key for a given text (public method for caching service)."""
        return self._get_cache_key(text)


# Singleton instance
_tts_service: Optional[TTSService] = None


def get_tts_service() -> TTSService:
    """Get or create the TTS service singleton."""
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
    return _tts_service
