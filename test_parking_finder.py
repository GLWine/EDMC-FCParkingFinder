"""
Unit tests for the EDR Parking System Finder plugin logic.
"""

import unittest
from unittest.mock import MagicMock, patch

from parking_finder import EDRParkingSystemFinder


class TestEDRParkingSystemFinder(unittest.TestCase):
    """Test suite for EDRParkingSystemFinder methods."""

    def setUp(self) -> None:
        """Set up test instances before each test."""
        self.finder = EDRParkingSystemFinder("Sol")

    def test_theoretical_parking_slots_normal(self) -> None:
        """Test parking slot calculation with a standard body count."""
        system_mock = {"name": "Sol", "information": {"bodyCount": 5}}
        # 5 bodies * 16 = 80 slots
        slots = self.finder._theoretical_parking_slots(system_mock)
        self.assertEqual(slots, 80)

    def test_theoretical_parking_slots_max_cap(self) -> None:
        """Test parking slot calculation capped at the 128 maximum limit."""
        system_mock = {"name": "BusySystem", "information": {"bodyCount": 20}}
        # 20 * 16 = 320, but the maximum limit is 128
        slots = self.finder._theoretical_parking_slots(system_mock)
        self.assertEqual(slots, 128)

    def test_theoretical_parking_slots_missing_info(self) -> None:
        """Test fallback behavior when body count information is missing."""
        system_mock = {"name": "EmptySystem", "information": {}}
        # Default fallback to 1 body * 16 = 16 slots
        slots = self.finder._theoretical_parking_slots(system_mock)
        self.assertEqual(slots, 16)

    def test_check_system_valid(self) -> None:
        """Test system validation for a suitable parking candidate."""
        system_mock = {
            "name": "Alpha Centauri",
            "distance": 4.3,
            "information": {"requirePermit": False, "bodyCount": 4},
        }
        result = self.finder._check_system(system_mock)
        self.assertTrue(result)
        self.assertEqual(system_mock["parking"]["slots"], 64)

    def test_check_system_permit_required(self) -> None:
        """Test system filtering when a permit is required."""
        system_mock = {
            "name": "Sol",
            "distance": 0.0,
            "information": {"requirePermit": True, "bodyCount": 10},
        }
        result = self.finder._check_system(system_mock)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
