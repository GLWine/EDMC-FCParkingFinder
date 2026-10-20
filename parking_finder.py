"""Core parking search logic based on supplied system data."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from logger_utils import logger

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any


class ParkingSystemFinder:
    """Evaluate supplied system records for Fleet Carrier parking availability.

    The finder does not retrieve system data from any API. Callers provide the
    starting system and nearby-system records to :meth:`search_sync`; records
    are expected to contain the fields used by the parking calculations.
    """

    def __init__(
        self,
        star_system: str,
        callback: Callable[..., Any] | None = None,
        fc_data: dict | None = None,
    ) -> None:
        """Create a finder for a reference system.

        Args:
            star_system: Name of the reference system. Comparisons are
                case-insensitive and ignore surrounding whitespace.
            callback: Optional callback retained for compatibility with existing
                callers. Searches are synchronous and this callback is not
                invoked by :meth:`search_sync`.
            fc_data: Optional Fleet Carrier journal telemetry. When the
                telemetry belongs to the reference system, it is attached to
                the evaluated record and used to identify the current body.

        The search radius defaults to 25 light-years. Known permit-locked
        system names are loaded from ``data/known_permits.json`` when the
        finder is created.

        """
        self.star_system = star_system
        self.radius = 25
        self.callback = callback
        self.fc_data = fc_data
        self.known_permits = self._load_known_permits()

    def _load_known_permits(self) -> set[str]:
        """Read permit-locked system names from the local JSON data file.

        Returns:
            A set of system names normalized to lowercase. If the file is
            absent, malformed, or cannot be read, logs the issue and returns
            an empty set.

        """
        permits = set()
        try:
            data_path = Path(__file__).parent / "data" / "known_permits.json"
            if data_path.exists():
                with data_path.open(encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        permits = {
                            p.strip().lower() for p in data if isinstance(p, str)
                        }
                logger.debug("Loaded %d known permit systems from file.", len(permits))
            else:
                logger.warning("known_permits.json not found at %s", data_path)
        except Exception:
            logger.exception("Failed to load known_permits.json")
        return permits

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
    ) -> dict | None:
        """Return the best parking location from caller-supplied system data.

        Neither the starting system nor nearby candidates are retrieved here:
        callers are responsible for supplying records from any desired data
        source. The starting record is included in the search and checked
        first. If it is available for parking, it is the closest result
        (distance zero) and is returned immediately. If it is unavailable,
        permit-locked, or otherwise unsuitable, nearby candidates are filtered
        for known permits and radius, sorted by distance, and checked until the
        closest suitable system is found. Permit-locked systems are skipped.

        Expected record fields are:

        * ``name``: system name.
        * ``distance``: numeric distance in light-years for nearby candidates.
        * ``information.requirePermit``: optional boolean permit requirement.
        * ``information.bodyCount``: optional number of bodies used to estimate
          theoretical parking capacity.
        * ``bodies``: optional list of body records, each optionally containing
          a ``name``. Body names are reported only when matching Fleet Carrier
          telemetry is available.

        The starting-system record must have a ``name`` matching the finder's
        reference system. Nearby records should not include the starting
        system; a zero-distance record with a different name is rejected.

        Returns:
            A copy of the selected system record with a ``parking`` mapping
            containing ``slots``, ``body_name_list``, and ``is_empirical``.
            Returns ``None`` if no suitable record is found or no data is
            supplied. Permit-locked systems are skipped rather than returned.
            Input records are not modified.

        """
        logger.debug(
            "Starting parking search for system '%s' (Radius: %sLy)",
            self.star_system,
            self.radius,
        )
        start_result = self._check_starting_system(starting_system)
        if start_result:
            return start_result

        if starting_system is None and nearby_systems is None:
            logger.error("Parking search requires supplied system data.")
            return None

        return self._search_sphere_systems(nearby_systems or [])

    def _check_starting_system(self, system: dict | None) -> dict | None:
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
        norm_start = self.star_system.strip().lower()
        if norm_start in self.known_permits:
            logger.debug(
                "Starting system '%s' is permit-locked; continuing search.",
                self.star_system,
            )
            return None

        if (
            not system
            or "name" not in system
            or system["name"].strip().lower() != norm_start
        ):
            return None

        info = system.get("information", {})
        if info.get("requirePermit", False):
            logger.debug(
                "Starting system '%s' requires a permit; continuing search.",
                system["name"],
            )
            return None

        the_system = {**system, "distance": 0, "information": info}

        # Attach telemetry if available
        if self.fc_data:
            the_system["fc_telemetry"] = self.fc_data

        if self._check_system(the_system):
            logger.debug(
                "Starting system '%s' is the closest suitable parking location.",
                the_system["name"],
            )
            return the_system

        return None

    def _search_sphere_systems(self, systems: list[dict]) -> dict | None:
        """Evaluate and select from supplied nearby-system records.

        Candidates are copied, filtered against the configured radius and
        local permit list, sorted by distance, and evaluated in order. The
        first suitable candidate is returned, ensuring the result is the
        closest available system after the starting system has been checked.

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

            if self._check_system(system):
                logger.debug(
                    "Selected closest parking system '%s' at %.2fLy",
                    system.get("name"),
                    system.get("distance", 0),
                )
                return system

        return None

    def _filter_candidate(self, system: dict) -> dict | None:
        """Reject malformed or out-of-range candidates and copy accepted ones.

        Args:
            system: Candidate record to validate. Its ``name`` must be a
                string, and its ``distance`` must be numeric and no greater
                than the configured radius.

        Returns:
            A shallow copy of the candidate when valid and not known to be
            permit-locked; otherwise, ``None``. Copying lets evaluation attach
            parking details without changing the caller's input dictionary.

        """
        if not isinstance(system, dict):
            return None

        name = system.get("name", "")
        distance = system.get("distance", 0)
        if (
            not isinstance(name, str)
            or name.strip().lower() in self.known_permits
            or not isinstance(distance, (int, float))
            or distance > self.radius
        ):
            return None
        return {**system}

    def _check_system(self, system: dict | None) -> bool:
        """Determine whether a system is accessible and has parking capacity.

        Args:
            system: Supplied record. The optional
                ``information.requirePermit`` field is used to reject systems
                requiring permits; body count is used to estimate capacity.

        Returns:
            ``True`` when the record is accessible and has at least one
            theoretical parking slot. On success, adds a ``parking`` mapping
            to the record; otherwise returns ``False`` without adding it.

        """
        if not system:
            return False

        sys_name = system.get("name", "Unknown")
        distance = system.get("distance", 0.0)

        if distance == 0 and sys_name.lower() != self.star_system.lower():
            logger.debug("System '%s' rejected: false positive distance 0.", sys_name)
            return False

        if sys_name.strip().lower() in self.known_permits:
            logger.debug("System '%s' rejected: found in known_permits set.", sys_name)
            return False

        accessible = not system.get("information", {}).get("requirePermit", False)
        if not accessible:
            logger.debug("System '%s' rejected: permit required.", sys_name)
            return False

        slots = self._theoretical_parking_slots(system)
        if slots <= 0:
            logger.debug("System '%s' rejected: 0 available slots.", sys_name)
            return False

        body_name_list, is_empirical = self._extract_body_names(system, sys_name)

        system["parking"] = {
            "slots": slots,
            "body_name_list": body_name_list,
            "is_empirical": is_empirical,
        }

        logger.debug(
            "System '%s' passed check with %s slots (Bodies: %s).",
            sys_name,
            slots,
            body_name_list,
        )
        return True

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
        body_count = info.get("bodyCount", None)

        if body_count is None or body_count <= 0:
            body_count = 1

        return min(128, body_count * 16)
