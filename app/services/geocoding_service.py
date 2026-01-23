"""Geocoding service using Google Maps API."""
import logging
from typing import List, Optional, Tuple
import httpx
from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def get_city_coordinates(city: str) -> Optional[List[float]]:
    """
    Get coordinates for a city using Google Maps Geocoding API.
    
    Args:
        city: City name to geocode
        
    Returns:
        List of [latitude, longitude] or None if geocoding fails
    """
    if not city:
        logger.warning("Empty city name provided for geocoding")
        return None
        
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": city,
        "key": settings.google_maps_api_key,
        "region": "in"  # Bias results toward India
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "OK" and data.get("results"):
                location = data["results"][0]["geometry"]["location"]
                coordinates = [location["lat"], location["lng"]]
                logger.info(f"Geocoded '{city}' to coordinates: {coordinates}")
                return coordinates
            else:
                logger.warning(f"Geocoding failed for '{city}': {data.get('status')}")
                return None
                
    except httpx.HTTPError as e:
        logger.error(f"HTTP error during geocoding for '{city}': {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during geocoding for '{city}': {e}")
        return None


async def get_city_coordinates_with_country(city: str) -> Tuple[Optional[List[float]], Optional[str]]:
    """
    Get coordinates and country code for a city using Google Maps Geocoding API.
    
    This function is used to validate that cities are in India before searching for duties.
    
    Args:
        city: City name to geocode
        
    Returns:
        Tuple of ([latitude, longitude], country_code) where:
        - coordinates: List of [lat, lng] or None if geocoding fails
        - country_code: ISO 2-letter country code (e.g., "IN" for India) or None if geocoding fails
        
    Examples:
        >>> await get_city_coordinates_with_country("Delhi")
        ([28.6139, 77.2090], "IN")
        
        >>> await get_city_coordinates_with_country("New York")
        ([40.7128, -74.0060], "US")
        
        >>> await get_city_coordinates_with_country("InvalidCity123")
        (None, None)
    """
    if not city:
        logger.warning("Empty city name provided for geocoding")
        return None, None
        
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": city,
        "key": settings.google_maps_api_key,
        "region": "in"  # Bias results toward India for ambiguous city names
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "OK" and data.get("results"):
                result = data["results"][0]
                
                # Extract coordinates
                location = result["geometry"]["location"]
                coordinates = [location["lat"], location["lng"]]
                
                # Extract country code from address_components
                country_code = None
                address_components = result.get("address_components", [])
                
                for component in address_components:
                    if "country" in component.get("types", []):
                        country_code = component.get("short_name")
                        break
                
                logger.info(
                    f"Geocoded '{city}' to coordinates: {coordinates}, "
                    f"country: {country_code}"
                )
                return coordinates, country_code
            else:
                logger.warning(f"Geocoding failed for '{city}': {data.get('status')}")
                return None, None
                
    except httpx.HTTPError as e:
        logger.error(f"HTTP error during geocoding for '{city}': {e}")
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error during geocoding for '{city}': {e}")
        return None, None


async def get_multiple_city_coordinates(cities: List[str]) -> dict[str, Optional[List[float]]]:
    """
    Get coordinates for multiple cities concurrently.
    
    Args:
        cities: List of city names to geocode
        
    Returns:
        Dictionary mapping city name to coordinates [lat, lng] or None
    """
    import asyncio
    
    if not cities:
        return {}
    
    # Create tasks for all cities
    tasks = [get_city_coordinates(city) for city in cities]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Map cities to their coordinates
    city_coords = {}
    for city, result in zip(cities, results):
        if isinstance(result, Exception):
            logger.error(f"Exception while geocoding '{city}': {result}")
            city_coords[city] = None
        else:
            city_coords[city] = result
    
    return city_coords
