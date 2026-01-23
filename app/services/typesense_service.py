"""
Typesense service for searching duties, trips, and leads.
"""

import logging
from typing import Optional, List

import typesense

from app.models import Location, DutyInfo
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
        limit: int = 30,
    ) -> List[dict]:
        """
        Search for trips with text-based or geo-based search.
        Filters out trips where customerIsOnboardedAsPartner=true.
        
        Args:
            pickup_city: Pickup city name for text search
            drop_city: Drop city name for text search (use "any" to skip drop filtering)
            pickup_coordinates: [lat, lng] for geo search
            radius_km: Search radius for geo search
            limit: Maximum results to return (default: 30)
            
        Returns:
            List of trip documents
        """
        try:
            # Check if drop_city should be used for filtering
            has_drop_city = drop_city and drop_city.strip() != "" and drop_city.lower() != "any"
            has_pickup_city = pickup_city and pickup_city.strip() != ""
            
            # Always filter out partner trips
            filter_parts = ["customerIsOnboardedAsPartner:=false"]
            
            # Add drop_city filter if valid
            if has_drop_city:
                filter_parts.append(f"customerDropLocationCity:={drop_city}")
            
            # Determine search strategy
            if pickup_coordinates:
                # Geo-based search
                lat, lng = pickup_coordinates
                search_params = {
                    "q": "*",
                    "query_by": "customerPickupLocationCity",
                    "filter_by": f"customerPickupLocationCoordinates:({lat}, {lng}, {radius_km} km) && " + " && ".join(filter_parts),
                    "sort_by": f"customerPickupLocationCoordinates({lat}, {lng}):asc, createdAt:desc",
                    "per_page": limit,
                }
            else:
                # Text-based search with directional matching
                if has_pickup_city:
                    # Pickup city specified - search in pickup field
                    search_params = {
                        "q": pickup_city,
                        "query_by": "customerPickupLocationCity",
                        "filter_by": " && ".join(filter_parts),
                        "sort_by": "createdAt:desc",
                        "per_page": limit,
                    }
                elif has_drop_city:
                    # Only drop specified - search in drop field
                    search_params = {
                        "q": drop_city,
                        "query_by": "customerDropLocationCity",
                        "filter_by": " && ".join(filter_parts),
                        "sort_by": "createdAt:desc",
                        "per_page": limit,
                    }
                else:
                    # No cities specified, return latest
                    search_params = {
                        "q": "*",
                        "filter_by": " && ".join(filter_parts),
                        "sort_by": "createdAt:desc",
                        "per_page": limit,
                    }
            
            results = self.client.collections[self.trips_collection].documents.search(
                search_params
            )
            
            # Extract all documents (filtering now done in Typesense)
            trips = [hit["document"] for hit in results.get("hits", [])]
            
            logger.info(f"Found {len(trips)} trips (pickup_city={pickup_city}, drop_city={drop_city}, coordinates={pickup_coordinates})")
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
        limit: int = 30,
    ) -> List[dict]:
        """
        Search for leads with text-based or geo-based search.
        Filters out leads where status=pending.
        
        Args:
            pickup_city: Pickup city name for text search
            drop_city: Drop city name for text search (use "any" to skip drop filtering)
            pickup_coordinates: [lat, lng] for geo search
            radius_km: Search radius for geo search
            limit: Maximum results to return (default: 30)
            
        Returns:
            List of lead documents
        """
        try:
            # Check if drop_city should be used for filtering
            has_drop_city = drop_city and drop_city.strip() != "" and drop_city.lower() != "any"
            has_pickup_city = pickup_city and pickup_city.strip() != ""
            
            # Always filter out pending leads
            filter_parts = ["status:!=pending"]
            
            # Add drop_city filter if valid
            if has_drop_city:
                filter_parts.append(f"toTxt:={drop_city}")
            
            # Determine search strategy
            if pickup_coordinates:
                # Geo-based search using the location field
                lat, lng = pickup_coordinates
                search_params = {
                    "q": "*",
                    "query_by": "fromTxt",
                    "filter_by": f"location:({lat}, {lng}, {radius_km} km) && " + " && ".join(filter_parts),
                    "sort_by": f"location({lat}, {lng}):asc, createdAt:desc",
                    "per_page": limit,
                }
            else:
                # Text-based search with directional matching
                if has_pickup_city:
                    # Pickup city specified - search in fromTxt field
                    search_params = {
                        "q": pickup_city,
                        "query_by": "fromTxt",
                        "filter_by": " && ".join(filter_parts),
                        "sort_by": "createdAt:desc",
                        "per_page": limit,
                    }
                elif has_drop_city:
                    # Only drop specified - search in toTxt field
                    search_params = {
                        "q": drop_city,
                        "query_by": "toTxt",
                        "filter_by": " && ".join(filter_parts),
                        "sort_by": "createdAt:desc",
                        "per_page": limit,
                    }
                else:
                    # No cities specified, return latest
                    search_params = {
                        "q": "*",
                        "filter_by": " && ".join(filter_parts),
                        "sort_by": "createdAt:desc",
                        "per_page": limit,
                    }
            
            results = self.client.collections[self.leads_collection].documents.search(
                search_params
            )
            
            # Extract all documents (filtering now done in Typesense)
            leads = [hit["document"] for hit in results.get("hits", [])]
            
            logger.info(f"Found {len(leads)} leads (pickup_city={pickup_city}, drop_city={drop_city}, coordinates={pickup_coordinates})")
            return leads
            
        except Exception as e:
            logger.error(f"Error searching leads: {e}")
            return []


# Singleton instance
_typesense_service: Optional[TypesenseService] = None


def get_typesense_service() -> TypesenseService:
    """Get or create the Typesense service singleton."""
    global _typesense_service
    if _typesense_service is None:
        _typesense_service = TypesenseService()
    return _typesense_service
