"""
Core parking search logic based on EDR algorithms and EDSM API integration.
"""

import logging
import os

import requests
from config import appname

# Official EDMC logging configuration for plugins
plugin_name = os.path.basename(os.path.dirname(__file__))
logger = logging.getLogger(f"{appname}.{plugin_name}")


class EDParkingSystemFinder:
    """
    Finds systems with available fleet carrier parking slots nearby using EDSM data.
    """

    def __init__(self, star_system: str, callback=None) -> None:
        """
        Initialize the parking system finder.

        Args:
            star_system (str): The name of the reference star system.
            callback (callable, optional): Optional callback function upon completion.
        """
        self.star_system = star_system
        self.radius = 25
        self.rank = 0
        self.callback = callback
        # Set an identifying User-Agent to avoid EDSM Cloudflare blocks
        self.headers = {"User-Agent": f"{appname}-{plugin_name}"}

    def within_radius(self, radius: int) -> None:
        """
        Set the search radius in light years.

        Args:
            radius (int): Search radius limit.
        """
        self.radius = radius

    def nb_to_pick(self, rank: int) -> None:
        """
        Set the result index rank to pick from candidates.

        Args:
            rank (int): Index rank.
        """
        self.rank = rank

    def search_sync(self) -> dict | None:
        """
        Synchronously search for a nearby system suitable for fleet carrier parking.
        If the target system doesn't have parking, it falls back to searching
        progressively through nearby systems within the radius.

        Returns:
            dict | None: System details including parking data, or None if not found.
        """
        try:
            candidates = []

            # 1. Check the starting system first if rank is 0
            sys_resp = requests.get(
                "https://www.edsm.net/api-v1/system",
                params={
                    "systemName": self.star_system,
                    "showInformation": 1,
                    "showPermit": 1,
                },
                headers=self.headers,
                timeout=10,
            ).json()

            if sys_resp and "name" in sys_resp:
                info = sys_resp.get("information", {})
                the_system = {
                    "name": sys_resp["name"],
                    "requirePermit": info.get("requirePermit", False),
                    "distance": 0,
                    "information": info,
                }
                if self.rank == 0 and self._check_system(the_system):
                    return the_system

            # 2. Search via spherical systems within the specified radius
            sphere_resp = requests.get(
                "https://www.edsm.net/api-v1/sphere-systems",
                params={
                    "systemName": self.star_system,
                    "radius": self.radius,
                    "showInformation": 1,
                    "showPermit": 1,
                },
                headers=self.headers,
                timeout=15,
            ).json()

            if isinstance(sphere_resp, list):
                # Sort systems by increasing distance from the origin point
                sorted_systems = sorted(sphere_resp, key=lambda s: s.get("distance", 0))

                for system in sorted_systems:
                    if self._check_system(system):
                        candidates.append(system)
                        if len(candidates) > self.rank:
                            return candidates[self.rank]

                # Fallback if valid candidates were found but are fewer than the requested rank
                if candidates:
                    return candidates[-1]

        except requests.RequestException as e:
            logger.error(f"[ED Parking Finder] EDSM API communication error: {e}")

        return None

    def _check_system(self, system: dict | None) -> bool:
        """
        Evaluate whether a system is accessible and has available parking slots.

        Args:
            system (dict | None): System dictionary retrieved from EDSM.

        Returns:
            bool: True if suitable for parking, False otherwise.
        """
        if not system:
            return False

        # Prevent false positives with distant systems incorrectly returned with distance 0
        if (
            system.get("distance", 0) == 0
            and system.get("name", "") != self.star_system
        ):
            return False

        accessible = not system.get("information", {}).get("requirePermit", False)
        slots = self._theoretical_parking_slots(system)

        if accessible and slots > 0:
            system["parking"] = {"slots": slots}
            return True

        return False

    def _theoretical_parking_slots(self, system: dict | None) -> int:
        """
        Calculate theoretical parking slots based on the body count (16 slots per body, max 128).

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
