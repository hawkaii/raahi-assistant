"""Geocoding service using Google Maps API."""
import logging
from typing import List, Optional
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
        "key": settings.google_maps_api_key
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
