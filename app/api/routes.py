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
from app.services.geocoding_service import get_city_coordinates
from app.utils.merge_utils import merge_and_deduplicate, combine_trips_and_leads
from app.constants import GREETING_AUDIO_MAP, DEFAULT_GREETING_TYPE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])


def extract_city_names(text: str) -> list[str]:
    """
    Extract city names from text in the order they appear.
    
    This is a simple pattern-based extraction for common Indian city names.
    Can be enhanced with NER (Named Entity Recognition) for better accuracy.
    """
    # Common Indian cities (can be expanded)
    indian_cities = [
        "mumbai", "delhi", "bangalore", "bengaluru", "hyderabad", "chennai", "kolkata",
        "pune", "ahmedabad", "surat", "jaipur", "lucknow", "kanpur", "nagpur",
        "indore", "thane", "bhopal", "visakhapatnam", "pimpri", "patna",
        "vadodara", "ghaziabad", "ludhiana", "agra", "nashik", "faridabad",
        "meerut", "rajkot", "kalyan", "vasai", "varanasi", "srinagar",
        "aurangabad", "dhanbad", "amritsar", "navi mumbai", "allahabad", "prayagraj",
        "ranchi", "howrah", "coimbatore", "jabalpur", "gwalior", "vijayawada",
        "jodhpur", "madurai", "raipur", "kota", "chandigarh", "guwahati",
        "solapur", "hubli", "mysore", "mysuru", "tiruchirappalli", "tiruppur",
        "moradabad", "bareilly", "aligarh", "jalandhar", "bhubaneswar", "salem",
        "warangal", "guntur", "bhiwandi", "saharanpur", "gorakhpur", "bikaner",
        "amravati", "noida", "jamshedpur", "bhilai", "cuttack", "firozabad",
        "kochi", "cochin", "nellore", "bhavnagar", "dehradun", "durgapur",
        "asansol", "rourkela", "nanded", "kolhapur", "ajmer", "akola",
        "gulbarga", "jamnagar", "ujjain", "loni", "siliguri", "jhansi",
        "ulhasnagar", "jammu", "sangli", "mangalore", "erode", "belgaum",
        "ambattur", "tirunelveli", "malegaon", "gaya", "thiruvananthapuram",
        "udaipur", "maheshtala", "davanagere", "kozhikode", "calicut", "akola"
    ]
    
    text_lower = text.lower()
    found_cities = []
    
    # Find all city matches with their positions
    city_matches = []
    for city in indian_cities:
        # Use word boundaries to match whole words
        match = re.search(r'\b' + re.escape(city) + r'\b', text_lower)
        if match:
            # Store (position, city_name)
            city_matches.append((match.start(), city.title()))
    
    # Sort by position in text (ascending order)
    city_matches.sort(key=lambda x: x[0])
    
    # Remove duplicates while preserving order
    seen = set()
    unique_cities = []
    for _, city in city_matches:
        if city.lower() not in seen:
            seen.add(city.lower())
            unique_cities.append(city)
    
    return unique_cities


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

    # Check for entry state (either interaction_count present OR empty text)
    if (request.interaction_count is not None 
        or request.text.strip() == ""):
        greeting_url = GREETING_AUDIO_MAP.get(DEFAULT_GREETING_TYPE)
        
        return AssistantResponse(
            session_id=session_id,
            intent=IntentType.ENTRY,
            ui_action=UIAction.ENTRY,
            response_text="",
            data=None,
            audio_cached=False,
            cache_key="",
            audio_url=greeting_url
        ), ""

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
        # Extract city names from the user's text
        city_names = extract_city_names(request.text)
        
        # Extract pickup and drop cities from Gemini's response
        pickup_city = extracted_params.get("from_city")
        drop_city = extracted_params.get("to_city")
        
        # Try to get coordinates for pickup city if available
        pickup_coordinates = None
        used_geo = False
        if pickup_city:
            pickup_coordinates = await get_city_coordinates(pickup_city)
            if pickup_coordinates:
                used_geo = True
                logger.info(f"Using geo search for pickup city '{pickup_city}': {pickup_coordinates}")
        
        # Run 4 parallel searches: trips (text), trips (geo), leads (text), leads (geo)
        search_tasks = []
        
        # Text-based searches (always run these)
        search_tasks.append(typesense.search_trips(
            pickup_city=pickup_city,
            drop_city=drop_city,
            limit=50
        ))
        search_tasks.append(typesense.search_leads(
            pickup_city=pickup_city,
            drop_city=drop_city,
            limit=50
        ))
        
        # Geo-based searches (only if we have coordinates)
        if pickup_coordinates:
            search_tasks.append(typesense.search_trips(
                pickup_coordinates=pickup_coordinates,
                radius_km=50.0,
                limit=50
            ))
            search_tasks.append(typesense.search_leads(
                pickup_coordinates=pickup_coordinates,
                radius_km=50.0,
                limit=50
            ))
        
        # Execute all searches in parallel
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # Handle exceptions
        trips_text = search_results[0] if not isinstance(search_results[0], Exception) else []
        leads_text = search_results[1] if not isinstance(search_results[1], Exception) else []
        trips_geo = search_results[2] if len(search_results) > 2 and not isinstance(search_results[2], Exception) else []
        leads_geo = search_results[3] if len(search_results) > 3 and not isinstance(search_results[3], Exception) else []
        
        # Merge and deduplicate trips
        all_trips = merge_and_deduplicate([trips_text, trips_geo])
        
        # Merge and deduplicate leads
        all_leads = merge_and_deduplicate([leads_text, leads_geo])
        
        # Combine trips and leads into normalized duties format
        duties = combine_trips_and_leads(all_trips, all_leads)
        
        # Build response data
        data = {
            "duties": duties,
            "city_names": city_names,
            "query": {
                "pickup_city": pickup_city,
                "drop_city": drop_city,
                "used_geo": used_geo,
            },
            "counts": {
                "trips": len(all_trips),
                "leads": len(all_leads),
                "total": len(duties)
            }
        }
        
        logger.info(f"GET_DUTIES: Found {len(all_trips)} trips, {len(all_leads)} leads, {len(duties)} total duties")

    elif intent_result.intent == IntentType.CNG_PUMPS:
        stations = await typesense.search_nearby_fuel_stations(
            location=request.current_location,
            fuel_type="cng",
        )
        data = {"stations": [s.model_dump() for s in stations]}

    elif intent_result.intent == IntentType.PETROL_PUMPS:
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

    # Step 3: Check if audio is cached and determine audio_url
    cache_key = tts.get_cache_key(intent_result.response_text)
    audio_cached = await cache.exists(cache_key)
    
    # Set audio_url for GET_DUTIES intent
    audio_url = None
    if intent_result.intent == IntentType.GET_DUTIES:
        audio_url = GREETING_AUDIO_MAP.get("duty_audio")

    return AssistantResponse(
        session_id=session_id,
        intent=intent_result.intent,
        ui_action=intent_result.ui_action,
        response_text=intent_result.response_text,
        data=data,
        audio_cached=audio_cached,
        cache_key=cache_key,
        audio_url=audio_url,
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

            # If audio_url is present (entry state), Flutter will fetch it directly
            # Don't stream any audio bytes - Flutter handles the greeting URL
            if response.audio_url:
                return

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
