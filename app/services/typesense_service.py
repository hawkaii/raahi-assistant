"""
Typesense service for searching duties and fuel stations.
"""

import logging
from typing import Optional

import typesense

from app.models import Location, DutyInfo, FuelStation
from config import get_settings

logger = logging.getLogger(__name__)


class TypesenseService:
    """Service for searching Typesense collections."""

    def __init__(self):
        settings = get_settings()
        self.client = typesense.Client({
            "nodes": [{
                "host": settings.typesense_host,
                "port": settings.typesense_port,
                "protocol": settings.typesense_protocol,
            }],
            "api_key": settings.typesense_api_key,
            "connection_timeout_seconds": 5,
        })
        self.duties_collection = settings.duties_collection
        self.fuel_stations_collection = settings.fuel_stations_collection

    async def search_duties(
        self,
        from_city: Optional[str] = None,
        to_city: Optional[str] = None,
        route: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[DutyInfo]:
        """
        Search for available duties/trips.
        
        Args:
            from_city: Pickup city
            to_city: Drop city
            route: Route name (e.g., "Delhi-Mumbai")
            vehicle_type: Required vehicle type
            limit: Maximum results to return
            
        Returns:
            List of matching duties
        """
        try:
            # Build search query
            query_parts = []
            filter_parts = []

            if from_city:
                query_parts.append(from_city)
            if to_city:
                query_parts.append(to_city)
            if route:
                query_parts.append(route)

            query = " ".join(query_parts) if query_parts else "*"

            if vehicle_type:
                filter_parts.append(f"vehicle_type:={vehicle_type}")

            search_params = {
                "q": query,
                "query_by": "pickup_city,drop_city,route",
                "per_page": limit,
                "sort_by": "posted_at:desc",
            }

            if filter_parts:
                search_params["filter_by"] = " && ".join(filter_parts)

            results = self.client.collections[self.duties_collection].documents.search(
                search_params
            )

            duties = []
            for hit in results.get("hits", []):
                doc = hit["document"]
                duties.append(DutyInfo(
                    id=doc["id"],
                    pickup_city=doc["pickup_city"],
                    drop_city=doc["drop_city"],
                    route=doc.get("route", f"{doc['pickup_city']}-{doc['drop_city']}"),
                    fare=doc["fare"],
                    distance_km=doc["distance_km"],
                    vehicle_type=doc["vehicle_type"],
                    posted_at=doc["posted_at"],
                ))

            return duties

        except Exception as e:
            logger.error(f"Error searching duties: {e}")
            return []

    async def search_nearby_fuel_stations(
        self,
        location: Location,
        fuel_type: str,  # "cng", "petrol", "diesel"
        radius_km: float = 10.0,
        limit: int = 10,
    ) -> list[FuelStation]:
        """
        Search for nearby fuel stations using geo search.
        
        Args:
            location: Current GPS location
            fuel_type: Type of fuel ("cng", "petrol", "diesel")
            radius_km: Search radius in kilometers
            limit: Maximum results to return
            
        Returns:
            List of nearby fuel stations sorted by distance
        """
        try:
            search_params = {
                "q": "*",
                "query_by": "name,address",
                "filter_by": f"location:({location.latitude}, {location.longitude}, {radius_km} km) && type:={fuel_type}",
                "sort_by": f"location({location.latitude}, {location.longitude}):asc",
                "per_page": limit,
            }

            results = self.client.collections[self.fuel_stations_collection].documents.search(
                search_params
            )

            stations = []
            for hit in results.get("hits", []):
                doc = hit["document"]
                geo_distance = hit.get("geo_distance_meters", {}).get("location", 0)
                
                # Handle location format (can be [lat, lng] or {"lat": x, "lng": y})
                loc = doc["location"]
                if isinstance(loc, list):
                    lat, lng = loc[0], loc[1]
                else:
                    lat, lng = loc["lat"], loc["lng"]

                stations.append(FuelStation(
                    id=doc["id"],
                    name=doc["name"],
                    type=doc["type"],
                    address=doc["address"],
                    location=Location(latitude=lat, longitude=lng),
                    distance_meters=geo_distance,
                    rating=doc.get("rating"),
                    is_open=doc.get("is_open", True),
                ))

            return stations

        except Exception as e:
            logger.error(f"Error searching fuel stations: {e}")
            return []


# Singleton instance
_typesense_service: Optional[TypesenseService] = None


def get_typesense_service() -> TypesenseService:
    """Get or create the Typesense service singleton."""
    global _typesense_service
    if _typesense_service is None:
        _typesense_service = TypesenseService()
    return _typesense_service
