"""Core parking search logic based on EDR algorithms and EDSM API integration."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import requests
from config import appname

# Official EDMC logging configuration for plugins
plugin_name = Path(__file__).parent.name
logger = logging.getLogger(f"{appname}.{plugin_name}")


class ParkingSystemFinder:
    """Finds systems with available fleet carrier parking slots nearby using EDSM data."""

    def __init__(
        self, star_system: str, callback=None, fc_data: dict | None = None
    ) -> None:
        """Initialize the parking system finder.

        Args:
            star_system (str): The name of the reference star system.
            callback (callable, optional): Optional callback function upon completion.
            fc_data (dict | None, optional): Fleet carrier position and saturation data from journal.
        """
        self.star_system = star_system
        self.radius = 25
        self.rank = 0
        self.callback = callback
        self.fc_data = fc_data
        # Set an identifying User-Agent to avoid EDSM Cloudflare blocks
        self.headers = {"User-Agent": f"{appname}-{plugin_name}"}
        self.known_permits = self._load_known_permits()

    def _load_known_permits(self) -> set[str]:
        """Load known permit-locked systems from data/known_permits.json.

        Returns:
            set[str]: Lowercase set of known permit system names.
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
        """Set the search radius in light years.

        Args:
            radius (int): Search radius limit.
        """
        self.radius = radius

    def nb_to_pick(self, rank: int) -> None:
        """Set the result index rank to pick from candidates.

        Args:
            rank (int): Index rank.
        """
        self.rank = rank

    def search_sync(self) -> dict | None:
        """Synchronously search for a nearby system suitable for fleet carrier parking.

        If the target system doesn't have parking, it falls back to searching
        progressively through nearby systems within the radius.

        Returns:
            dict | None: System details including parking data, or None if not found.
        """
        logger.debug(
            "Starting parking search for system '%s' (Radius: %sLy, Rank: %s)",
            self.star_system,
            self.radius,
            self.rank,
        )
        try:
            # 0 & 1. Check starting system
            start_result = self._check_starting_system()
            if start_result:
                return start_result

            # 2. Search via spherical systems within the specified radius
            return self._search_sphere_systems()

        except requests.Timeout as e:
            logger.error("EDSM API request timed out: %s", e)
        except requests.RequestException as e:
            logger.error("EDSM API communication error: %s", e)
        except Exception:
            logger.exception("Unexpected critical error during search_sync")

        return None

    def _check_starting_system(self) -> dict | None:
        """Check if the starting system is a permit or valid parking choice.

        Returns:
            dict | None: System evaluation dictionary or None.
        """
        norm_start = self.star_system.strip().lower()
        if norm_start in self.known_permits:
            logger.debug(
                "Starting system '%s' is natively recognized as a permit system.",
                self.star_system,
            )
            return {"name": self.star_system, "permit_locked": True}

        logger.debug("Querying EDSM API for starting system: %s", self.star_system)
        sys_resp = requests.get(
            "https://www.edsm.net/api-v1/system",
            params={
                "systemName": self.star_system,
                "showInformation": 1,
                "showPermit": 1,
                "showBodies": 1,
            },
            headers=self.headers,
            timeout=10,
        )

        if sys_resp.status_code != 200:
            return None

        sys_data = sys_resp.json()
        if not sys_data or "name" not in sys_data:
            return None

        info = sys_data.get("information", {})
        if info.get("requirePermit", False):
            logger.debug(
                "Starting system '%s' requires permit according to EDSM.",
                sys_data["name"],
            )
            return {"name": sys_data["name"], "permit_locked": True}

        the_system = {
            "name": sys_data["name"],
            "requirePermit": False,
            "distance": 0,
            "information": info,
            "bodies": sys_data.get("bodies", []),
        }

        # Attach telemetry if available
        if self.fc_data:
            the_system["fc_telemetry"] = self.fc_data

        if self.rank == 0 and self._check_system(the_system):
            logger.debug(
                "Starting system '%s' is suitable for parking (Rank 0 match).",
                the_system["name"],
            )
            return the_system

        return None

    def _search_sphere_systems(self) -> dict | None:
        """Query and evaluate nearby systems within radius.

        Returns:
            dict | None: Chosen system dictionary or None.
        """
        logger.debug(
            "Querying EDSM sphere-systems around '%s' (Radius: %sLy)",
            self.star_system,
            self.radius,
        )
        sphere_resp = requests.get(
            "https://www.edsm.net/api-v1/sphere-systems",
            params={
                "systemName": self.star_system,
                "radius": self.radius,
                "showInformation": 1,
                "showPermit": 1,
                "showBodies": 1,
            },
            headers=self.headers,
            timeout=15,
        )

        if sphere_resp.status_code != 200:
            return None

        sphere_data = sphere_resp.json()
        if not isinstance(sphere_data, list):
            return None

        filtered_sphere = []
        for s in sphere_data:
            s_name = s.get("name", "").strip().lower()
            if s_name in self.known_permits:
                continue
            filtered_sphere.append(s)

        sorted_systems = sorted(filtered_sphere, key=lambda s: s.get("distance", 0))
        candidates = []

        for system in sorted_systems:
            if (
                self.fc_data
                and system.get("name", "").strip().lower()
                == self.star_system.strip().lower()
            ):
                system["fc_telemetry"] = self.fc_data

            if self._check_system(system):
                candidates.append(system)
                if len(candidates) > self.rank:
                    chosen = candidates[self.rank]
                    logger.debug(
                        "Selected parking system '%s' at %.2fLy (Rank %s)",
                        chosen.get("name"),
                        chosen.get("distance", 0),
                        self.rank,
                    )
                    return chosen

        if candidates:
            return candidates[-1]

        return None

    def _check_system(self, system: dict | None) -> bool:
        """Evaluate whether a system is accessible and has available parking slots.

        Args:
            system (dict | None): System dictionary retrieved from EDSM.

        Returns:
            bool: True if suitable for parking, False otherwise.
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
        """Clean and shorten a body name by removing system prefix and whitespace.

        Args:
            raw_name (str): Raw body name from data.
            sys_name (str): Star system name.

        Returns:
            str: Cleaned short body name string.
        """
        cleaned = raw_name
        if cleaned.lower().startswith(sys_name.lower()):
            cleaned = cleaned[len(sys_name) :].strip()
        return re.sub(r"\s+", "", cleaned)

    def _extract_body_names(
        self, system: dict, sys_name: str
    ) -> tuple[str | None, bool]:
        """Extract and format short body names from telemetry or bodies list.

        Args:
            system (dict): System dictionary.
            sys_name (str): Name of the star system.

        Returns:
            tuple[str | None, bool]: Formatted body names string and empirical status flag.
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
        """Calculate theoretical parking slots based on the body count (16 slots per body, max 128).

        Args:
            system (dict | None): System dictionary.

        Returns:
            int: Calculated number of available parking slots.
        """
        if not system:
            return 0

        info = system.get("information", {})
        body_count = info.get("bodyCount", None)

        if body_count is None or body_count <= 0:
            body_count = 1

        return min(128, body_count * 16)
