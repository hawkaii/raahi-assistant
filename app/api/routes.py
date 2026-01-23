"""
Main API router for the Raahi Assistant.

Architecture:
- POST /assistant/query - Returns JSON with intent, UI action, and data
- GET /assistant/audio/{cache_key} - Streams cached audio
- POST /assistant/query-with-audio - Returns JSON + streams audio via chunked transfer encoding
"""

import asyncio
import json
import logging
import re
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Response, BackgroundTasks
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
    get_audio_config_service,
)
from app.services.geocoding_service import get_city_coordinates, get_city_coordinates_with_country
from app.services.firebase_service import get_firebase_service
from app.utils.merge_utils import (
    merge_and_deduplicate,
    combine_trips_and_leads,
    normalize_trip_to_duty,
    normalize_lead_to_duty,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])


async def _process_intent(
    request: AssistantRequest, background_tasks: BackgroundTasks
) -> tuple[AssistantResponse, str]:
    """
    Process user request: classify intent, fetch data, generate response.

    Args:
        request: Assistant request with user text and profile
        background_tasks: FastAPI background tasks for async Firebase logging

    Returns:
        Tuple of (AssistantResponse, response_text_for_tts)
    """
    gemini = get_gemini_service()
    typesense = get_typesense_service()
    tts = get_tts_service()
    cache = get_cache_service()
    audio_config = get_audio_config_service()

    # Generate session ID if not provided
    session_id = request.session_id or str(uuid.uuid4())

    # Check for chip_click (UI button/chip interaction - no Gemini parsing needed)
    if request.chip_click == "find":
        find_chip_url = audio_config.get_url_direct("find_chip")
        
        return AssistantResponse(
            session_id=session_id,
            intent=IntentType.GENERIC,
            ui_action=UIAction.NONE,
            response_text="",  # No TTS, use audio_url instead
            data=None,
            audio_cached=False,
            cache_key="",
            audio_url=find_chip_url,
        ), ""

    # Check for entry state (either interaction_count present OR empty text)
    if request.text.strip() == "":
        greeting_url = audio_config.get_url(
            IntentType.ENTRY, 
            request.interaction_count,
            request.is_home
        )

        return AssistantResponse(
            session_id=session_id,
            intent=IntentType.ENTRY,
            ui_action=UIAction.ENTRY,
            response_text="",  # No TTS, use audio_url instead
            data=None,
            audio_cached=False,
            cache_key="",
            audio_url=greeting_url,
        ), ""

    # Step 1: Classify intent and get response using Gemini
    # Force English responses (audio URLs are in English)
    intent_result = await gemini.classify_and_respond(
        user_text=request.text,
        driver_profile=request.driver_profile,
        location=request.current_location,
        session_id=session_id,
        preferred_language="en",  # Always use English
    )

    # Step 1.5: Check if GET_DUTIES has both cities missing, convert to ENTRY
    extracted_params = intent_result.data.get("extracted_params", {}) if intent_result.data else {}
    
    if intent_result.intent == IntentType.GET_DUTIES:
        pickup_city = extracted_params.get("from_city")
        drop_city = extracted_params.get("to_city")
        
        # If BOTH cities are missing, return ENTRY state instead
        pickup_empty = not pickup_city or (isinstance(pickup_city, str) and pickup_city.strip() == "")
        drop_empty = not drop_city or (isinstance(drop_city, str) and drop_city.strip() == "")
        
        if pickup_empty and drop_empty:
            logger.info(
                f"GET_DUTIES with no cities specified for driver {request.driver_profile.id}, "
                f"converting to ENTRY state"
            )
            
            entry_url = audio_config.get_url(
                IntentType.ENTRY,
                request.interaction_count,
                request.is_home
            )
            
            return AssistantResponse(
                session_id=session_id,
                intent=IntentType.ENTRY,
                ui_action=UIAction.ENTRY,
                response_text="",  # No TTS, use audio_url instead
                data=None,
                audio_cached=False,
                cache_key="",
                audio_url=entry_url,
            ), ""

    # Step 2: Fetch data based on intent
    data = None

    if intent_result.intent == IntentType.GET_DUTIES:
        # Extract pickup and drop cities from Gemini's response
        pickup_city = extracted_params.get("from_city")
        drop_city = extracted_params.get("to_city")

        # Validate that cities are in India
        pickup_coordinates = None
        pickup_country = None
        drop_country = None
        used_geo = False
        
        # Check pickup city if provided
        if pickup_city:
            pickup_coordinates, pickup_country = await get_city_coordinates_with_country(pickup_city)
            
            # If geocoding failed, skip geo search but continue with text search
            # This handles cases like "Kamathivada" (misspelled "Kamithi wada")
            if pickup_country is None:
                logger.warning(
                    f"Could not geocode pickup city '{pickup_city}' - "
                    f"skipping geo-based search, will use text-based search only"
                )
                # Don't deny request - Typesense has better fuzzy matching
                pickup_coordinates = None
                used_geo = False
                # Continue to text search (don't return here)
            # Only validate if geocoding succeeded
            elif pickup_country != "IN":
                logger.info(
                    f"Pickup city '{pickup_city}' is in {pickup_country}, not India - denying request"
                )
                
                # Log rejected search to Firebase Analytics
                background_tasks.add_task(
                    get_firebase_service().log_search,
                    driver_id=request.driver_profile.id,
                    pickup_city=pickup_city,
                    drop_city=drop_city,
                    used_geo=False,
                    trips_count=0,
                    leads_count=0,
                )
                
                india_only_url = audio_config.get_url_direct("india_only")
                
                return AssistantResponse(
                    session_id=session_id,
                    success=True,
                    intent=IntentType.END,
                    ui_action=UIAction.SHOW_END,
                    response_text="",  # No TTS, use audio_url instead
                    data=None,
                    audio_cached=False,
                    cache_key="",
                    audio_url=india_only_url,
                ), ""
            
            # City is in India - coordinates are valid for geo search
            if pickup_coordinates:
                used_geo = True
                logger.info(
                    f"Using geo search for pickup city '{pickup_city}' (India): {pickup_coordinates}"
                )
        
        # Check drop city if provided (validate country only if geocoding succeeds)
        if drop_city:
            _, drop_country = await get_city_coordinates_with_country(drop_city)
            
            # If geocoding failed, log warning but continue with text search
            # This handles cases like "Kamathivada" (misspelled "Kamithi wada")
            if drop_country is None:
                logger.warning(
                    f"Could not geocode drop city '{drop_city}' - "
                    f"proceeding with text-based search only"
                )
                # Don't deny request - Typesense has better fuzzy matching
                # Continue execution (no return statement)
            # Only validate if geocoding succeeded
            elif drop_country != "IN":
                logger.info(
                    f"Drop city '{drop_city}' is in {drop_country}, not India - denying request"
                )
                
                # Log rejected search to Firebase Analytics
                background_tasks.add_task(
                    get_firebase_service().log_search,
                    driver_id=request.driver_profile.id,
                    pickup_city=pickup_city,
                    drop_city=drop_city,
                    used_geo=used_geo,
                    trips_count=0,
                    leads_count=0,
                )
                
                india_only_url = audio_config.get_url_direct("india_only")
                
                return AssistantResponse(
                    session_id=session_id,
                    success=True,
                    intent=IntentType.END,
                    ui_action=UIAction.SHOW_END,
                    response_text="",  # No TTS, use audio_url instead
                    data=None,
                    audio_cached=False,
                    cache_key="",
                    audio_url=india_only_url,
                ), ""

        # Run 4 parallel searches: trips (text), trips (geo), leads (text), leads (geo)
        search_tasks = []

        # Text-based searches (always run these)
        search_tasks.append(
            typesense.search_trips(pickup_city=pickup_city, drop_city=drop_city, limit=50)
        )
        search_tasks.append(
            typesense.search_leads(pickup_city=pickup_city, drop_city=drop_city, limit=50)
        )

        # Geo-based searches (only if we have coordinates)
        if pickup_coordinates:
            search_tasks.append(
                typesense.search_trips(
                    pickup_coordinates=pickup_coordinates, 
                    drop_city=drop_city,
                    radius_km=50.0, 
                    limit=50
                )
            )
            search_tasks.append(
                typesense.search_leads(
                    pickup_coordinates=pickup_coordinates, 
                    drop_city=drop_city,
                    radius_km=50.0, 
                    limit=50
                )
            )

        # Execute all searches in parallel
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # Handle exceptions
        trips_text = search_results[0] if not isinstance(search_results[0], Exception) else []
        leads_text = search_results[1] if not isinstance(search_results[1], Exception) else []
        trips_geo = (
            search_results[2]
            if len(search_results) > 2 and not isinstance(search_results[2], Exception)
            else []
        )
        leads_geo = (
            search_results[3]
            if len(search_results) > 3 and not isinstance(search_results[3], Exception)
            else []
        )

        # Merge and deduplicate trips
        all_trips = merge_and_deduplicate([trips_text, trips_geo])

        # Merge and deduplicate leads
        all_leads = merge_and_deduplicate([leads_text, leads_geo])

        # Extract query and counts to root level (for restructured response)
        query_info = {
            "pickup_city": pickup_city,
            "drop_city": drop_city,
            "used_geo": used_geo,
        }

        counts_info = {
            "trips": len(all_trips),
            "leads": len(all_leads),
        }

        # Return raw trips and leads without normalization
        data = {"trips": all_trips, "leads": all_leads}

        logger.info(f"GET_DUTIES: Found {len(all_trips)} trips, {len(all_leads)} leads")

        # Check if no duties were found - return END intent
        if len(all_trips) == 0 and len(all_leads) == 0:
            logger.info("No duties found - returning END intent with no_duty audio")
            
            # Log zero-result search to Firebase Analytics
            background_tasks.add_task(
                get_firebase_service().log_search,
                driver_id=request.driver_profile.id,
                pickup_city=pickup_city,
                drop_city=drop_city,
                used_geo=used_geo,
                trips_count=0,
                leads_count=0,
            )
            
            # Get no_duty audio URL
            no_duty_url = audio_config.get_url_direct("no_duty")
            
            return AssistantResponse(
                session_id=session_id,
                success=True,
                intent=IntentType.END,
                ui_action=UIAction.SHOW_END,
                response_text="",  # No TTS, use audio_url instead
                data=None,
                audio_cached=False,
                cache_key="",
                audio_url=no_duty_url,
            ), ""

        # Log search analytics to Firebase (background task - async, non-blocking)
        background_tasks.add_task(
            get_firebase_service().log_search,
            driver_id=request.driver_profile.id,
            pickup_city=pickup_city,
            drop_city=drop_city,
            used_geo=used_geo,
            trips_count=len(all_trips),
            leads_count=len(all_leads),
        )

    elif intent_result.intent == IntentType.CNG_PUMPS:
        data = {"stations": []}

    elif intent_result.intent == IntentType.PETROL_PUMPS:
        data = {"stations": []}

    elif intent_result.intent == IntentType.PARKING:
        data = {"stations": []}

    elif intent_result.intent == IntentType.NEARBY_DRIVERS:
        data = {"drivers": []}

    elif intent_result.intent == IntentType.TOWING:
        data = {"services": []}

    elif intent_result.intent == IntentType.TOILETS:
        data = {"locations": []}

    elif intent_result.intent == IntentType.TAXI_STANDS:
        data = {"stands": []}

    elif intent_result.intent == IntentType.AUTO_PARTS:
        data = {"shops": []}

    elif intent_result.intent == IntentType.CAR_REPAIR:
        data = {"shops": []}

    elif intent_result.intent == IntentType.HOSPITAL:
        data = {"hospitals": []}

    elif intent_result.intent == IntentType.POLICE_STATION:
        data = {"stations": []}

    elif intent_result.intent == IntentType.END:
        data = {}

    # Step 3: Get audio URL from config (no TTS generation)
    # No cache needed since we're using pre-recorded audio URLs
    audio_url = audio_config.get_url(
        intent_result.intent, 
        request.interaction_count,
        request.is_home
    )

    # Build response with conditional query/counts for GET_DUTIES
    response_kwargs = {
        "session_id": session_id,
        "success": True,
        "intent": intent_result.intent,
        "ui_action": intent_result.ui_action,
        "response_text": "",  # No TTS, use audio_url instead
        "data": data,
        "audio_cached": False,  # Not using cache anymore
        "cache_key": "",  # Empty since no TTS
        "audio_url": audio_url,
    }

    # Add query and counts for GET_DUTIES intent
    if intent_result.intent == IntentType.GET_DUTIES:
        response_kwargs["query"] = query_info
        response_kwargs["counts"] = counts_info

    return AssistantResponse(**response_kwargs), intent_result.response_text


