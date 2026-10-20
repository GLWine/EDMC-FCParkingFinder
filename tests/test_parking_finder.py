"""Tests for the standalone parking-finder core."""

from __future__ import annotations

import math
import unittest
from importlib import import_module

ParkingSystemFinder = import_module("parking_finder").ParkingSystemFinder


class ParkingSystemFinderTests(unittest.TestCase):
    """Verify candidate filtering and theoretical capacity calculations."""

    def test_permit_required_systems_are_excluded(self) -> None:
        """Both normalized and provider permit flags reject a candidate."""
        finder = ParkingSystemFinder("Reference")
        candidates = [
            {
                "name": "Information Restricted",
                "distance": 1,
                "information": {"bodyCount": 1, "requirePermit": True},
            },
            {
                "name": "Provider Restricted",
                "distance": 2,
                "needs_permit": True,
                "information": {"bodyCount": 1},
            },
            {
                "name": "Allowed",
                "distance": 3,
                "needs_permit": False,
                "information": {"bodyCount": 1},
            },
        ]

        result = finder.search_sync(nearby_systems=candidates)

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Allowed")
        self.assertEqual(set(result), {"name", "distance", "parking"})

    def test_nearest_eligible_candidate_is_selected(self) -> None:
        """Candidate input order does not override distance order."""
        finder = ParkingSystemFinder("Reference")
        candidates = [
            {
                "name": "Farther",
                "distance": 12,
                "information": {"bodyCount": 1, "requirePermit": False},
            },
            {
                "name": "Nearest",
                "distance": 4,
                "information": {"bodyCount": 1, "requirePermit": False},
            },
        ]

        result = finder.search_sync(nearby_systems=candidates)

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Nearest")
        self.assertEqual(result["distance"], 4.0)

    def test_radius_limit_is_inclusive(self) -> None:
        """Systems at the radius are accepted and those beyond it are ignored."""
        finder = ParkingSystemFinder("Reference")
        finder.within_radius(25)
        candidates = [
            {
                "name": "Outside",
                "distance": 25.1,
                "information": {"bodyCount": 1, "requirePermit": False},
            },
            {
                "name": "At Boundary",
                "distance": 25,
                "information": {"bodyCount": 1, "requirePermit": False},
            },
        ]

        result = finder.search_sync(nearby_systems=candidates)

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "At Boundary")
        self.assertEqual(result["distance"], 25.0)

    def test_capacity_uses_sixteen_slots_per_body_and_caps_at_128(self) -> None:
        """Body counts produce 16 slots each, with a system maximum of 128."""
        finder = ParkingSystemFinder("Reference")
        for body_count, expected_slots in ((1, 16), (8, 128), (20, 128)):
            with self.subTest(body_count=body_count):
                result = finder.search_sync(
                    nearby_systems=[
                        {
                            "name": "Candidate",
                            "distance": 1,
                            "information": {
                                "bodyCount": body_count,
                                "requirePermit": False,
                            },
                        }
                    ]
                )

                self.assertIsNotNone(result)
                self.assertEqual(
                    result["parking"]["theoretical_slots"], expected_slots
                )

    def test_missing_or_invalid_body_count_uses_one_body_fallback(self) -> None:
        """Missing, non-positive, and malformed body counts stay safe."""
        finder = ParkingSystemFinder("Reference")
        for body_count in (None, 0, -1, True, 1.5, "invalid"):
            with self.subTest(body_count=body_count):
                result = finder.search_sync(
                    nearby_systems=[
                        {
                            "name": "Candidate",
                            "distance": 1,
                            "information": {
                                "bodyCount": body_count,
                                "requirePermit": False,
                            },
                        }
                    ]
                )

                self.assertIsNotNone(result)
                self.assertEqual(result["parking"]["theoretical_slots"], 16)

    def test_malformed_candidate_data_is_rejected(self) -> None:
        """Invalid names and distances cannot produce a selected result."""
        finder = ParkingSystemFinder("Reference")
        invalid_candidates = [
            {"name": None, "distance": 1, "information": {"bodyCount": 1}},
            {"name": "Missing Distance", "information": {"bodyCount": 1}},
            {"name": "Text Distance", "distance": "1", "information": {"bodyCount": 1}},
            {"name": "Boolean Distance", "distance": True, "information": {"bodyCount": 1}},
            {"name": "Negative Distance", "distance": -1, "information": {"bodyCount": 1}},
            {
                "name": "Infinite Distance",
                "distance": math.inf,
                "information": {"bodyCount": 1},
            },
            {
                "name": "NaN Distance",
                "distance": math.nan,
                "information": {"bodyCount": 1},
            },
        ]

        self.assertIsNone(finder.search_sync(nearby_systems=invalid_candidates))


if __name__ == "__main__":
    unittest.main()
