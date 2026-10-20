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

    SEARCH_SYSTEMS_URL = "https://spansh.co.uk/api/systems/search"
    PERMIT_SYSTEMS_PAGE_SIZE = 500

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

            if isinstance(data, list):
                results = data
            elif isinstance(data, dict):
                results = data.get("results", data.get("systems"))
            else:
                results = None

            if not isinstance(results, list) or not all(
                isinstance(result, dict) for result in results
            ):
                error_msg = "Spansh API returned an invalid systems response structure."
                logger.error(error_msg)
                raise SpanshAPIError(error_msg)

            logger.debug(
                "Spansh search successful. Retrieved %d systems.", len(results)
            )
            return results

    def search_permit_systems(self) -> list[str]:
        """Return every system Spansh reports as requiring a permit.

        The search endpoint is paginated; results are accepted only when all
        pages declared by Spansh are returned with valid system names.
        """
        page_size = self.PERMIT_SYSTEMS_PAGE_SIZE
        page = 0
        expected_count: int | None = None
        names: list[str] = []
        seen_names: set[str] = set()

        while expected_count is None or len(names) < expected_count:
            count, offset, page_names = self._search_permit_systems_page(
                page, page_size
            )
            if expected_count is None:
                expected_count = count
            if count != expected_count or offset != page * page_size:
                raise SpanshAPIError(
                    "Spansh permit-list pagination changed during retrieval."
                )

            for name in page_names:
                normalized_name = name.strip().casefold()
                if normalized_name in seen_names:
                    raise SpanshAPIError(
                        "Spansh permit-list response contains duplicate systems."
                    )
                seen_names.add(normalized_name)
                names.append(name)

            if len(names) < expected_count and not page_names:
                raise SpanshAPIError(
                    "Spansh permit-list response ended before all systems were read."
                )
            page += 1

        if len(names) != expected_count:
            raise SpanshAPIError(
                "Spansh permit-list response did not contain the declared number "
                "of systems."
            )

        logger.info("Retrieved %d permit systems from Spansh.", len(names))
        return names

    def _search_permit_systems_page(
        self, page: int, page_size: int
    ) -> tuple[int, int, list[str]]:
        """Fetch and validate one page of Spansh's permit-required systems."""
        payload = {
            "filters": {"needs_permit": {"value": True}},
            "sort": [],
            "size": page_size,
            "page": page,
        }
        try:
            response = requests.post(
                self.SEARCH_SYSTEMS_URL,
                json=payload,
                headers=self.headers,
                timeout=self.timeout,
            )
        except requests.Timeout as error:
            logger.error(
                "Spansh permit-list request timed out after %s seconds: %s",
                self.timeout,
                error,
            )
            raise SpanshTimeoutError(
                f"Spansh permit-list request timed out: {error}"
            ) from error
        except requests.RequestException as error:
            logger.error("Spansh permit-list network error: %s", error)
            raise SpanshAPIError(
                f"Network error retrieving Spansh permit systems: {error}"
            ) from error

        if response.status_code != 200:
            error_message = (
                "Spansh permit-list request returned status code "
                f"{response.status_code}: {response.text}"
            )
            logger.error(error_message)
            raise SpanshAPIError(error_message)

        try:
            data = response.json()
        except ValueError as error:
            logger.error("Invalid JSON in Spansh permit-list response: %s", error)
            raise SpanshAPIError(
                f"Invalid JSON response from Spansh: {error}"
            ) from error

        if not isinstance(data, dict):
            raise SpanshAPIError("Spansh permit-list response is not a JSON object.")

        count = data.get("count")
        offset = data.get("from")
        results = data.get("results")
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            or isinstance(offset, bool)
            or not isinstance(offset, int)
            or not isinstance(results, list)
            or len(results) > page_size
        ):
            raise SpanshAPIError(
                "Spansh permit-list response has invalid pagination data."
            )

        names: list[str] = []
        for result in results:
            name = result.get("name") if isinstance(result, dict) else None
            if (
                not isinstance(name, str)
                or not name.strip()
                or result.get("needs_permit") is not True
            ):
                raise SpanshAPIError(
                    "Spansh permit-list response contains an invalid system."
                )
            names.append(name.strip())
        return count, offset, names
