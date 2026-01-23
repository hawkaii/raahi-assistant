"""
City name validation utilities.

This module provides utilities for validating that city names are in English
(ASCII characters only) to ensure compatibility with Typesense search.
"""

import logging

logger = logging.getLogger(__name__)


def is_english_text(text: str) -> bool:
    """
    Check if the given text contains only English (ASCII) characters.
    
    Args:
        text: The text to check
        
    Returns:
        bool: True if text is ASCII (English), False otherwise
    """
    if not text:
        return False
    
    try:
        text.encode('ascii')
        return True
    except UnicodeEncodeError:
        return False


def validate_city_name(city: str, field_name: str = "city") -> tuple[bool, str]:
    """
    Validate that a city name is in English.
    
    Args:
        city: The city name to validate
        field_name: The name of the field (for error messages)
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
               error_message is empty string if valid
    """
    # Allow "any" as a special wildcard value
    if city.lower() == "any":
        return True, ""
    
    if not is_english_text(city):
        error_msg = f"{field_name} '{city}' contains non-English characters"
        logger.warning(error_msg)
        return False, error_msg
    
    return True, ""


def validate_city_pair(from_city: str, to_city: str) -> tuple[bool, str]:
    """
    Validate that both from_city and to_city are in English.
    
    Args:
        from_city: The origin city name
        to_city: The destination city name
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
               error_message is empty string if valid
    """
    # Validate from_city
    is_valid, error_msg = validate_city_name(from_city, "from_city")
    if not is_valid:
        return False, error_msg
    
    # Validate to_city
    is_valid, error_msg = validate_city_name(to_city, "to_city")
    if not is_valid:
        return False, error_msg
    
    return True, ""
