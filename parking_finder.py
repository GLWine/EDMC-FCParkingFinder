"""
Core parking search logic based on EDR algorithms and EDSM API integration.
"""

import logging
from pathlib import Path

import requests
from config import appname

# Official EDMC logging configuration for plugins
plugin_name = Path(__file__).parent.name
logger = logging.getLogger(f"{appname}.{plugin_name}")


class ParkingSystemFinder:
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

    def search_sync(self) -> dict | None:  # noqa: C901
        """
        Synchronously search for a nearby system suitable for fleet carrier parking.
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
            candidates = []

            # 1. Check the starting system first if rank is 0
            logger.debug("Querying EDSM API for starting system: %s", self.star_system)
            sys_resp = requests.get(
                "https://www.edsm.net/api-v1/system",
                params={
                    "systemName": self.star_system,
                    "showInformation": 1,
                    "showPermit": 1,
                },
                headers=self.headers,
                timeout=10,
            )

            if sys_resp.status_code != 200:
                logger.error(
                    "EDSM API returned status code %s for system query: %s",
                    sys_resp.status_code,
                    self.star_system,
                )

            sys_data = sys_resp.json()

            if sys_data and "name" in sys_data:
                info = sys_data.get("information", {})
                the_system = {
                    "name": sys_data["name"],
                    "requirePermit": info.get("requirePermit", False),
                    "distance": 0,
                    "information": info,
                }
                if self.rank == 0 and self._check_system(the_system):
                    logger.debug(
                        "Starting system '%s' is suitable for parking (Rank 0 match).",
                        the_system["name"],
                    )
                    return the_system
            else:
                logger.debug(
                    "Starting system '%s' not found or invalid response.",
                    self.star_system,
                )

            # 2. Search via spherical systems within the specified radius
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
                },
                headers=self.headers,
                timeout=15,
            )

            if sphere_resp.status_code != 200:
                logger.error(
                    "EDSM API returned status code %s for sphere-systems query.",
                    sphere_resp.status_code,
                )

            sphere_data = sphere_resp.json()

            if isinstance(sphere_data, list):
                logger.debug(
                    "Sphere search returned %d systems. Sorting...", len(sphere_data)
                )
                sorted_systems = sorted(sphere_data, key=lambda s: s.get("distance", 0))

                for system in sorted_systems:
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

                # Fallback if valid candidates were found but are fewer than the requested rank
                if candidates:
                    fallback_system = candidates[-1]
                    logger.debug(
                        "Rank %s exceeds candidates (%d). Falling back to: '%s'",
                        self.rank,
                        len(candidates),
                        fallback_system.get("name"),
                    )
                    return fallback_system
                else:
                    logger.debug(
                        "No suitable parking candidates found within %sLy of '%s'.",
                        self.radius,
                        self.star_system,
                    )
            else:
                logger.error(
                    "Unexpected response format from EDSM sphere-systems API: %s",
                    type(sphere_data),
                )

        except requests.Timeout as e:
            logger.error("EDSM API request timed out: %s", e)
        except requests.RequestException as e:
            logger.error("EDSM API communication error: %s", e)
        except Exception:
            logger.exception("Unexpected critical error during search_sync")

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

        sys_name = system.get("name", "Unknown")
        distance = system.get("distance", 0.0)

        # Prevent false positives with distant systems incorrectly returned with distance 0
        if distance == 0 and sys_name.lower() != self.star_system.lower():
            logger.debug("System '%s' rejected: false positive distance 0.", sys_name)
            return False

        accessible = not system.get("information", {}).get("requirePermit", False)
        if not accessible:
            logger.debug("System '%s' rejected: permit required.", sys_name)
            return False

        slots = self._theoretical_parking_slots(system)
        if slots <= 0:
            logger.debug("System '%s' rejected: 0 available slots.", sys_name)
            return False

        system["parking"] = {"slots": slots}
        logger.debug("System '%s' passed check with %s slots.", sys_name, slots)
        return True

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
