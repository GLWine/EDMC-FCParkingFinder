"""Core parking search logic based on supplied system data."""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from parking_result import AccessStatus, ParkingDetails, ParkingResult

try:
    from logger_utils import logger
except ImportError:
    logger = logging.getLogger(__name__)


class ParkingSystemFinder:
    """Evaluate Fleet Carrier parking availability from supplied system data.

    Callers provide the starting system and nearby-system records to
    :meth:`search_sync`. Records are expected to contain the fields used by
    the parking calculations.
    """

    def __init__(
        self,
        star_system: str,
        fc_data: dict | None = None,
    ) -> None:
        """Create a finder for a reference system.

        Args:
            star_system: Name of the reference system. Comparisons are
                case-insensitive and ignore surrounding whitespace.
            fc_data: Optional Fleet Carrier journal telemetry. When the
                telemetry belongs to the reference system, it is attached to
                the evaluated record and used to identify the current body.

        The search radius defaults to 25 light-years. Permit access is
        determined by Spansh's search filter and each returned system record.

        """
        self.star_system = star_system
        self.radius = 25
        self.fc_data = fc_data

    def within_radius(self, radius: int) -> None:
        """Set the maximum accepted distance for nearby-system candidates.

        Args:
            radius: Maximum distance from the reference system, in light-years.
                Candidates farther than this value are ignored. The supplied
                nearby records must already have their distances calculated.

        This setting does not fetch candidates or calculate distances. It only
        filters the records passed to :meth:`search_sync`.

        """
        self.radius = radius

    def search_sync(
        self,
        starting_system: dict | None = None,
        nearby_systems: list[dict] | None = None,
    ) -> ParkingResult | None:
        """Return the best parking location from caller-supplied system data.

        Only supplied records are evaluated. The starting record is included
        in the search and checked first. If it is available for parking, it is
        the closest result (distance zero) and is returned immediately. If it
        is unavailable, permit-locked, or otherwise unsuitable, nearby
        candidates are checked for access and radius, sorted by distance, and
        evaluated until the closest suitable system is found. Spansh's
        provider query excludes permit-required systems, and returned records
        are still checked when they explicitly report a permit requirement.

        Expected record fields are:

        * ``name``: system name.
        * ``distance``: numeric distance in light-years for nearby candidates.
        * ``information.requirePermit``: optional boolean permit requirement
          after provider normalization.
        * ``information.bodyCount``: optional number of bodies used to estimate
          theoretical parking capacity.
        * ``bodies``: optional list of body records, each optionally containing
          a ``name``. Body names are reported only when matching Fleet Carrier
          telemetry is available.
        * ``stations``: optional Spansh station list. Entries with type
          ``Drake-Class Carrier`` are counted as provider-reported occupants.
          When arrival distances are available, carriers are assigned to the
          nearest body by radial-distance difference, up to 16 per body.

        The starting-system record must have a ``name`` matching the finder's
        reference system. Nearby records should not include the starting
        system; a zero-distance record with a different name is rejected.

        Returns:
            A :class:`ParkingResult` for the selected system, or ``None`` if no
            suitable record is found. Confirmed availability is unknown unless
            occupancy data is supplied; theoretical capacity is not a
            confirmed slot count. Input records are not modified.

        """
        logger.debug(
            "Starting parking search for system '%s' (Radius: %sLy)",
            self.star_system,
            self.radius,
        )
        start_result = self._check_starting_system(starting_system)
        if start_result:
            return start_result

        return self._search_sphere_systems(nearby_systems or [])

    def _access_details(
        self, information: dict, needs_permit: object = None
    ) -> tuple[AccessStatus, str | None]:
        """Return access status from Spansh's permit flag."""
        permit_flags = (information.get("requirePermit"), needs_permit)
        if any(flag is True for flag in permit_flags):
            return "restricted", "spansh_requires_permit"
        if any(flag is False for flag in permit_flags):
            return "allowed", None
        return "unknown", "permit_status_not_reported"

    def _check_starting_system(self, system: dict | None) -> ParkingResult | None:
        """Evaluate a supplied record for the reference system.

        Args:
            system: Record for the reference system, or ``None`` if the caller
                has no record for it. The record must have a matching ``name``
                and may contain ``information`` and ``bodies`` fields.

        Returns:
            A parking result when the system is suitable, or ``None`` when it
            is missing, mismatched, permit-locked, or otherwise unsuitable.
            Returning ``None`` for a permit-locked system allows
            :meth:`search_sync` to continue with nearby candidates.

        """
        if (
            not system
            or "name" not in system
            or not isinstance(system["name"], str)
            or system["name"].strip().casefold() != self.star_system.strip().casefold()
        ):
            return None

        info = system.get("information", {})
        if not isinstance(info, dict):
            info = {}

        the_system = {**system, "distance": 0, "information": info}

        # Attach telemetry if available
        if self.fc_data:
            the_system["fc_telemetry"] = self.fc_data

        result = self._check_system(the_system)
        if result:
            logger.debug(
                "Starting system '%s' is the closest suitable parking location.",
                result["name"],
            )
            return result

        return None

    def _search_sphere_systems(self, systems: list[dict]) -> ParkingResult | None:
        """Evaluate and select from supplied nearby-system records.

        Candidates are copied, filtered against the configured radius,
        checked for access restrictions, sorted by distance, and evaluated in
        order. The first suitable candidate is returned, ensuring the result
        is the closest available system after the starting system has been
        checked.

        Args:
            systems: Nearby system records. Each candidate should contain a
                string ``name``, numeric ``distance`` in light-years, and the
                optional ``information`` and ``bodies`` fields documented by
                :meth:`search_sync`.

        Returns:
            The selected candidate with its parking evaluation, or ``None`` if
            no supplied candidate is suitable.

        """
        logger.debug(
            "Evaluating supplied systems around '%s' (Radius: %sLy)",
            self.star_system,
            self.radius,
        )

        filtered_sphere = []
        for system in systems:
            candidate = self._filter_candidate(system)
            if candidate:
                filtered_sphere.append(candidate)

        sorted_systems = sorted(filtered_sphere, key=lambda s: s.get("distance", 0))
        for candidate in sorted_systems:
            system = {**candidate}
            if (
                self.fc_data
                and system.get("name", "").strip().lower()
                == self.star_system.strip().lower()
            ):
                system["fc_telemetry"] = self.fc_data

            result = self._check_system(system)
            if result:
                logger.debug(
                    "Selected closest parking system '%s' at %.2fLy",
                    result["name"],
                    result["distance"],
                )
                return result

        return None

    def _filter_candidate(self, system: dict) -> dict | None:
        """Reject malformed or out-of-range candidates and copy accepted ones.

        Args:
            system: Candidate record to validate. Its ``name`` must be a
                string, and its ``distance`` must be numeric and no greater
                than the configured radius.

        Returns:
            A shallow copy of the candidate when valid; otherwise, ``None``.
            Copying lets evaluation attach parking details without changing
            the caller's input dictionary.

        """
        if not isinstance(system, dict):
            return None

        name = system.get("name", "")
        distance = system.get("distance", 0)
        if not isinstance(name, str) or isinstance(distance, bool):
            return None
        if not isinstance(distance, (int, float)):
            return None
        try:
            normalized_distance = float(distance)
        except OverflowError:
            return None
        if (
            not math.isfinite(normalized_distance)
            or normalized_distance < 0
            or normalized_distance > self.radius
        ):
            return None
        return {**system}

    def _check_system(self, system: dict | None) -> ParkingResult | None:
        """Determine whether a system is accessible and has parking capacity.

        Args:
            system: Supplied record. The optional
                ``                information.requirePermit`` field or Spansh's top-level
                ``needs_permit`` flag is used to reject systems requiring permits;
                body count is used to estimate capacity.

        Returns:
            A structured result when the record is accessible and has at
            least one theoretical parking slot; otherwise returns ``None``.

        """
        if not system:
            return None

        sys_name = system.get("name", "Unknown")
        distance = system.get("distance", 0.0)

        if distance == 0 and sys_name.lower() != self.star_system.lower():
            logger.debug("System '%s' rejected: false positive distance 0.", sys_name)
            return None

        information = system.get("information", {})
        if not isinstance(information, dict):
            information = {}
        access_status, access_reason = self._access_details(
            information, system.get("needs_permit")
        )
        if access_status == "restricted":
            logger.debug(
                "System '%s' rejected: access restricted (%s).",
                sys_name,
                access_reason,
            )
            return None

        slots = self._theoretical_parking_slots(system)
        if slots <= 0:
            logger.debug("System '%s' rejected: 0 theoretical slots.", sys_name)
            return None

        (
            carrier_count,
            estimated_available_slots,
            body_assignment_complete,
            body_details,
        ) = self._estimate_spansh_occupancy(system, slots)
        provider_data_stale = self._provider_data_is_stale(system.get("updated_at"))
        if provider_data_stale:
            logger.debug(
                "Spansh system data for '%s' is older than 24 hours.",
                sys_name,
            )
        if estimated_available_slots == 0:
            logger.debug(
                "System '%s' rejected: Spansh reports %s carriers for %s theoretical slots (data stale: %s).",
                sys_name,
                carrier_count,
                slots,
                provider_data_stale,
            )
            return None

        body_name_list, is_empirical = self._extract_body_names(system, sys_name)
        parking: ParkingDetails = {
            "theoretical_slots": slots,
            "confirmed_available_slots": None,
            "spansh_reported_carrier_count": carrier_count,
            "estimated_available_slots": estimated_available_slots,
            "body_assignment_complete": body_assignment_complete,
            "provider_data_stale": provider_data_stale,
            "body_details": body_details,
            "slots": slots,
            "body_name_list": body_name_list,
            "is_empirical": is_empirical,
        }
        result: ParkingResult = {
            "name": sys_name,
            "distance": float(distance),
            "access_status": access_status,
            "access_reason": access_reason,
            "parking": parking,
        }

        logger.debug(
            "System '%s' passed check with %s slots (Bodies: %s).",
            sys_name,
            slots,
            body_name_list,
        )
        return result

    @staticmethod
    def _estimate_spansh_occupancy(
        system: dict, theoretical_slots: int
    ) -> tuple[int | None, int | None, bool | None, list[dict[str, object]]]:
        """Estimate open slots from Spansh carrier records and arrival distances.

        Carrier distances are compared with each body's distance from the
        system arrival point. Each body is assigned at most 16 reported
        carriers. This is a radial-distance heuristic, not a confirmed
        carrier-to-body location or occupancy.
        """
        raw_bodies = system.get("bodies", [])
        body_details = (
            [dict(body) for body in raw_bodies if isinstance(body, dict)]
            if isinstance(raw_bodies, list)
            else []
        )

        stations = system.get("stations")
        if not isinstance(stations, list):
            return None, None, None, body_details

        carriers = [
            station
            for station in stations
            if isinstance(station, dict)
            and station.get("type") == "Drake-Class Carrier"
        ]
        carriers_with_distance = []
        for carrier in carriers:
            distance = ParkingSystemFinder._arrival_distance(carrier)
            if distance is None:
                logger.debug(
                    "Ignoring Spansh carrier '%s' without a valid arrival distance.",
                    carrier.get("name", "Unknown"),
                )
                continue
            carriers_with_distance.append((carrier, distance))

        carrier_count = len(carriers_with_distance)
        estimated_available_slots = max(0, theoretical_slots - carrier_count)

        body_distances = [
            (index, distance)
            for index, body in enumerate(body_details)
            if (distance := ParkingSystemFinder._arrival_distance(body)) is not None
        ]
        carrier_distances = [distance for _, distance in carriers_with_distance]

        information = system.get("information", {})
        body_count = (
            information.get("bodyCount") if isinstance(information, dict) else None
        )
        body_assignment_complete = (
            len(carrier_distances) == carrier_count
            and len(body_distances) == len(body_details)
            and isinstance(body_count, int)
            and not isinstance(body_count, bool)
            and len(body_details) >= body_count
        )

        assigned_carriers = [0] * len(body_details)
        for carrier_distance in sorted(carrier_distances):
            available_bodies = [
                (index, distance)
                for index, distance in body_distances
                if assigned_carriers[index] < 16
            ]
            if not available_bodies:
                break
            body_index, _ = min(
                available_bodies,
                key=lambda body: abs(carrier_distance - body[1]),
            )
            assigned_carriers[body_index] += 1

        body_proximity = sorted(
            body_distances,
            key=lambda body: (
                min(
                    (
                        abs(body[1] - carrier_distance)
                        for carrier_distance in carrier_distances
                    ),
                    default=body[1],
                ),
                body[1],
            ),
        )
        body_available_slots = [0] * len(body_details)
        remaining_slots = estimated_available_slots
        for body_index, _ in body_proximity:
            available_for_body = 16 - assigned_carriers[body_index]
            allocated_slots = min(remaining_slots, available_for_body)
            body_available_slots[body_index] = allocated_slots
            remaining_slots -= allocated_slots
            if remaining_slots == 0:
                break

        known_body_indices = {index for index, _ in body_distances}
        for index, body in enumerate(body_details):
            body["spansh_reported_carrier_count"] = (
                assigned_carriers[index] if index in known_body_indices else None
            )
            body["estimated_available_slots"] = (
                body_available_slots[index] if index in known_body_indices else None
            )

        return (
            carrier_count,
            estimated_available_slots,
            body_assignment_complete,
            body_details,
        )

    @staticmethod
    def _arrival_distance(record: dict) -> float | None:
        """Return a finite non-negative Spansh arrival distance, if supplied."""
        distance = record.get("distance_to_arrival")
        if isinstance(distance, bool) or not isinstance(distance, (int, float)):
            return None
        try:
            distance = float(distance)
        except OverflowError:
            return None
        if not math.isfinite(distance) or distance < 0:
            return None
        return distance

    @staticmethod
    def _provider_data_is_stale(updated_at: object) -> bool | None:
        """Return whether the Spansh system record is more than 24 hours old."""
        if not isinstance(updated_at, str) or not updated_at.strip():
            return None
        try:
            timestamp = datetime.fromisoformat(
                updated_at.strip().replace("Z", "+00:00")
            )
        except ValueError:
            logger.debug(
                "Ignoring invalid Spansh system update timestamp: %r", updated_at
            )
            return None
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)
        return age.total_seconds() > 24 * 60 * 60

    def _clean_body_name(self, raw_name: str, sys_name: str) -> str:
        """Remove a system-name prefix and whitespace from a body name.

        Args:
            raw_name: Full body name as supplied by the system record or journal.
            sys_name: System name whose leading occurrence should be removed.

        Returns:
            Body name with a case-insensitive leading system name removed and
            all remaining whitespace deleted.

        """
        cleaned = raw_name
        if cleaned.lower().startswith(sys_name.lower()):
            cleaned = cleaned[len(sys_name) :].strip()
        return re.sub(r"\s+", "", cleaned)

    def _extract_body_names(
        self, system: dict, sys_name: str
    ) -> tuple[str | None, bool]:
        """Find body names matching the Fleet Carrier's journal telemetry.

        Args:
            system: System record, including optional ``fc_telemetry`` and
                ``bodies`` fields.
            sys_name: Name of the system being evaluated.

        Returns:
            Pair of the formatted body name(s) and an empirical-data flag.
            Names are returned only when telemetry identifies the same
            system; otherwise returns ``(None, False)``. If body records are
            available, their names take precedence over the telemetry's
            ``body_name`` value.

        """
        fc_telemetry = system.get("fc_telemetry")
        if (
            not fc_telemetry
            or fc_telemetry.get("system", "").strip().lower()
            != sys_name.strip().lower()
        ):
            return None, False

        bodies = system.get("bodies", [])
        if bodies:
            short_names = [
                self._clean_body_name(b.get("name", ""), sys_name)
                for b in bodies
                if b.get("name")
            ]
            valid_names = [n for n in short_names if n]
            if valid_names:
                return ", ".join(valid_names), True

        single_body = fc_telemetry.get("body_name")
        if single_body:
            cleaned = self._clean_body_name(single_body, sys_name)
            if cleaned:
                return cleaned, True

        return None, False

    def _theoretical_parking_slots(self, system: dict | None) -> int:
        """Estimate parking capacity from the system's reported body count.

        Args:
            system: System record with optional ``information.bodyCount``.

        Returns:
            Estimated theoretical slot count: 16 per body, capped at 128.
            Missing or non-positive body counts are treated as one body;
            ``None`` input produces zero slots.

        """
        if not system:
            return 0

        info = system.get("information", {})
        body_count = info.get("bodyCount") if isinstance(info, dict) else None

        if (
            isinstance(body_count, bool)
            or not isinstance(body_count, int)
            or body_count <= 0
        ):
            body_count = 1

        return min(128, body_count * 16)
