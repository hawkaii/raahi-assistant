"""Constants and configuration for Raahi Assistant."""

# Audio URLs for different interaction types
GREETING_AUDIO_MAP = {
    "entry": "https://firebasestorage.googleapis.com/v0/b/bwi-cabswalle.appspot.com/o/Raahi%2Fgreeting.wav?alt=media&token=93970efd-eaf5-45bd-850a-ed9cdac4856b",
    "duty_audio": "https://firebasestorage.googleapis.com/v0/b/bwi-cabswalle.appspot.com/o/Raahi%2Fduty.wav?alt=media&token=7a74cbad-8e82-42a5-9c86-b19ee619ef67",
    "cng_pumps": "https://firebasestorage.googleapis.com/v0/b/bwi-cabswalle.appspot.com/o/Raahi%2Fcng.wav?alt=media&token=7b213349-af22-4d3b-84ba-26cd814926ef",
    "petrol_pumps": "https://firebasestorage.googleapis.com/v0/b/bwi-cabswalle.appspot.com/o/Raahi%2Fgreeting.wav?alt=media&token=93970efd-eaf5-45bd-850a-ed9cdac4856b",
    # Future greetings can be added here:
    # "morning_greeting": "https://...",
    # "evening_greeting": "https://...",
    # "returning_user": "https://...",
}

# Default greeting type
DEFAULT_GREETING_TYPE = "entry"
