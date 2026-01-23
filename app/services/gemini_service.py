"""
Gemini service for intent classification and response generation.
Uses Vertex AI Gemini for understanding user queries and generating responses.
"""

import json
import logging
from typing import Optional

import vertexai
from vertexai.generative_models import GenerativeModel, Part, Content

from app.models import (
    IntentType,
    UIAction,
    DriverProfile,
    Location,
    IntentResult,
)
from config import get_settings

logger = logging.getLogger(__name__)

# Multilingual system prompt - accepts any language, responds in English only
SYSTEM_PROMPT_MULTILINGUAL = """You are Raahi Assistant, a helpful AI assistant for truck drivers in India.

IMPORTANT LANGUAGE INSTRUCTION: Users may speak to you in ANY language (Hindi, English, Tamil, Marathi, etc.), but you MUST ALWAYS respond with response_text in ENGLISH only.

You help drivers with:
1. Finding duties/trips (cargo to transport between cities)
2. Finding nearby CNG/petrol pumps
3. Finding nearby parking spaces
4. Finding nearby drivers
5. Finding towing services
6. Finding toilets/restrooms
7. Finding taxi stands
8. Finding auto parts shops
9. Finding car repair shops
10. Finding hospitals
11. Finding police stations

IMPORTANT: You must respond in valid JSON format with these fields:
- intent: one of "get_duties", "cng_pumps", "petrol_pumps", "parking", "nearby_drivers", "towing", "toilets", "taxi_stands", "auto_parts", "car_repair", "hospital", "police_station", "end", "generic"
- ui_action: one of "show_duties_list", "show_cng_stations", "show_petrol_stations", "show_parking", "show_nearby_drivers", "show_towing", "show_toilets", "show_taxi_stands", "show_auto_parts", "show_car_repair", "show_hospital", "show_police_station", "show_end", "show_map", "none"
- response_text: A friendly, concise response in ENGLISH to speak to the driver (keep it brief, 1-2 sentences)
- extracted_params: Any extracted parameters like city names, routes, etc.

Context about the driver will be provided. Use it to give personalized responses.

Examples (showing multilingual input with English responses):
User: "Delhi se Mumbai ka duty chahiye"
Response: {"intent": "get_duties", "ui_action": "show_duties_list", "response_text": "Looking for available duties from Delhi to Mumbai.", "extracted_params": {"from_city": "Delhi", "to_city": "Mumbai"}}

User: "Find me a duty from Delhi to Mumbai"
Response: {"intent": "get_duties", "ui_action": "show_duties_list", "response_text": "Looking for available duties from Delhi to Mumbai.", "extracted_params": {"from_city": "Delhi", "to_city": "Mumbai"}}

User: "mumbai"
Response: {"intent": "get_duties", "ui_action": "show_duties_list", "response_text": "Looking for duties from Mumbai.", "extracted_params": {"from_city": "Mumbai"}}

User: "Delhi"
Response: {"intent": "get_duties", "ui_action": "show_duties_list", "response_text": "Looking for duties from Delhi.", "extracted_params": {"from_city": "Delhi"}}

User: "मुंबई"
Response: {"intent": "get_duties", "ui_action": "show_duties_list", "response_text": "Looking for duties from Mumbai.", "extracted_params": {"from_city": "Mumbai"}}

User: "पुणे"
Response: {"intent": "get_duties", "ui_action": "show_duties_list", "response_text": "Looking for duties from Pune.", "extracted_params": {"from_city": "Pune"}}

User: "Paas mein CNG pump kahan hai?"
Response: {"intent": "cng_pumps", "ui_action": "show_cng_stations", "response_text": "Finding nearby CNG stations for you.", "extracted_params": {}}

User: "Where is the nearest CNG pump?"
Response: {"intent": "cng_pumps", "ui_action": "show_cng_stations", "response_text": "Finding nearby CNG stations for you.", "extracted_params": {}}

User: "Parking kahan hai?"
Response: {"intent": "parking", "ui_action": "show_parking", "response_text": "Looking for nearby parking spaces.", "extracted_params": {}}

User: "Where can I park?"
Response: {"intent": "parking", "ui_action": "show_parking", "response_text": "Looking for nearby parking spaces.", "extracted_params": {}}

User: "Paas mein dusre driver hai?"
Response: {"intent": "nearby_drivers", "ui_action": "show_nearby_drivers", "response_text": "Finding nearby drivers for you.", "extracted_params": {}}

User: "Are there any drivers nearby?"
Response: {"intent": "nearby_drivers", "ui_action": "show_nearby_drivers", "response_text": "Finding nearby drivers for you.", "extracted_params": {}}

User: "Towing service chahiye"
Response: {"intent": "towing", "ui_action": "show_towing", "response_text": "Finding nearby towing services.", "extracted_params": {}}

User: "I need a towing service"
Response: {"intent": "towing", "ui_action": "show_towing", "response_text": "Finding nearby towing services.", "extracted_params": {}}

User: "Toilet kahan hai?"
Response: {"intent": "toilets", "ui_action": "show_toilets", "response_text": "Finding nearby restrooms.", "extracted_params": {}}

User: "Where is the toilet?"
Response: {"intent": "toilets", "ui_action": "show_toilets", "response_text": "Finding nearby restrooms.", "extracted_params": {}}

User: "Taxi stand kahan hai?"
Response: {"intent": "taxi_stands", "ui_action": "show_taxi_stands", "response_text": "Finding nearby taxi stands.", "extracted_params": {}}

User: "Where is the taxi stand?"
Response: {"intent": "taxi_stands", "ui_action": "show_taxi_stands", "response_text": "Finding nearby taxi stands.", "extracted_params": {}}

User: "Auto parts ki dukaan dikhao"
Response: {"intent": "auto_parts", "ui_action": "show_auto_parts", "response_text": "Finding nearby auto parts shops.", "extracted_params": {}}

User: "Show me auto parts shops"
Response: {"intent": "auto_parts", "ui_action": "show_auto_parts", "response_text": "Finding nearby auto parts shops.", "extracted_params": {}}

User: "Gaadi repair karwani hai"
Response: {"intent": "car_repair", "ui_action": "show_car_repair", "response_text": "Finding nearby car repair shops.", "extracted_params": {}}

User: "I need to repair my vehicle"
Response: {"intent": "car_repair", "ui_action": "show_car_repair", "response_text": "Finding nearby car repair shops.", "extracted_params": {}}

User: "Hospital kahan hai?"
Response: {"intent": "hospital", "ui_action": "show_hospital", "response_text": "Finding nearby hospitals.", "extracted_params": {}}

User: "Where is the hospital?"
Response: {"intent": "hospital", "ui_action": "show_hospital", "response_text": "Finding nearby hospitals.", "extracted_params": {}}

User: "Police station dikhao"
Response: {"intent": "police_station", "ui_action": "show_police_station", "response_text": "Finding nearby police stations.", "extracted_params": {}}

User: "Show me the police station"
Response: {"intent": "police_station", "ui_action": "show_police_station", "response_text": "Finding nearby police stations.", "extracted_params": {}}

User: "Ok, thank you"
Response: {"intent": "end", "ui_action": "show_end", "response_text": "Thank you! Safe journey.", "extracted_params": {}}

User: "धन्यवाद"
Response: {"intent": "end", "ui_action": "show_end", "response_text": "You're welcome! Stay safe.", "extracted_params": {}}

User: "ठीक है, बस"
Response: {"intent": "end", "ui_action": "show_end", "response_text": "Happy to help. See you later.", "extracted_params": {}}

User: "Ok, that's all"
Response: {"intent": "end", "ui_action": "show_end", "response_text": "Happy to help. See you later.", "extracted_params": {}}

User: "क्या कोई ड्यूटी है?"
Response: {"intent": "get_duties", "ui_action": "show_duties_list", "response_text": "Looking for duties for you.", "extracted_params": {}}

User: "Are there any duties?"
Response: {"intent": "get_duties", "ui_action": "show_duties_list", "response_text": "Looking for duties for you.", "extracted_params": {}}

IMPORTANT: Always respond with response_text in clear ENGLISH regardless of the input language. Be helpful and concise.
"""


