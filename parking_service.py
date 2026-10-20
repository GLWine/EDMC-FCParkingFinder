"""Coordinate Spansh data acquisition and parking availability evaluation."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from logger_utils import logger
from parking_finder import ParkingSystemFinder
from spansh_client import SpanshClient, SpanshError

if TYPE_CHECKING:
    from parking_result import ParkingResult


class ParkingServiceError(Exception):
    """Raised when the Spansh provider cannot return parking search data."""


class ParkingSearchService:
    """Connect the Spansh provider to the pure parking-search core."""

    def __init__(self, client: SpanshClient | None = None) -> None:
        """Create the service with an injected or default Spansh client.

        Args:
            client: Provider instance used to retrieve system records.

        """
        self.client = client or SpanshClient()

    def search(
        self, system_name: str, fc_data: dict | None = None
    ) -> ParkingResult | None:
        """Acquire nearby systems, normalize their records, and evaluate parking.

        Provider failures are exposed as :class:`ParkingServiceError` with
        their original exception preserved as the cause.
        """
        if not isinstance(system_name, str) or not system_name.strip():
            raise ValueError("A non-empty reference system name is required.")

        system_name = system_name.strip()
        finder = ParkingSystemFinder(system_name, fc_data=fc_data)
        try:
            records = self.client.search_systems_around(
                system_name, radius=finder.radius
            )
        except SpanshError as error:
            raise ParkingServiceError(
                f"Unable to retrieve systems around '{system_name}'."
            ) from error

        normalized_records = self._normalize_systems(records)
        normalized_name = system_name.strip().casefold()
        starting_system = next(
            (
                record
                for record in normalized_records
                if record["name"].strip().casefold() == normalized_name
            ),
            None,
        )
        nearby_systems = [
            record
            for record in normalized_records
            if record["name"].strip().casefold() != normalized_name
        ]
        return finder.search_sync(
            starting_system=starting_system,
            nearby_systems=nearby_systems,
        )

    @staticmethod
    def _normalize_systems(records: list[dict]) -> list[dict]:
        """Return core-compatible copies of well-formed Spansh system records."""
        normalized: list[dict] = []
        for index, record in enumerate(records):
            name = record.get("name")
            distance = record.get("distance")
            information = record.get("information")
            if information is None:
                information = {}
            bodies = record.get("bodies", [])
            body_count = (
                information.get("bodyCount") if isinstance(information, dict) else None
            )
            if body_count is None:
                body_count = record.get("body_count")
            permit_required = (
                information.get("requirePermit")
                if isinstance(information, dict)
                else None
            )
            needs_permit = record.get("needs_permit")

            if (
                not isinstance(name, str)
                or not name.strip()
                or isinstance(distance, bool)
                or not isinstance(distance, (int, float))
                or not math.isfinite(distance)
                or distance < 0
                or not isinstance(information, dict)
                or (
                    body_count is not None
                    and (
                        isinstance(body_count, bool) or not isinstance(body_count, int)
                    )
                )
                or (
                    permit_required is not None
                    and not isinstance(permit_required, bool)
                )
                or (needs_permit is not None and not isinstance(needs_permit, bool))
                or not isinstance(bodies, list)
                or any(
                    not isinstance(body, dict)
                    or (
                        body.get("name") is not None
                        and not isinstance(body.get("name"), str)
                    )
                    for body in bodies
                )
            ):
                logger.warning(
                    "Skipping malformed Spansh system record at index %d.", index
                )
                continue

            normalized_information = dict(information)
            if permit_required is True or needs_permit is True:
                normalized_information["requirePermit"] = True
            elif permit_required is False or needs_permit is False:
                normalized_information["requirePermit"] = False

            normalized_record: dict[str, Any] = {
                **record,
                "name": name.strip(),
                "distance": float(distance),
                "information": normalized_information,
                "bodies": [dict(body) for body in bodies],
            }
            if body_count is not None:
                normalized_record["information"].setdefault("bodyCount", body_count)
            normalized.append(normalized_record)

        return normalized