@router.post("/query", response_model=AssistantResponse)
async def query_assistant(
    request: AssistantRequest, background_tasks: BackgroundTasks
) -> AssistantResponse:
    """
    Process a text query from the user.

    Returns JSON with:
    - intent classification
    - UI action for client application to perform
    - relevant data (duties, stations, etc.)
    - cache_key to fetch audio separately

    Use this endpoint when you want to:
    1. Get the response data first
    2. Control the UI based on intent
    3. Then stream audio separately via /audio/{cache_key}
    """
    try:
        response, _ = await _process_intent(request, background_tasks)
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
            yield audio_data[i : i + chunk_size]

    return StreamingResponse(
        audio_stream(),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": "inline",
            "Transfer-Encoding": "chunked",
        },
    )


@router.post("/query-with-audio")
async def query_with_audio(
    request: AssistantRequest, background_tasks: BackgroundTasks
) -> StreamingResponse:
    """
    Process query and return JSON metadata + streamed audio.

    Response format (chunked transfer encoding):
    1. First chunk: JSON metadata (terminated with newline)
    2. Subsequent chunks: Audio data (MP3)

    This is a hybrid approach:
    - REST-like JSON response with all metadata
    - Chunked audio streaming for low latency playback

    Client application should:
    1. Read first line as JSON, parse it for UI actions
    2. Pipe remaining bytes to audio player
    """
    try:
        response, response_text = await _process_intent(request, background_tasks)

        # TTS service no longer needed - using audio_url instead
        # tts = get_tts_service()
        # cache = get_cache_service()
        # cache_key = response.cache_key

        async def stream_response() -> AsyncIterator[bytes]:
            # First, yield JSON metadata
            json_data = response.model_dump_json()
            yield json_data.encode() + b"\n"

            # Client will fetch audio from audio_url directly
            # No audio bytes streamed from server anymore
            # 
            # NOTE: If audio_url is present, client application will fetch it directly
            # The streaming endpoint now only returns JSON metadata
            #
            # --- TTS generation code commented out (no longer needed) ---
            # if response.audio_url:
            #     return
            #
            # # Check cache first
            # cached_audio = await cache.get(cache_key)
            # if cached_audio:
            #     # Stream cached audio in chunks
            #     chunk_size = 4096
            #     for i in range(0, len(cached_audio), chunk_size):
            #         yield cached_audio[i : i + chunk_size]
            # else:
            #     # Generate and cache audio
            #     audio_chunks = []
            #     async for chunk in tts.synthesize_speech_streaming(response_text):
            #         audio_chunks.append(chunk)
            #         yield chunk
            #
            #     # Cache the full audio
            #     full_audio = b"".join(audio_chunks)
            #     await cache.set(cache_key, full_audio)

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
