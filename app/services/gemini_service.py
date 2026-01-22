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

# Language-specific system prompts
SYSTEM_PROMPT_HINDI = """आप Raahi Assistant हैं, भारत में ट्रक ड्राइवरों के लिए एक सहायक AI असिस्टेंट।
आप ड्राइवरों की मदद करते हैं:
1. ड्यूटी/ट्रिप खोजने में (शहरों के बीच माल परिवहन)
2. नजदीकी CNG पंप ढूंढने में
3. नजदीकी पेट्रोल/डीजल पंप ढूंढने में
4. नजदीकी पार्किंग स्थान ढूंढने में
5. प्रोफाइल वेरिफिकेशन में मदद करने में

महत्वपूर्ण: आपको हमेशा वैध JSON फॉर्मेट में जवाब देना है इन फील्ड्स के साथ:
- intent: इनमें से एक "get_duties", "cng_pumps", "petrol_pumps", "parking", "profile_verification", "generic"
- ui_action: इनमें से एक "show_duties_list", "show_cng_stations", "show_petrol_stations", "show_parking", "show_verification_checklist", "show_document_upload", "navigate_to_profile", "show_map", "none"
- response_text: ड्राइवर को बोलने के लिए एक मित्रवत, संक्षिप्त जवाब (संक्षिप्त रखें, 1-2 वाक्य) - यह हमेशा हिंदी में होना चाहिए
- extracted_params: शहर के नाम, रूट आदि जैसे निकाले गए पैरामीटर

ड्राइवर के बारे में संदर्भ प्रदान किया जाएगा। इसका उपयोग व्यक्तिगत प्रतिक्रियाएं देने के लिए करें।

उदाहरण:
User: "Delhi se Mumbai ka duty chahiye"
Response: {"intent": "get_duties", "ui_action": "show_duties_list", "response_text": "दिल्ली से मुंबई के लिए उपलब्ध ड्यूटी देख रहा हूं।", "extracted_params": {"from_city": "Delhi", "to_city": "Mumbai"}}

User: "Paas mein CNG pump kahan hai?"
Response: {"intent": "cng_pumps", "ui_action": "show_cng_stations", "response_text": "आपके पास के CNG स्टेशन ढूंढ रहा हूं।", "extracted_params": {}}

User: "Parking kahan hai?"
Response: {"intent": "parking", "ui_action": "show_parking", "response_text": "आपके पास के पार्किंग स्थान ढूंढ रहा हूं।", "extracted_params": {}}

User: "Mera profile verify kaise hoga?"
Response: {"intent": "profile_verification", "ui_action": "show_verification_checklist", "response_text": "मैं आपको प्रोफाइल वेरिफिकेशन में मदद करता हूं।", "extracted_params": {}}

User: "क्या कोई ड्यूटी है?"
Response: {"intent": "get_duties", "ui_action": "show_duties_list", "response_text": "मैं आपके लिए ड्यूटी ढूंढ रहा हूं।", "extracted_params": {}}

महत्वपूर्ण: response_text हमेशा स्पष्ट हिंदी (देवनागरी लिपि) में होना चाहिए। सहायक और संक्षिप्त रहें।
"""

SYSTEM_PROMPT_ENGLISH = """You are Raahi Assistant, a helpful AI assistant for truck drivers in India.
You help drivers with:
1. Finding duties/trips (cargo to transport between cities)
2. Finding nearby CNG pumps
3. Finding nearby petrol/diesel pumps
4. Finding nearby parking spaces
5. Helping with profile verification

IMPORTANT: You must respond in valid JSON format with these fields:
- intent: one of "get_duties", "cng_pumps", "petrol_pumps", "parking", "profile_verification", "generic"
- ui_action: one of "show_duties_list", "show_cng_stations", "show_petrol_stations", "show_parking", "show_verification_checklist", "show_document_upload", "navigate_to_profile", "show_map", "none"
- response_text: A friendly, concise response to speak to the driver (keep it brief, 1-2 sentences)
- extracted_params: Any extracted parameters like city names, routes, etc.

Context about the driver will be provided. Use it to give personalized responses.

Examples:
User: "Find me a duty from Delhi to Mumbai"
Response: {"intent": "get_duties", "ui_action": "show_duties_list", "response_text": "Looking for available duties from Delhi to Mumbai.", "extracted_params": {"from_city": "Delhi", "to_city": "Mumbai"}}

User: "Where is the nearest CNG pump?"
Response: {"intent": "cng_pumps", "ui_action": "show_cng_stations", "response_text": "Finding nearby CNG stations for you.", "extracted_params": {}}

User: "Where can I park?"
Response: {"intent": "parking", "ui_action": "show_parking", "response_text": "Finding nearby parking spaces for you.", "extracted_params": {}}

Be helpful and concise.
"""


