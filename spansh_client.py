"""Spansh API Client module for Elite Dangerous galactic data integration.

Isolates network requests, payload generation, and error handling for Spansh endpoints.
"""

from __future__ import annotations

import requests
from config import appname

from logger_utils import logger, plugin_name


class SpanshError(Exception):
    """Base exception for all Spansh API related errors."""


class SpanshTimeoutError(SpanshError):
    """Raised when the Spansh API request times out."""


class SpanshAPIError(SpanshError):
    """Raised when the Spansh API returns an unsuccessful status code or invalid response."""


class SpanshClient:
    """Client for interacting with Spansh APIs (https://spansh.co.uk/api)."""

    SEARCH_SYSTEMS_URL = "https://spansh.co.uk/api/search/systems"

    def __init__(self, timeout: int = 15) -> None:
        """Initialize the Spansh API client.

        Args:
            timeout (int): Request timeout in seconds. Defaults to 15.
        """
        self.timeout = timeout
        self.headers = {
            "User-Agent": f"{appname}-{plugin_name}",
            "Content-Type": "application/json",
        }

    def _build_system_search_payload(
        self, reference_system: str, radius: float, limit: int
    ) -> dict:
        """Build the JSON payload for the Spansh systems search endpoint.

        Args:
            reference_system (str): The center system for the search.
            radius (float): Search radius in light years.
            limit (int): Maximum number of results to return.

        Returns:
            dict: Structured dictionary payload for the POST request.
        """
        return {
            "filters": {
                "distance": {
                    "min": 0,
                    "max": radius,
                    "reference_system": reference_system,
                },
            },
            "size": limit,
            "sort": [{"distance": {"direction": "asc"}}],
        }

    def search_systems_around(
        self, reference_system: str, radius: float = 25.0, limit: int = 500
    ) -> list[dict]:
        """Perform a spatial search for systems around a reference system via Spansh POST API.

        Args:
            reference_system (str): The name of the reference star system.
            radius (float, optional): Radius in Ly. Defaults to 25.0.
            limit (int, optional): Max result size. Defaults to 500.

        Returns:
            list[dict]: A list of system records matching the search criteria.

        Raises:
            SpanshTimeoutError: If the request times out.
            SpanshAPIError: If the API returns a non-200 status or malformed structure.
        """
        payload = self._build_system_search_payload(reference_system, radius, limit)

        logger.debug(
            "Sending Spansh POST request for systems around '%s' (Radius: %sLy, Limit: %s)",
            reference_system,
            radius,
            limit,
        )

        try:
            response = requests.post(
                self.SEARCH_SYSTEMS_URL,
                json=payload,
                headers=self.headers,
                timeout=self.timeout,
            )
        except requests.Timeout as e:
            logger.error(
                "Spansh API request timed out after %s seconds: %s", self.timeout, e
            )
            raise SpanshTimeoutError(f"Spansh request timed out: {e}") from e
        except requests.RequestException as e:
            logger.error("Network communication error with Spansh API: %s", e)
            raise SpanshAPIError(f"Network error communicating with Spansh: {e}") from e
        else:
            if response.status_code != 200:
                error_msg = f"Spansh API returned status code {response.status_code}: {response.text}"
                logger.error(error_msg)
                raise SpanshAPIError(error_msg)

            try:
                data = response.json()
            except ValueError as e:
                logger.error("Failed to parse JSON response from Spansh API: %s", e)
                raise SpanshAPIError(f"Invalid JSON response from Spansh: {e}") from e

            results = []
            if isinstance(data, list):
                results = data
            elif isinstance(data, dict):
                results = data.get("results", data.get("systems", []))

            logger.debug(
                "Spansh search successful. Retrieved %d systems.", len(results)
            )
            return results
