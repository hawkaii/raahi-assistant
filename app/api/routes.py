"""
Main API router for the Raahi Assistant.

Architecture:
- POST /assistant/query - Returns JSON with intent, UI action, and data
- GET /assistant/audio/{cache_key} - Streams cached audio
- POST /assistant/query-with-audio - Returns JSON + streams audio via chunked transfer encoding
"""

import json
import logging
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse

from app.models import (
    AssistantRequest,
    AssistantResponse,
    IntentType,
    UIAction,
)
from app.services import (
    get_gemini_service,
    get_typesense_service,
    get_tts_service,
    get_cache_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])


async def _process_intent(request: AssistantRequest) -> tuple[AssistantResponse, str]:
    """
    Process user request: classify intent, fetch data, generate response.
    
    Returns:
        Tuple of (AssistantResponse, response_text_for_tts)
    """
    gemini = get_gemini_service()
    typesense = get_typesense_service()
    tts = get_tts_service()
    cache = get_cache_service()

    # Generate session ID if not provided
    session_id = request.session_id or str(uuid.uuid4())

    # Step 1: Classify intent and get response using Gemini
    intent_result = await gemini.classify_and_respond(
        user_text=request.text,
        driver_profile=request.driver_profile,
        location=request.current_location,
        session_id=session_id,
        preferred_language=request.preferred_language,
    )

    # Step 2: Fetch data based on intent
    data = None
    extracted_params = intent_result.data.get("extracted_params", {}) if intent_result.data else {}

    if intent_result.intent == IntentType.GET_DUTIES:
        duties = await typesense.search_duties(
            from_city=extracted_params.get("from_city"),
            to_city=extracted_params.get("to_city"),
            route=extracted_params.get("route"),
            vehicle_type=request.driver_profile.vehicle_type,
        )
        data = {"duties": [d.model_dump() for d in duties]}

    elif intent_result.intent == IntentType.NEARBY_CNG:
        stations = await typesense.search_nearby_fuel_stations(
            location=request.current_location,
            fuel_type="cng",
        )
        data = {"stations": [s.model_dump() for s in stations]}

    elif intent_result.intent == IntentType.NEARBY_PETROL:
        stations = await typesense.search_nearby_fuel_stations(
            location=request.current_location,
            fuel_type="petrol",
        )
        data = {"stations": [s.model_dump() for s in stations]}

    elif intent_result.intent == IntentType.PROFILE_VERIFICATION:
        # Build verification checklist from driver profile
        profile = request.driver_profile
        verification_status = {
            "is_verified": profile.is_verified,
            "checklist": [
                {"item": "License", "verified": profile.license_verified},
                {"item": "RC (Registration Certificate)", "verified": profile.rc_verified},
                {"item": "Insurance", "verified": profile.insurance_verified},
            ],
            "pending_documents": profile.documents_pending,
        }
        data = {"verification": verification_status}

    # Step 3: Check if audio is cached
    cache_key = tts.get_cache_key(intent_result.response_text)
    audio_cached = await cache.exists(cache_key)

    return AssistantResponse(
        session_id=session_id,
        intent=intent_result.intent,
        ui_action=intent_result.ui_action,
        response_text=intent_result.response_text,
        data=data,
        audio_cached=audio_cached,
        cache_key=cache_key,
    ), intent_result.response_text


@router.post("/query", response_model=AssistantResponse)
async def query_assistant(request: AssistantRequest) -> AssistantResponse:
    """
    Process a text query from the user.
    
    Returns JSON with:
    - intent classification
    - UI action for Flutter to perform
    - relevant data (duties, stations, verification info)
    - cache_key to fetch audio separately
    
    Use this endpoint when you want to:
    1. Get the response data first
    2. Control the UI based on intent
    3. Then stream audio separately via /audio/{cache_key}
    """
    try:
        response, _ = await _process_intent(request)
        return response
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/audio/{cache_key}")
async def get_audio(cache_key: str) -> StreamingResponse:
    """
    Stream audio for a given cache key.
    
    If cached, returns cached audio.
    If not cached, returns 404 (use /query-with-audio to generate).
    """
    cache = get_cache_service()
    
    audio_data = await cache.get(cache_key)
    if not audio_data:
        raise HTTPException(status_code=404, detail="Audio not found in cache")

    async def audio_stream() -> AsyncIterator[bytes]:
        chunk_size = 4096
        for i in range(0, len(audio_data), chunk_size):
            yield audio_data[i:i + chunk_size]

    return StreamingResponse(
        audio_stream(),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": "inline",
            "Transfer-Encoding": "chunked",
        },
    )


@router.post("/query-with-audio")
async def query_with_audio(request: AssistantRequest) -> StreamingResponse:
    """
    Process query and return JSON metadata + streamed audio.
    
    Response format (chunked transfer encoding):
    1. First chunk: JSON metadata (terminated with newline)
    2. Subsequent chunks: Audio data (MP3)
    
    This is a hybrid approach:
    - REST-like JSON response with all metadata
    - Chunked audio streaming for low latency playback
    
    Flutter client should:
    1. Read first line as JSON, parse it for UI actions
    2. Pipe remaining bytes to audio player
    """
    try:
        response, response_text = await _process_intent(request)
        
        tts = get_tts_service()
        cache = get_cache_service()
        cache_key = response.cache_key

        async def stream_response() -> AsyncIterator[bytes]:
            # First, yield JSON metadata
            json_data = response.model_dump_json()
            yield json_data.encode() + b"\n"

            # Check cache first
            cached_audio = await cache.get(cache_key)
            if cached_audio:
                # Stream cached audio in chunks
                chunk_size = 4096
                for i in range(0, len(cached_audio), chunk_size):
                    yield cached_audio[i:i + chunk_size]
            else:
                # Generate and cache audio
                audio_chunks = []
                async for chunk in tts.synthesize_speech_streaming(response_text):
                    audio_chunks.append(chunk)
                    yield chunk
                
                # Cache the full audio
                full_audio = b"".join(audio_chunks)
                await cache.set(cache_key, full_audio)

        return StreamingResponse(
            stream_response(),
            media_type="application/octet-stream",
            headers={
                "Transfer-Encoding": "chunked",
                "X-Content-Type": "application/json+audio/mpeg",
            },
        )

    except Exception as e:
        logger.error(f"Error in query-with-audio: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/session/{session_id}")
async def clear_session(session_id: str) -> dict:
    """Clear conversation history for a session."""
    gemini = get_gemini_service()
    gemini.clear_session(session_id)
    return {"status": "ok", "message": f"Session {session_id} cleared"}