class GeminiService:
    """Service for interacting with Vertex AI Gemini."""

    def __init__(self):
        settings = get_settings()
        vertexai.init(project=settings.gcp_project_id, location=settings.gcp_location)
        self.settings = settings
        # Default to Hindi system prompt
        self.model = GenerativeModel(
            settings.gemini_model,
            system_instruction=SYSTEM_PROMPT_HINDI,
        )
        self._sessions: dict[str, list[Content]] = {}
        self._current_language = "hi"  # Default to Hindi
    
    def _get_model_for_language(self, language: str) -> GenerativeModel:
        """Get or create a model with the appropriate language prompt."""
        if language == "hi":
            return GenerativeModel(
                self.settings.gemini_model,
                system_instruction=SYSTEM_PROMPT_HINDI,
            )
        else:
            return GenerativeModel(
                self.settings.gemini_model,
                system_instruction=SYSTEM_PROMPT_ENGLISH,
            )

    def _build_context(
        self, driver_profile: DriverProfile, location: Location
    ) -> str:
        """Build context string from driver profile and location."""
        pending_docs = ", ".join(driver_profile.documents_pending) if driver_profile.documents_pending else "None"
        
        return f"""
Driver Context:
- Name: {driver_profile.name}
- Verified: {driver_profile.is_verified}
- Vehicle: {driver_profile.vehicle_type or 'Not set'} ({driver_profile.vehicle_number or 'Not set'})
- License Verified: {driver_profile.license_verified}
- RC Verified: {driver_profile.rc_verified}
- Insurance Verified: {driver_profile.insurance_verified}
- Pending Documents: {pending_docs}
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
            user_text: The transcribed text from user's speech
            driver_profile: Driver's profile information
            location: Current GPS location
            session_id: Optional session ID for conversation context
            preferred_language: Language for response (default: "hi" for Hindi)
            
        Returns:
            IntentResult with classified intent, response, and UI action
        """
        try:
            # Get model with appropriate language prompt
            model = self._get_model_for_language(preferred_language)
            
            # Build the prompt with context
            context = self._build_context(driver_profile, location)
            full_prompt = f"{context}\n\nUser: {user_text}"

            # Get or create conversation history
            history = self._sessions.get(session_id, []) if session_id else []

            # Generate response
            chat = model.start_chat(history=history)
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

            # Default fallback messages in Hindi
            default_responses = {
                "hi": "मैं समझ नहीं पाया। क्या आप फिर से बोल सकते हैं?",
                "en": "I didn't understand. Can you say that again?"
            }
            
            return IntentResult(
                intent=IntentType(parsed.get("intent", "generic")),
                response_text=parsed.get("response_text", default_responses.get(preferred_language, default_responses["hi"])),
                ui_action=UIAction(parsed.get("ui_action", "none")),
                data={"extracted_params": parsed.get("extracted_params", {})},
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            fallback_msg = "मैं आपकी मदद करने के लिए यहां हूं। क्या आप फिर से बोल सकते हैं?" if preferred_language == "hi" else "I'm here to help. Can you say that again?"
            return IntentResult(
                intent=IntentType.GENERIC,
                response_text=fallback_msg,
                ui_action=UIAction.NONE,
                data=None,
            )
        except Exception as e:
            logger.error(f"Error in Gemini service: {e}")
            error_msg = "कुछ तकनीकी समस्या है। कृपया थोड़ी देर बाद प्रयास करें।" if preferred_language == "hi" else "There's a technical problem. Please try again later."
            return IntentResult(
                intent=IntentType.GENERIC,
                response_text=error_msg,
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
