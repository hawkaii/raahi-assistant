from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class IntentType(str, Enum):
    """Types of intents the assistant can handle."""

    ENTRY = "entry"
    GET_DUTIES = "get_duties"
    CNG_PUMPS = "cng_pumps"
    PETROL_PUMPS = "petrol_pumps"
    PROFILE_VERIFICATION = "profile_verification"
    GENERIC = "generic"


class UIAction(str, Enum):
    """UI actions that client application should perform."""

    ENTRY = "entry"
    SHOW_DUTIES_LIST = "show_duties_list"
    SHOW_CNG_STATIONS = "show_cng_stations"
    SHOW_PETROL_STATIONS = "show_petrol_stations"
    SHOW_VERIFICATION_CHECKLIST = "show_verification_checklist"
    SHOW_DOCUMENT_UPLOAD = "show_document_upload"
    NAVIGATE_TO_PROFILE = "navigate_to_profile"
    SHOW_MAP = "show_map"
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
    is_verified: bool = False
    documents_pending: list[str] = Field(default_factory=list)
    vehicle_type: Optional[str] = None
    vehicle_number: Optional[str] = None
    license_verified: bool = False
    rc_verified: bool = False
    insurance_verified: bool = False


class AssistantRequest(BaseModel):
    """Request from client application to the assistant."""

    text: str  # Transcribed text from speech_to_text
    driver_profile: DriverProfile
    current_location: Location
    session_id: Optional[str] = None  # For conversation context
    preferred_language: str = "hi"  # Default to Hindi
    interaction_count: Optional[int] = None  # Track user interaction count


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


class FuelStation(BaseModel):
    """Fuel station information."""

    id: str
    name: str
    type: Literal["cng", "petrol", "diesel", "ev"]
    address: str
    location: Location
    distance_meters: int
    rating: Optional[float] = None
    is_open: bool = True


class IntentResult(BaseModel):
    """Result of intent classification and data retrieval."""

    intent: IntentType
    response_text: str
    ui_action: UIAction
    data: Optional[dict] = None  # Duties, stations, verification info


class AssistantResponse(BaseModel):
    """REST response with metadata (audio streamed separately via chunked transfer)."""

    session_id: str
    success: bool = True  # Always true for successful 200 responses
    intent: IntentType
    ui_action: UIAction
    response_text: str
    query: Optional[dict] = None  # Query info (for GET_DUTIES)
    counts: Optional[dict] = None  # Counts info (for GET_DUTIES)
    data: Optional[dict] = None
    audio_cached: bool = False
    cache_key: Optional[str] = None
    audio_url: Optional[str] = None  # Direct audio URL (for greeting)
