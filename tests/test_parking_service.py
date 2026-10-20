"""Tests for the Spansh-to-parking-core integration service."""

from __future__ import annotations

import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
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
parking_finder = import_module("parking_finder")


class ParkingSearchServiceTests(unittest.TestCase):
    """Verify provider-to-core coordination and data handling."""

    def test_search_normalizes_records_and_returns_core_result(self) -> None:
        """The service cleans records and forwards them to the core."""
        records = [
            {
                "name": "  Test System  ",
                "distance": 0,
                "information": {"bodyCount": 2, "requirePermit": False},
                "bodies": [{"name": "Test System A 1"}, {"name": "Test System A 2"}],
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
        self.assertEqual(result["access_status"], "allowed")
        self.assertIsNone(result["access_reason"])
        self.assertEqual(result["parking"]["theoretical_slots"], 32)
        self.assertIsNone(result["parking"]["confirmed_available_slots"])
        self.assertIsNone(result["parking"]["spansh_reported_carrier_count"])
        self.assertIsNone(result["parking"]["estimated_available_slots"])
        self.assertIsNone(result["parking"]["body_assignment_complete"])
        self.assertIsNone(result["parking"]["provider_data_stale"])
        self.assertEqual(
            result["parking"]["body_details"],
            [{"name": "Test System A 1"}, {"name": "Test System A 2"}],
        )
        self.assertEqual(result["parking"]["body_name_list"], None)
        self.assertFalse(result["parking"]["is_empirical"])
        self.assertEqual(records[0]["name"], "  Test System  ")

    def test_missing_access_and_occupancy_data_remain_unknown(self) -> None:
        """Legacy records do not imply reported access or confirmed capacity."""
        client = Mock()
        client.search_systems_around.return_value = [
            {
                "name": "Test System",
                "distance": 1,
                "information": {"bodyCount": 1},
            }
        ]

        result = ParkingSearchService(client).search("Reference")

        self.assertIsNotNone(result)
        self.assertEqual(result["access_status"], "unknown")
        self.assertEqual(result["access_reason"], "permit_status_not_reported")
        self.assertEqual(result["parking"]["theoretical_slots"], 16)
        self.assertIsNone(result["parking"]["confirmed_available_slots"])
        self.assertIsNone(result["parking"]["spansh_reported_carrier_count"])
        self.assertIsNone(result["parking"]["estimated_available_slots"])
        self.assertIsNone(result["parking"]["body_assignment_complete"])
        self.assertIsNone(result["parking"]["provider_data_stale"])
        self.assertEqual(result["parking"]["slots"], 16)

    def test_exact_target_is_evaluated_before_closer_candidates(self) -> None:
        """The exact reference system is checked before nearby records."""
        client = Mock()
        client.search_systems_around.return_value = [
            {
                "name": "Reference System",
                "distance": 8,
                "information": {"bodyCount": 4, "requirePermit": False},
            },
            {
                "name": "Reference System B",
                "distance": 1,
                "information": {"bodyCount": 1, "requirePermit": False},
            },
        ]

        result = ParkingSearchService(client).search(" reference system ")

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Reference System")
        self.assertEqual(result["distance"], 0)
        self.assertEqual(result["parking"]["theoretical_slots"], 64)

    def test_target_with_unreported_information_is_evaluated(self) -> None:
        """A live Spansh record with null information remains usable."""
        client = Mock()
        client.search_systems_around.return_value = [
            {
                "name": "Reference System",
                "distance": 0,
                "information": None,
                "bodies": [{"name": "Reference System A 1"}],
            }
        ]

        result = ParkingSearchService(client).search("Reference System")

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Reference System")
        self.assertEqual(result["access_status"], "unknown")
        self.assertEqual(result["access_reason"], "permit_status_not_reported")
        self.assertEqual(result["parking"]["theoretical_slots"], 16)
        self.assertIsNone(result["parking"]["confirmed_available_slots"])

    def test_top_level_needs_permit_flag_sets_access_status(self) -> None:
        """Spansh's current top-level flag is normalized for the result contract."""
        client = Mock()
        client.search_systems_around.return_value = [
            {
                "name": "Reference System",
                "distance": 0,
                "needs_permit": False,
                "information": {"bodyCount": 1},
            }
        ]

        result = ParkingSearchService(client).search("Reference System")

        self.assertIsNotNone(result)
        self.assertEqual(result["access_status"], "allowed")
        self.assertIsNone(result["access_reason"])

    def test_top_level_permit_required_flag_triggers_fallback(self) -> None:
        """The provider's top-level restriction is rejected before selection."""
        client = Mock()
        client.search_systems_around.return_value = [
            {
                "name": "Reference System",
                "distance": 0,
                "needs_permit": True,
                "information": {"bodyCount": 1},
            },
            {
                "name": "Nearby System",
                "distance": 2,
                "needs_permit": False,
                "information": {"bodyCount": 1},
            },
        ]

        result = ParkingSearchService(client).search("Reference System")

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Nearby System")
        self.assertEqual(result["access_status"], "allowed")

    def test_theoretical_capacity_uses_floor_and_system_cap(self) -> None:
        """Reported body counts produce theoretical slots within the defined bounds."""
        for body_count, expected_slots in (
            (0, 16),
            (1, 16),
            (2, 32),
            (8, 128),
            (9, 128),
        ):
            with self.subTest(body_count=body_count):
                client = Mock()
                client.search_systems_around.return_value = [
                    {
                        "name": "Reference System",
                        "distance": 0,
                        "information": {
                            "bodyCount": body_count,
                            "requirePermit": False,
                        },
                    }
                ]

                result = ParkingSearchService(client).search("Reference System")

                self.assertIsNotNone(result)
                self.assertEqual(result["parking"]["theoretical_slots"], expected_slots)
                self.assertIsNone(result["parking"]["confirmed_available_slots"])

    def test_spansh_top_level_body_count_sets_theoretical_capacity(self) -> None:
        """Spansh's top-level body_count field is normalized for the core."""
        client = Mock()
        client.search_systems_around.return_value = [
            {
                "name": "Fixture System",
                "distance": 0,
                "body_count": 40,
                "bodies": [
                    {
                        "name": "Fixture System",
                        "type": "Star",
                        "subtype": "G (White-Yellow) Star",
                    }
                ],
            }
        ]

        result = ParkingSearchService(client).search("Fixture System")

        self.assertIsNotNone(result)
        self.assertEqual(result["parking"]["theoretical_slots"], 128)
        self.assertEqual(len(result["parking"]["body_details"]), 1)
        self.assertIsNone(result["parking"]["confirmed_available_slots"])

    def test_carriers_are_assigned_to_nearest_bodies_with_sixteen_slots_each(
        self,
    ) -> None:
        """Reported carrier distances fill nearby body capacity before the next."""
        client = Mock()
        client.search_systems_around.return_value = [
            {
                "name": "Reference System",
                "distance": 0,
                "body_count": 2,
                "bodies": [
                    {"name": "Reference System A", "distance_to_arrival": 0},
                    {"name": "Reference System B", "distance_to_arrival": 1000},
                ],
                "stations": [
                    {
                        "type": "Drake-Class Carrier",
                        "distance_to_arrival": 100,
                    }
                    for _ in range(16)
                ]
                + [
                    {
                        "type": "Drake-Class Carrier",
                        "distance_to_arrival": 1000,
                    }
                ],
            }
        ]

        result = ParkingSearchService(client).search("Reference System")

        self.assertIsNotNone(result)
        parking = result["parking"]
        self.assertEqual(parking["spansh_reported_carrier_count"], 17)
        self.assertEqual(parking["estimated_available_slots"], 15)
        self.assertTrue(parking["body_assignment_complete"])
        self.assertIsNone(parking["confirmed_available_slots"])
        self.assertEqual(
            [
                (
                    body["spansh_reported_carrier_count"],
                    body["estimated_available_slots"],
                )
                for body in parking["body_details"]
            ],
            [(16, 0), (1, 15)],
        )
        self.assertEqual(
            sum(body["estimated_available_slots"] for body in parking["body_details"]),
            parking["estimated_available_slots"],
        )

    def test_carriers_without_arrival_distance_are_omitted_and_logged(self) -> None:
        """Undistanced carriers are excluded from counts and logged at debug."""
        client = Mock()
        client.search_systems_around.return_value = [
            {
                "name": "Reference System",
                "distance": 0,
                "body_count": 1,
                "bodies": [{"name": "Reference System A", "distance_to_arrival": 0}],
                "stations": [
                    {"type": "Drake-Class Carrier", "name": "Missing Distance"},
                    {
                        "type": "Drake-Class Carrier",
                        "name": "Located Carrier",
                        "distance_to_arrival": 100,
                    },
                ],
            }
        ]

        with unittest.mock.patch.object(parking_finder.logger, "debug") as debug:
            result = ParkingSearchService(client).search("Reference System")

        self.assertIsNotNone(result)
        parking = result["parking"]
        self.assertEqual(parking["spansh_reported_carrier_count"], 1)
        self.assertEqual(parking["estimated_available_slots"], 15)
        self.assertTrue(parking["body_assignment_complete"])
        self.assertEqual(parking["body_details"][0]["spansh_reported_carrier_count"], 1)
        self.assertEqual(parking["body_details"][0]["estimated_available_slots"], 15)
        debug.assert_any_call(
            "Ignoring Spansh carrier '%s' without a valid arrival distance.",
            "Missing Distance",
        )

    def test_system_data_older_than_24_hours_is_logged_and_system_rejected(
        self,
    ) -> None:
        """Stale full-system data is logged and still triggers candidate fallback."""
        client = Mock()
        old_timestamp = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        client.search_systems_around.return_value = [
            {
                "name": "Reference System",
                "distance": 0,
                "body_count": 1,
                "updated_at": old_timestamp,
                "stations": [
                    {
                        "type": "Drake-Class Carrier",
                        "distance_to_arrival": 100,
                    }
                    for _ in range(16)
                ],
            },
            {
                "name": "Nearby System",
                "distance": 2,
                "body_count": 1,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "stations": [],
            },
        ]

        with unittest.mock.patch.object(parking_finder.logger, "debug") as debug:
            result = ParkingSearchService(client).search("Reference System")

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Nearby System")
        debug.assert_any_call(
            "Spansh system data for '%s' is older than 24 hours.",
            "Reference System",
        )
        debug.assert_any_call(
            "System '%s' rejected: Spansh reports %s carriers for %s theoretical slots (data stale: %s).",
            "Reference System",
            16,
            16,
            True,
        )

    def test_recent_system_data_is_not_marked_stale(self) -> None:
        """A current Spansh update timestamp is recognized as fresh."""
        client = Mock()
        client.search_systems_around.return_value = [
            {
                "name": "Reference System",
                "distance": 0,
                "body_count": 1,
                "updated_at": (
                    datetime.now(timezone.utc) - timedelta(hours=23)
                ).isoformat(),
                "stations": [],
            }
        ]

        result = ParkingSearchService(client).search("Reference System")

        self.assertIsNotNone(result)
        self.assertFalse(result["parking"]["provider_data_stale"])

    def test_full_target_uses_nearest_fallback(self) -> None:
        """Spansh-reported carriers filling all theoretical slots reject a system."""
        client = Mock()
        client.search_systems_around.return_value = [
            {
                "name": "Reference System",
                "distance": 0,
                "body_count": 1,
                "stations": [
                    {
                        "type": "Drake-Class Carrier",
                        "distance_to_arrival": 100,
                    }
                    for _ in range(16)
                ],
            },
            {
                "name": "Nearby System",
                "distance": 2,
                "body_count": 1,
                "stations": [],
            },
        ]

        result = ParkingSearchService(client).search("Reference System")

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Nearby System")
        self.assertEqual(result["parking"]["spansh_reported_carrier_count"], 0)
        self.assertEqual(result["parking"]["estimated_available_slots"], 16)
        self.assertIsNone(result["parking"]["confirmed_available_slots"])

    def test_128_reported_carriers_fill_system_capacity(self) -> None:
        """A system at the global 128-carrier cap is skipped."""
        client = Mock()
        client.search_systems_around.return_value = [
            {
                "name": "Reference System",
                "distance": 0,
                "body_count": 20,
                "stations": [
                    {
                        "type": "Drake-Class Carrier",
                        "distance_to_arrival": 100,
                    }
                    for _ in range(128)
                ],
            },
            {
                "name": "Nearby System",
                "distance": 2,
                "body_count": 1,
                "stations": [],
            },
        ]

        result = ParkingSearchService(client).search("Reference System")

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Nearby System")

    def test_missing_body_details_and_high_capacity_do_not_confirm_or_exclude(
        self,
    ) -> None:
        """Body details and theoretical capacity do not imply occupancy data."""
        client = Mock()
        client.search_systems_around.return_value = [
            {
                "name": "Maximum Capacity Candidate",
                "distance": 1,
                "information": {"bodyCount": 12, "requirePermit": False},
                "bodies": [],
            },
            {
                "name": "Further Candidate",
                "distance": 2,
                "information": {"bodyCount": 1, "requirePermit": False},
            },
        ]

        result = ParkingSearchService(client).search("Reference System")

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Maximum Capacity Candidate")
        self.assertEqual(result["distance"], 1)
        self.assertEqual(result["parking"]["theoretical_slots"], 128)
        self.assertEqual(result["parking"]["body_details"], [])
        self.assertIsNone(result["parking"]["confirmed_available_slots"])

    def test_missing_body_count_keeps_theoretical_fallback_and_unknown_occupancy(
        self,
    ) -> None:
        """Missing body count uses the documented minimum estimate, not occupancy."""
        client = Mock()
        client.search_systems_around.return_value = [
            {
                "name": "Reference System",
                "distance": 0,
                "information": {"requirePermit": False},
            }
        ]

        result = ParkingSearchService(client).search("Reference System")

        self.assertIsNotNone(result)
        self.assertEqual(result["parking"]["theoretical_slots"], 16)
        self.assertIsNone(result["parking"]["confirmed_available_slots"])

    def test_missing_target_falls_back_to_nearest_candidate(self) -> None:
        """When Spansh omits the target, the closest eligible candidate wins."""
        client = Mock()
        client.search_systems_around.return_value = [
            {
                "name": "Far System",
                "distance": 4,
                "information": {"bodyCount": 3, "requirePermit": False},
            },
            {
                "name": "Near System",
                "distance": 2,
                "information": {"bodyCount": 1, "requirePermit": False},
            },
        ]

        result = ParkingSearchService(client).search("Missing Target")

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Near System")
        self.assertEqual(result["distance"], 2)

    def test_inaccessible_target_falls_back_to_nearby_system(self) -> None:
        """Permit-locked targets are skipped in favor of an eligible system."""
        client = Mock()
        client.search_systems_around.return_value = [
            {
                "name": "Reference System",
                "distance": 0,
                "information": {"bodyCount": 2, "requirePermit": True},
            },
            {
                "name": "Nearby System",
                "distance": 3,
                "information": {"bodyCount": 1, "requirePermit": False},
            },
        ]

        result = ParkingSearchService(client).search("Reference System")

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Nearby System")
        self.assertEqual(result["distance"], 3)

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
