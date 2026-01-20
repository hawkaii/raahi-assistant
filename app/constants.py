"""Constants and configuration for Raahi Assistant."""

# Greeting audio URLs for different interaction types
# Future: Can add more greeting types (morning, evening, returning_user, etc.)
GREETING_AUDIO_MAP = {
    "entry": "https://firebasestorage.googleapis.com/v0/b/bwi-cabswalle.appspot.com/o/Raahi%2Fgreeting.wav?alt=media&token=93970efd-eaf5-45bd-850a-ed9cdac4856b",
    # Future greetings can be added here:
    # "morning_greeting": "https://...",
    # "evening_greeting": "https://...",
    # "returning_user": "https://...",
}

# Default greeting type
DEFAULT_GREETING_TYPE = "entry"