class GeminiService:
    """Service for interacting with Vertex AI Gemini."""

    def __init__(self):
        settings = get_settings()
        vertexai.init(project=settings.gcp_project_id, location=settings.gcp_location)
        self.settings = settings
        # Use multilingual prompt - accepts any language, responds in English
        self.model = GenerativeModel(
            settings.gemini_model,
            system_instruction=SYSTEM_PROMPT_MULTILINGUAL,
        )
        self._sessions: dict[str, list[Content]] = {}

    def _build_context(
        self, driver_profile: DriverProfile, location: Location
    ) -> str:
        """Build context string from driver profile and location."""
        return f"""
Driver Context:
- Name: {driver_profile.name}
- Vehicle: {driver_profile.vehicle_type or 'Not set'} ({driver_profile.vehicle_number or 'Not set'})
- Current Location: ({location.latitude}, {location.longitude})
"""

    async def classify_and_respond(
        self,
        user_text: str,
        driver_profile: DriverProfile,
        location: Location,
        session_id: Optional[str] = None,
        preferred_language: str = "hi",
    ) -> IntentResult:
        """
        Classify user intent and generate response using Gemini.
        
        Args:
            user_text: The transcribed text from user's speech (can be in any language)
            driver_profile: Driver's profile information
            location: Current GPS location
            session_id: Optional session ID for conversation context
            preferred_language: Language preference (deprecated - all responses are in English)
            
        Returns:
            IntentResult with classified intent, response (in English), and UI action
        """
        try:
            # Build the prompt with context
            context = self._build_context(driver_profile, location)
            full_prompt = f"{context}\n\nUser: {user_text}"

            # Get or create conversation history
            history = self._sessions.get(session_id, []) if session_id else []

            # Generate response using multilingual model
            chat = self.model.start_chat(history=history)
            response = await chat.send_message_async(full_prompt)

            # Parse the JSON response
            response_text = response.text.strip()
            
            # Handle markdown code blocks if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1])

            parsed = json.loads(response_text)

            # Update session history
            if session_id:
                self._sessions[session_id] = chat.history
            
            return IntentResult(
                intent=IntentType(parsed.get("intent", "generic")),
                response_text=parsed.get("response_text", "I didn't understand. Can you say that again?"),
                ui_action=UIAction(parsed.get("ui_action", "none")),
                data={"extracted_params": parsed.get("extracted_params", {})},
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            return IntentResult(
                intent=IntentType.GENERIC,
                response_text="I'm here to help. Can you say that again?",
                ui_action=UIAction.NONE,
                data=None,
            )
        except Exception as e:
            logger.error(f"Error in Gemini service: {e}")
            return IntentResult(
                intent=IntentType.GENERIC,
                response_text="There's a technical problem. Please try again later.",
                ui_action=UIAction.NONE,
                data=None,
            )

    def clear_session(self, session_id: str) -> None:
        """Clear conversation history for a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]


# Singleton instance
_gemini_service: Optional[GeminiService] = None


def get_gemini_service() -> GeminiService:
    """Get or create the Gemini service singleton."""
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service
