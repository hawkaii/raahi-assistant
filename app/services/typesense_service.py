"""
Typesense service for searching duties and fuel stations.
"""

import logging
from typing import Optional, List

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
        self.trips_collection = settings.trips_collection
        self.leads_collection = settings.leads_collection

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

    async def search_trips(
        self,
        pickup_city: Optional[str] = None,
        drop_city: Optional[str] = None,
        pickup_coordinates: Optional[List[float]] = None,
        radius_km: float = 50.0,
        limit: int = 50,
    ) -> List[dict]:
        """
        Search for trips with text-based or geo-based search.
        Filters out trips where customerIsOnboardedAsPartner=true.
        
        Args:
            pickup_city: Pickup city name for text search
            drop_city: Drop city name for text search
            pickup_coordinates: [lat, lng] for geo search
            radius_km: Search radius for geo search
            limit: Maximum results to return
            
        Returns:
            List of trip documents
        """
        try:
            # Always filter out partner trips
            filter_parts = ["customerIsOnboardedAsPartner:=false"]
            
            # Determine search strategy
            if pickup_coordinates:
                # Geo-based search
                lat, lng = pickup_coordinates
                search_params = {
                    "q": "*",
                    "query_by": "customerPickupLocationCity",
                    "filter_by": f"customerPickupLocationCoordinates:({lat}, {lng}, {radius_km} km) && " + " && ".join(filter_parts),
                    "sort_by": f"customerPickupLocationCoordinates({lat}, {lng}):asc",
                    "per_page": limit,
                }
            else:
                # Text-based search with strict directional filtering
                # Add city filters for strict direction matching
                if pickup_city and drop_city:
                    # Strict direction: pickup=Mumbai AND drop=Pune
                    filter_parts.append(f"customerPickupLocationCity:={pickup_city}")
                    filter_parts.append(f"customerDropLocationCity:={drop_city}")
                elif pickup_city:
                    # Only pickup specified
                    filter_parts.append(f"customerPickupLocationCity:={pickup_city}")
                elif drop_city:
                    # Only drop specified
                    filter_parts.append(f"customerDropLocationCity:={drop_city}")
                
                search_params = {
                    "q": "*",  # Wildcard query since we're using filters
                    "filter_by": " && ".join(filter_parts),
                    "sort_by": "createdAt:desc",
                    "per_page": limit,
                }
            
            results = self.client.collections[self.trips_collection].documents.search(
                search_params
            )
            
            trips = []
            for hit in results.get("hits", []):
                trips.append(hit["document"])
            
            logger.info(f"Found {len(trips)} trips (pickup_city={pickup_city}, coordinates={pickup_coordinates})")
            return trips
            
        except Exception as e:
            logger.error(f"Error searching trips: {e}")
            return []

    async def search_leads(
        self,
        pickup_city: Optional[str] = None,
        drop_city: Optional[str] = None,
        pickup_coordinates: Optional[List[float]] = None,
        radius_km: float = 50.0,
        limit: int = 50,
    ) -> List[dict]:
        """
        Search for leads with text-based or geo-based search.
        Filters out leads where status=pending.
        
        Args:
            pickup_city: Pickup city name for text search
            drop_city: Drop city name for text search
            pickup_coordinates: [lat, lng] for geo search
            radius_km: Search radius for geo search
            limit: Maximum results to return
            
        Returns:
            List of lead documents
        """
        try:
            # Always filter out pending leads
            filter_parts = ["status:!=pending"]
            
            # Determine search strategy
            if pickup_coordinates:
                # Geo-based search using the location field
                lat, lng = pickup_coordinates
                search_params = {
                    "q": "*",
                    "query_by": "fromTxt",
                    "filter_by": f"location:({lat}, {lng}, {radius_km} km) && " + " && ".join(filter_parts),
                    "sort_by": f"location({lat}, {lng}):asc",
                    "per_page": limit,
                }
            else:
                # Text-based search with strict directional filtering
                # Add city filters for strict direction matching
                if pickup_city and drop_city:
                    # Strict direction: from=Mumbai AND to=Pune
                    filter_parts.append(f"fromTxt:={pickup_city}")
                    filter_parts.append(f"toTxt:={drop_city}")
                elif pickup_city:
                    # Only pickup specified
                    filter_parts.append(f"fromTxt:={pickup_city}")
                elif drop_city:
                    # Only drop specified
                    filter_parts.append(f"toTxt:={drop_city}")
                
                search_params = {
                    "q": "*",  # Wildcard query since we're using filters
                    "filter_by": " && ".join(filter_parts),
                    "sort_by": "createdAt:desc",
                    "per_page": limit,
                }
            
            results = self.client.collections[self.leads_collection].documents.search(
                search_params
            )
            
            leads = []
            for hit in results.get("hits", []):
                leads.append(hit["document"])
            
            logger.info(f"Found {len(leads)} leads (pickup_city={pickup_city}, coordinates={pickup_coordinates})")
            return leads
            
        except Exception as e:
            logger.error(f"Error searching leads: {e}")
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
