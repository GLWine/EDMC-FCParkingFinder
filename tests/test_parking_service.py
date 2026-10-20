"""Tests for the Spansh-to-parking-core integration service."""

from __future__ import annotations

import sys
import types
import unittest
from importlib import import_module
from unittest.mock import Mock

config_stub = types.ModuleType("config")
config_stub.appname = "EDMC"
config_stub.config = types.SimpleNamespace(shutting_down=False)
sys.modules.setdefault("config", config_stub)

parking_service = import_module("parking_service")
ParkingSearchService = parking_service.ParkingSearchService
ParkingServiceError = parking_service.ParkingServiceError
SpanshAPIError = import_module("spansh_client").SpanshAPIError


class ParkingSearchServiceTests(unittest.TestCase):
    """Verify provider-to-core coordination and data handling."""

    def test_search_normalizes_records_and_returns_core_result(self) -> None:
        """The service cleans records and forwards them to the core."""
        records = [
            {
                "name": "  Test System  ",
                "distance": 0,
                "information": {"bodyCount": 2},
                "bodies": [],
            },
            {"name": "", "distance": 3},
        ]
        client = Mock()
        client.search_systems_around.return_value = records
        service = ParkingSearchService(client)

        result = service.search("Test System")

        client.search_systems_around.assert_called_once_with("Test System", radius=25)
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Test System")
        self.assertEqual(result["distance"], 0)
        self.assertEqual(result["parking"]["slots"], 32)
        self.assertEqual(records[0]["name"], "  Test System  ")

    def test_search_wraps_provider_errors_and_preserves_cause(self) -> None:
        """Provider failures are exposed as service errors with their cause."""
        client = Mock()
        provider_error = SpanshAPIError("network unavailable")
        client.search_systems_around.side_effect = provider_error
        service = ParkingSearchService(client)

        try:
            service.search("Test System")
        except ParkingServiceError as error:
            self.assertIs(error.__cause__, provider_error)
        else:
            self.fail("Expected the service to surface a provider error.")

    def test_search_rejects_empty_system_name(self) -> None:
        """An empty target is rejected before a provider request."""
        service = ParkingSearchService(Mock())

        try:
            service.search("  ")
        except ValueError:
            return
        self.fail("Expected an empty system name to raise ValueError.")


if __name__ == "__main__":
    unittest.main()
