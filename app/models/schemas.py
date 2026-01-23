from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class IntentType(str, Enum):
    """Types of intents the assistant can handle."""

    ENTRY = "entry"
    GET_DUTIES = "get_duties"
    CNG_PUMPS = "cng_pumps"
    PARKING = "parking"
    PETROL_PUMPS = "petrol_pumps"
    NEARBY_DRIVERS = "nearby_drivers"
    TOWING = "towing"
    TOILETS = "toilets"
    TAXI_STANDS = "taxi_stands"
    AUTO_PARTS = "auto_parts"
    CAR_REPAIR = "car_repair"
    HOSPITAL = "hospital"
    POLICE_STATION = "police_station"
    END = "end"
    GENERIC = "generic"


class UIAction(str, Enum):
    """UI actions that client application should perform."""

    ENTRY = "entry"
    SHOW_DUTIES_LIST = "show_duties_list"
    SHOW_CNG_STATIONS = "show_cng_stations"
    SHOW_PETROL_STATIONS = "show_petrol_stations"
    SHOW_PARKING = "show_parking"
    SHOW_NEARBY_DRIVERS = "show_nearby_drivers"
    SHOW_TOWING = "show_towing"
    SHOW_TOILETS = "show_toilets"
    SHOW_TAXI_STANDS = "show_taxi_stands"
    SHOW_AUTO_PARTS = "show_auto_parts"
    SHOW_CAR_REPAIR = "show_car_repair"
    SHOW_HOSPITAL = "show_hospital"
    SHOW_POLICE_STATION = "show_police_station"
    SHOW_MAP = "show_map"
    SHOW_END = "show_end"
    NONE = "none"


class Location(BaseModel):
    """Geographic location."""

    latitude: float
    longitude: float


class DriverProfile(BaseModel):
    """Driver profile information sent with each request."""

    id: str
    name: str
    phone: str
    vehicle_type: Optional[str] = None
    vehicle_number: Optional[str] = None


class AssistantRequest(BaseModel):
    """Request from client application to the assistant."""

    text: str  # Transcribed text from speech_to_text
    driver_profile: DriverProfile
    current_location: Location
    session_id: Optional[str] = None  # For conversation context
    preferred_language: str = "hi"  # Default to Hindi
    interaction_count: Optional[int] = None  # Track user interaction count
    is_home: bool = True
    chip_click: Optional[str] = None  # UI chip click type (e.g., "find")


class DutyInfo(BaseModel):
    """Duty/trip information."""

    id: str
    pickup_city: str
    drop_city: str
    route: str
    fare: float
    distance_km: float
    vehicle_type: str
    posted_at: str


class IntentResult(BaseModel):
    """Result of intent classification and data retrieval."""

    intent: IntentType
    response_text: str
    ui_action: UIAction
    data: Optional[dict] = None  # Duties, stations, etc.


class AssistantResponse(BaseModel):
    """REST response with metadata (audio streamed separately via chunked transfer)."""

    session_id: str
    success: bool = True  # Always true for successful 200 responses
    intent: IntentType
    ui_action: UIAction
    response_text: str  # Deprecated: Always empty, use audio_url instead
    query: Optional[dict] = None  # Query info (for GET_DUTIES)
    counts: Optional[dict] = None  # Counts info (for GET_DUTIES)
    data: Optional[dict] = None
    audio_cached: bool = False
    cache_key: Optional[str] = None
    audio_url: Optional[str] = None  # Direct audio URL (for greeting)
