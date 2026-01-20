"""
Typesense collection setup script.
Run this to create the required collections in Typesense.
"""

import typesense
from config import get_settings


def create_collections():
    """Create Typesense collections for duties and fuel stations."""
    settings = get_settings()
    
    client = typesense.Client({
        "nodes": [{
            "host": settings.typesense_host,
            "port": settings.typesense_port,
            "protocol": settings.typesense_protocol,
        }],
        "api_key": settings.typesense_api_key,
        "connection_timeout_seconds": 5,
    })

    # Duties collection schema
    duties_schema = {
        "name": settings.duties_collection,
        "fields": [
            {"name": "pickup_city", "type": "string", "facet": True},
            {"name": "drop_city", "type": "string", "facet": True},
            {"name": "route", "type": "string"},
            {"name": "fare", "type": "float"},
            {"name": "distance_km", "type": "float"},
            {"name": "vehicle_type", "type": "string", "facet": True},
            {"name": "posted_at", "type": "string", "sort": True},
            {"name": "pickup_location", "type": "geopoint", "optional": True},
            {"name": "drop_location", "type": "geopoint", "optional": True},
        ],
        "default_sorting_field": "posted_at",
    }

    # Fuel stations collection schema
    fuel_stations_schema = {
        "name": settings.fuel_stations_collection,
        "fields": [
            {"name": "name", "type": "string"},
            {"name": "type", "type": "string", "facet": True},  # cng, petrol, diesel, ev
            {"name": "address", "type": "string"},
            {"name": "location", "type": "geopoint"},
            {"name": "rating", "type": "float", "optional": True},
            {"name": "is_open", "type": "bool", "optional": True},
            {"name": "brand", "type": "string", "optional": True, "facet": True},
        ],
    }

    # Create collections (delete if exists for fresh setup)
    for schema in [duties_schema, fuel_stations_schema]:
        try:
            client.collections[schema["name"]].delete()
            print(f"Deleted existing collection: {schema['name']}")
        except typesense.exceptions.ObjectNotFound:
            pass
        
        client.collections.create(schema)
        print(f"Created collection: {schema['name']}")


def seed_sample_data():
    """Seed some sample data for testing."""
    settings = get_settings()
    
    client = typesense.Client({
        "nodes": [{
            "host": settings.typesense_host,
            "port": settings.typesense_port,
            "protocol": settings.typesense_protocol,
        }],
        "api_key": settings.typesense_api_key,
        "connection_timeout_seconds": 5,
    })

    # Sample duties
    sample_duties = [
        {
            "id": "1",
            "pickup_city": "Delhi",
            "drop_city": "Mumbai",
            "route": "Delhi-Mumbai NH48",
            "fare": 45000.0,
            "distance_km": 1420.0,
            "vehicle_type": "Container",
            "posted_at": "2024-01-15T10:30:00Z",
        },
        {
            "id": "2",
            "pickup_city": "Delhi",
            "drop_city": "Jaipur",
            "route": "Delhi-Jaipur NH48",
            "fare": 15000.0,
            "distance_km": 280.0,
            "vehicle_type": "Truck",
            "posted_at": "2024-01-15T11:00:00Z",
        },
        {
            "id": "3",
            "pickup_city": "Mumbai",
            "drop_city": "Pune",
            "route": "Mumbai-Pune Expressway",
            "fare": 8000.0,
            "distance_km": 150.0,
            "vehicle_type": "Mini Truck",
            "posted_at": "2024-01-15T09:00:00Z",
        },
    ]

    # Sample fuel stations (Delhi area)
    sample_stations = [
        {
            "id": "cng1",
            "name": "Indraprastha Gas CNG Station",
            "type": "cng",
            "address": "Ring Road, Near ISBT, Delhi",
            "location": [28.6692, 77.2182],  # [lat, lng]
            "rating": 4.2,
            "is_open": True,
            "brand": "IGL",
        },
        {
            "id": "cng2",
            "name": "Mahanagar Gas CNG Pump",
            "type": "cng",
            "address": "Karol Bagh, Delhi",
            "location": [28.6519, 77.1897],
            "rating": 4.0,
            "is_open": True,
            "brand": "MGL",
        },
        {
            "id": "petrol1",
            "name": "Indian Oil Petrol Pump",
            "type": "petrol",
            "address": "Connaught Place, Delhi",
            "location": [28.6315, 77.2167],
            "rating": 4.3,
            "is_open": True,
            "brand": "Indian Oil",
        },
        {
            "id": "petrol2",
            "name": "HP Petrol Pump",
            "type": "petrol",
            "address": "Nehru Place, Delhi",
            "location": [28.5494, 77.2517],
            "rating": 4.1,
            "is_open": True,
            "brand": "HP",
        },
    ]

    # Import data
    for duty in sample_duties:
        client.collections[settings.duties_collection].documents.upsert(duty)
    print(f"Imported {len(sample_duties)} sample duties")

    for station in sample_stations:
        client.collections[settings.fuel_stations_collection].documents.upsert(station)
    print(f"Imported {len(sample_stations)} sample fuel stations")


if __name__ == "__main__":
    print("Setting up Typesense collections...")
    create_collections()
    print("\nSeeding sample data...")
    seed_sample_data()
    print("\nDone!")
