"""
Unit and Integration tests for the ED Parking System Finder plugin logic.
"""

import sys
from unittest.mock import MagicMock

# Mock EDMC config module before importing parking_finder
mock_config = MagicMock()
mock_config.appname = "EDMC"
mock_config.user_agent = "EDMC/TestEnvironment"
sys.modules["config"] = mock_config

import unittest
from unittest.mock import patch

import requests
from requests.exceptions import RequestException

from parking_finder import EDParkingSystemFinder


class TestEDParkingSystemFinder(unittest.TestCase):
    """Test suite for EDParkingSystemFinder methods covering all functionalities."""

    def setUp(self) -> None:
        """Set up test instances before each test."""
        self.finder = EDParkingSystemFinder("Sol")

    def test_within_radius(self) -> None:
        """Test setting the search radius."""
        self.finder.within_radius(35)
        self.assertEqual(self.finder.radius, 35)

    def test_nb_to_pick(self) -> None:
        """Test setting the result index rank."""
        self.finder.nb_to_pick(2)
        self.assertEqual(self.finder.rank, 2)

    def test_theoretical_parking_slots_normal(self) -> None:
        """Test parking slot calculation with a standard body count."""
        system_mock = {"name": "Sol", "information": {"bodyCount": 5}}
        slots = self.finder._theoretical_parking_slots(system_mock)
        self.assertEqual(slots, 80)

    def test_theoretical_parking_slots_max_cap(self) -> None:
        """Test parking slot calculation capped at the 128 maximum limit."""
        system_mock = {"name": "BusySystem", "information": {"bodyCount": 20}}
        slots = self.finder._theoretical_parking_slots(system_mock)
        self.assertEqual(slots, 128)

    def test_theoretical_parking_slots_missing_info(self) -> None:
        """Test fallback behavior when body count information is missing or zero/negative."""
        system_mock_empty = {"name": "EmptySystem", "information": {}}
        self.assertEqual(self.finder._theoretical_parking_slots(system_mock_empty), 16)

        system_mock_none = None
        self.assertEqual(self.finder._theoretical_parking_slots(system_mock_none), 0)

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

    def test_check_system_none(self) -> None:
        """Test system validation with None input."""
        self.assertFalse(self.finder._check_system(None))

    def test_check_system_false_positive_distance_zero(self) -> None:
        """Test that systems with distance 0 but different name are rejected."""
        system_mock = {
            "name": "OtherSystem",
            "distance": 0.0,
            "information": {"requirePermit": False, "bodyCount": 5},
        }
        result = self.finder._check_system(system_mock)
        self.assertFalse(result)

    def test_check_system_permit_required(self) -> None:
        """Test system filtering when a permit is required."""
        system_mock = {
            "name": "Sol",
            "distance": 0.0,
            "information": {"requirePermit": True, "bodyCount": 10},
        }
        result = self.finder._check_system(system_mock)
        self.assertFalse(result)

    @patch("parking_finder.requests.get")
    def test_search_sync_rank_zero_starting_system(self, mock_get) -> None:
        """Test search_sync returning the starting system when rank is 0 and valid."""
        mock_sys_response = MagicMock()
        mock_sys_response.json.return_value = {
            "name": "Sol",
            "information": {"requirePermit": False, "bodyCount": 3},
        }

        mock_get.return_value = mock_sys_response

        result = self.finder.search_sync()
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["name"], "Sol")
        self.assertEqual(result["parking"]["slots"], 48)

    @patch("parking_finder.requests.get")
    def test_search_sync_progressive_fallback_to_sphere(self, mock_get) -> None:
        """Test search_sync falling back to sphere search when starting system requires a permit."""
        # Starting system requires a permit, forcing the check to fail and trigger sphere search fallback
        mock_sys_resp = MagicMock()
        mock_sys_resp.json.return_value = {
            "name": "Sol",
            "information": {"requirePermit": True, "bodyCount": 5},
        }

        # Sphere response containing a valid nearby system
        mock_sphere_resp = MagicMock()
        mock_sphere_resp.json.return_value = [
            {
                "name": "Alpha Centauri",
                "distance": 4.3,
                "information": {"requirePermit": False, "bodyCount": 3},
            }
        ]

        mock_get.side_effect = [mock_sys_resp, mock_sphere_resp]

        result = self.finder.search_sync()
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["name"], "Alpha Centauri")
        self.assertEqual(result["parking"]["slots"], 48)

    @patch("parking_finder.requests.get")
    def test_search_sync_request_exception(self, mock_get) -> None:
        """Test search_sync safely handling network exceptions."""
        mock_get.side_effect = RequestException("API down")

        result = self.finder.search_sync()
        self.assertIsNone(result)

    def test_live_edsm_api_response_status(self) -> None:
        """Test live EDSM API response status and basic payload."""
        try:
            headers = {"User-Agent": "EDMC/TestEnvironment ED-Parking-Finder"}
            resp = requests.get(
                "https://www.edsm.net/api-v1/system",
                params={"systemName": "Sol", "showInformation": 1, "showPermit": 1},
                headers=headers,
                timeout=10,
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data.get("name"), "Sol")
        except requests.RequestException as e:
            self.fail(f"Live EDSM API request failed: {e}")


if __name__ == "__main__":
    unittest.main()
