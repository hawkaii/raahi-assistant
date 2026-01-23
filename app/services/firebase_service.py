"""
Firebase Firestore service for analytics logging.

This service logs search analytics to Firestore to track driver search behavior,
matching the Node.js implementation structure.

Firestore Path: drivers/{driver_id}/raahiSearch/{auto_id}
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class FirebaseService:
    """Service for logging search analytics to Firestore."""

    def __init__(self):
        self._client = None
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

            # Get synchronous Firestore client (Firebase Admin SDK's official approach)
            # We'll use asyncio.to_thread() to run sync operations without blocking
            self._client = firestore.client()
            self._initialized = True

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

            # Write to Firestore using thread pool (non-blocking async wrapper around sync client)
            # Path: drivers/{driver_id}/raahiSearch/{auto_generated_id}
            def _write_to_firestore():
                """Synchronous Firestore write operation."""
                return (
                    self._client.collection("drivers")
                    .document(driver_id)
                    .collection("raahiSearch")
                    .add(doc_data)
                )

            # Run sync operation in thread pool to avoid blocking async event loop
            update_time, doc_ref = await asyncio.to_thread(_write_to_firestore)

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

    async def log_intent(
        self,
        driver_id: str,
        query_text: str,
        intent: str,
        session_id: str,
        interaction_count: int,
    ):
        """
        Log intent query to Firestore for analytics.

        Firestore Path: raahiIntents/{auto_id}

        Document structure:
        {
            driver_id: "driver_123",
            query_text: "User's query",
            intent: "GENERIC",
            timestamp: <Firestore timestamp>,
            session_id: "uuid",
            interaction_count: 3
        }

        Args:
            driver_id: Driver ID from driver_profile
            query_text: User's original query text
            intent: Detected intent type (e.g., "GENERIC", "GET_DUTIES")
            session_id: Session ID for tracking conversation
            interaction_count: Number of interactions in this session
        """
        if not settings.enable_analytics_logging:
            logger.debug("Analytics logging disabled via config")
            return

        if not self._initialized or not self._client:
            logger.warning("Firebase not initialized - skipping intent logging")
            return

        try:
            # Prepare intent log document (includes driver_id as field)
            doc_data = {
                "driver_id": driver_id,
                "query_text": query_text,
                "intent": intent,
                "timestamp": datetime.utcnow(),
                "session_id": session_id,
                "interaction_count": interaction_count,
            }

            # Write to Firestore using thread pool (top-level collection)
            def _write_to_firestore():
                """Synchronous Firestore write operation."""
                return self._client.collection("raahiIntents").add(doc_data)

            # Run sync operation in thread pool to avoid blocking
            update_time, doc_ref = await asyncio.to_thread(_write_to_firestore)

            logger.info(
                f"Intent logged: driver={driver_id}, "
                f"query='{query_text[:50]}...', intent={intent} | "
                f"Doc ID: {doc_ref.id} | Path: raahiIntents/{doc_ref.id}"
            )

        except Exception as e:
            # Don't raise - analytics failure should never break the API
            logger.error(f"Failed to log intent to Firestore: {e}", exc_info=True)


# Singleton instance
_firebase_service: Optional[FirebaseService] = None


def get_firebase_service() -> FirebaseService:
    """Get Firebase service singleton."""
    global _firebase_service
    if _firebase_service is None:
        _firebase_service = FirebaseService()
    return _firebase_service
