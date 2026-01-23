"""Utility functions for merging and deduplicating search results."""
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def merge_and_deduplicate(results_lists: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Merge multiple lists of results and remove duplicates based on 'id' field.
    
    Behavior matches JavaScript mergeAndUnique():
    - Items WITHOUT 'id' field are SKIPPED (not included in results)
    - For duplicates, LAST occurrence wins (later arrays override earlier ones)
    - Order is preserved based on insertion order (Python 3.7+ dict behavior)
    
    This ensures geo search results (which come later) override text search results
    when the same item appears in both, preserving additional data like distance.
    
    Args:
        results_lists: List of result lists to merge
        
    Returns:
        Merged and deduplicated list of results
    """
    id_map = {}  # Use dict instead of set to allow overwriting
    
    for results in results_lists:
        # Safety check: ensure results is a list
        if not isinstance(results, list):
            continue
            
        for item in results:
            item_id = item.get("id")
            if item_id:  # Only process items with an id (skip items without id)
                id_map[item_id] = item  # Last occurrence wins (overwrites previous)
    
    merged = list(id_map.values())
    
    # Safe logging that handles None values in results_lists
    total_input = sum(len(r) for r in results_lists if isinstance(r, list))
    logger.info(f"Merged {total_input} results into {len(merged)} unique items")
    
    return merged


def normalize_trip_to_duty(trip: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a trip document to a duty format.
    
    Args:
        trip: Trip document from Typesense
        
    Returns:
        Normalized duty dictionary
    """
    return {
        "id": trip.get("id"),
        "type": "trip",
        "pickup_city": trip.get("customerPickupLocationCity"),
        "drop_city": trip.get("customerDropLocationCity"),
        "pickup_coordinates": trip.get("customerPickupLocationCoordinates"),
        "drop_coordinates": trip.get("customerDropLocationCoordinates"),
        "trip_type": trip.get("tripType"),
        "status": trip.get("status"),
        "created_at": trip.get("createdAt"),
    }


def normalize_lead_to_duty(lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a lead document to a duty format.
    
    Args:
        lead: Lead document from Typesense
        
    Returns:
        Normalized duty dictionary
    """
    from_info = lead.get("from", {})
    to_info = lead.get("to", {})
    
    return {
        "id": lead.get("id"),
        "type": "lead",
        "pickup_city": from_info.get("city") if isinstance(from_info, dict) else None,
        "drop_city": to_info.get("city") if isinstance(to_info, dict) else None,
        "pickup_coordinates": lead.get("location"),
        "pickup_text": lead.get("fromTxt"),
        "drop_text": lead.get("toTxt"),
        "status": lead.get("status"),
        "created_at": lead.get("createdAt"),
    }


def combine_trips_and_leads(trips: List[Dict[str, Any]], leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Combine trips and leads into a single normalized duties list.
    
    Args:
        trips: List of trip documents
        leads: List of lead documents
        
    Returns:
        Combined and normalized list of duties
    """
    duties = []
    
    # Normalize all trips
    for trip in trips:
        duties.append(normalize_trip_to_duty(trip))
    
    # Normalize all leads
    for lead in leads:
        duties.append(normalize_lead_to_duty(lead))
    
    # Sort by created_at (newest first)
    duties.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    
    logger.info(f"Combined {len(trips)} trips and {len(leads)} leads into {len(duties)} duties")
    return duties
