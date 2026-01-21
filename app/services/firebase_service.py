"""
Firebase Firestore service for analytics logging.

This service logs search analytics to Firestore to track driver search behavior,
matching the Node.js implementation structure.

Firestore Path: drivers/{driver_id}/raahiSearch/{auto_id}
"""

import logging
from typing import Optional
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import AsyncClient
from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class FirebaseService:
    """Service for logging search analytics to Firestore."""

    def __init__(self):
        self._client: Optional[AsyncClient] = None
        self._initialized = False

    async def initialize(self):
        """Initialize Firebase Admin SDK (async)."""
        if self._initialized:
            return

        try:
            if not settings.firebase_credentials_path:
                logger.warning(
                    "Firebase credentials path not configured - analytics logging disabled"
                )
                return

            # Initialize Firebase Admin SDK
            cred = credentials.Certificate(settings.firebase_credentials_path)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)

            # Get async Firestore client
            self._initialized = True
            self._client = firestore.AsyncClient()

            # Log Firebase initialization details (without exposing credentials)
            logger.info(
                f"Firebase Firestore initialized successfully - "
                f"Project: {cred.project_id}, "
                f"Service Account: {cred.service_account_email}"
            )

        except Exception as e:
            logger.error(
                f"Failed to initialize Firebase: {str(e)[:100]}"
            )  # Limit error message length
            self._client = None

    async def log_search(
        self,
        driver_id: str,
        pickup_city: Optional[str],
        drop_city: Optional[str],
        used_geo: bool,
        trips_count: int,
        leads_count: int,
    ):
        """
        Log search analytics to Firestore.

        Firestore Path: drivers/{driver_id}/raahiSearch/{auto_id}

        Document structure matches Node.js implementation:
        {
            pickup_city: "Ambala",
            drop_city: "Chandigarh",
            used_geo: true,
            trips_count: 35,
            leads_count: 30,
            timestamp: <Firestore timestamp>
        }

        Args:
            driver_id: Driver ID from driver_profile
            pickup_city: Pickup city name (or None)
            drop_city: Drop city name (or None)
            used_geo: Whether geo-based search was used
            trips_count: Number of trips found
            leads_count: Number of leads found
        """
        if not settings.enable_analytics_logging:
            logger.debug("Analytics logging disabled via config")
            return

        if not self._initialized or not self._client:
            logger.warning("Firebase not initialized - skipping analytics logging")
            return

        try:
            # Prepare analytics document (matches Node.js structure exactly)
            doc_data = {
                "pickup_city": pickup_city or "ALL",
                "drop_city": drop_city or "N/A",
                "used_geo": used_geo,
                "trips_count": trips_count,
                "leads_count": leads_count,
                "timestamp": datetime.utcnow(),
            }

            # Write to Firestore (async, non-blocking)
            # Path: drivers/{driver_id}/raahiSearch/{auto_generated_id}
            update_time, doc_ref = await (
                self._client.collection("drivers")
                .document(driver_id)
                .collection("raahiSearch")
                .add(doc_data)
            )

            # Log with the auto-generated document ID for Firebase verification
            logger.info(
                f"Analytics logged for driver {driver_id}: "
                f"{pickup_city or 'ALL'} → {drop_city or 'N/A'} "
                f"({trips_count} trips, {leads_count} leads, geo={used_geo}) | "
                f"Firestore Doc ID: {doc_ref.id} | Path: drivers/{driver_id}/raahiSearch/{doc_ref.id}"
            )

        except Exception as e:
            # Don't raise - analytics failure should never break the API
            logger.error(f"Failed to log analytics to Firestore: {e}", exc_info=True)


# Singleton instance
_firebase_service: Optional[FirebaseService] = None


def get_firebase_service() -> FirebaseService:
    """Get Firebase service singleton."""
    global _firebase_service
    if _firebase_service is None:
        _firebase_service = FirebaseService()
    return _firebase_service
