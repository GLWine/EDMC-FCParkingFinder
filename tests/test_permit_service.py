"""Tests for the Spansh permit-list client and persistence service."""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from importlib import import_module
from pathlib import Path
from unittest.mock import MagicMock, Mock, mock_open, patch

config_stub = types.ModuleType("config")
config_stub.appname = "EDMC"
config_stub.config = types.SimpleNamespace(shutting_down=False)
sys.modules.setdefault("config", config_stub)

permit_service = import_module("permit_service")
spansh_client = import_module("spansh_client")
parking_finder = import_module("parking_finder")
PermitListService = permit_service.PermitListService
PermitListError = permit_service.PermitListError
SpanshAPIError = spansh_client.SpanshAPIError
SpanshClient = spansh_client.SpanshClient
ParkingSystemFinder = parking_finder.ParkingSystemFinder


class SpanshPermitSearchTests(unittest.TestCase):
    """Verify complete, paginated retrieval of permit-required systems."""

    def test_searches_every_page_using_spansh_permit_filter(self) -> None:
        """Uses Spansh's permit filter and returns records from all pages."""
        client = SpanshClient()
        client.PERMIT_SYSTEMS_PAGE_SIZE = 2
        responses = [
            Mock(
                status_code=200,
                json=Mock(
                    return_value={
                        "count": 3,
                        "from": 0,
                        "results": [
                            {"name": "System A", "needs_permit": True},
                            {"name": "System B", "needs_permit": True},
                        ],
                    }
                ),
            ),
            Mock(
                status_code=200,
                json=Mock(
                    return_value={
                        "count": 3,
                        "from": 2,
                        "results": [{"name": "System C", "needs_permit": True}],
                    }
                ),
            ),
        ]

        with patch(
            f"{spansh_client.__name__}.requests.post", side_effect=responses
        ) as post:
            systems = client.search_permit_systems()

        self.assertEqual(systems, ["System A", "System B", "System C"])
        self.assertEqual(post.call_count, 2)
        first_payload = post.call_args_list[0].kwargs["json"]
        second_payload = post.call_args_list[1].kwargs["json"]
        self.assertEqual(first_payload["filters"], {"needs_permit": {"value": True}})
        self.assertEqual(first_payload["page"], 0)
        self.assertEqual(second_payload["page"], 1)

    def test_rejects_incomplete_pages(self) -> None:
        """Rejects pagination that declares systems but omits a later page."""
        client = SpanshClient()
        client.PERMIT_SYSTEMS_PAGE_SIZE = 1
        response = Mock(
            status_code=200,
            json=Mock(
                return_value={
                    "count": 2,
                    "from": 0,
                    "results": [{"name": "System A", "needs_permit": True}],
                }
            ),
        )

        with patch(f"{spansh_client.__name__}.requests.post", return_value=response):
            try:
                client.search_permit_systems()
            except SpanshAPIError:
                return
        self.fail("Expected incomplete pagination to raise SpanshAPIError.")


class PermitListServiceTests(unittest.TestCase):
    """Verify 30-day refresh metadata and atomic list persistence."""

    def test_persists_timestamp_even_when_the_list_does_not_change(self) -> None:
        """Advances the update timestamp even when the system set is unchanged."""
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "known_permits.json"
            old_timestamp = datetime.now(timezone.utc) - timedelta(days=31)
            data_path.write_text(
                json.dumps(
                    {
                        "updated_at": old_timestamp.isoformat(),
                        "systems": ["System A"],
                    }
                ),
                encoding="utf-8",
            )
            client = Mock()
            client.search_permit_systems.return_value = ["System A"]
            service = PermitListService(client, data_path)

            service.refresh_from_spansh()

            saved = json.loads(data_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["systems"], ["System A"])
            self.assertNotEqual(saved["updated_at"], old_timestamp.isoformat())
            self.assertEqual(client.search_permit_systems.call_count, 1)
            self.assertGreater(service.seconds_until_refresh(), 0)

    def test_downloads_action_data_when_local_copy_expires(self) -> None:
        """Downloads the GitHub-published list without querying Spansh."""
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "known_permits.json"
            old_timestamp = datetime.now(timezone.utc) - timedelta(days=31)
            data_path.write_text(
                json.dumps(
                    {"updated_at": old_timestamp.isoformat(), "systems": ["Old"]}
                ),
                encoding="utf-8",
            )
            published_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            response = Mock(
                json=Mock(
                    return_value={
                        "updated_at": published_at,
                        "systems": ["System B", "System A"],
                    }
                )
            )
            client = Mock()

            with patch(
                f"{permit_service.__name__}.requests.get", return_value=response
            ) as get:
                refreshed = PermitListService(client, data_path).refresh_if_due()

            self.assertTrue(refreshed)
            get.assert_called_once_with(
                permit_service.PERMIT_LIST_URL,
                timeout=permit_service.PERMIT_LIST_TIMEOUT,
            )
            response.raise_for_status.assert_called_once()
            client.search_permit_systems.assert_not_called()
            saved = json.loads(data_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["systems"], ["System A", "System B"])
            self.assertEqual(saved["updated_at"], f"{published_at[:19]}Z")

    def test_skips_refresh_within_the_30_day_window(self) -> None:
        """Does not call GitHub while the saved successful update is recent."""
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "known_permits.json"
            data_path.write_text(
                json.dumps(
                    {
                        "updated_at": datetime.now(timezone.utc)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "systems": ["System A"],
                    }
                ),
                encoding="utf-8",
            )
            client = Mock()

            with patch(f"{permit_service.__name__}.requests.get") as get:
                refreshed = PermitListService(client, data_path).refresh_if_due()

            self.assertFalse(refreshed)
            get.assert_not_called()
            client.search_permit_systems.assert_not_called()

    def test_failed_spansh_fetch_leaves_the_existing_file_unchanged(self) -> None:
        """Preserves the prior list and timestamp when the Action fetch fails."""
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "known_permits.json"
            existing_content = '{"updated_at":"old","systems":["System A"]}\n'
            data_path.write_text(existing_content, encoding="utf-8")
            client = Mock()
            client.search_permit_systems.side_effect = SpanshAPIError("unavailable")

            try:
                PermitListService(client, data_path).refresh_from_spansh()
            except SpanshAPIError:
                pass
            else:
                self.fail("Expected a failed fetch to raise SpanshAPIError.")

            self.assertEqual(data_path.read_text(encoding="utf-8"), existing_content)

    def test_rejects_stale_action_data_without_replacing_local_copy(self) -> None:
        """Rejects old GitHub data and retains the current local list."""
        with tempfile.TemporaryDirectory() as directory:
            data_path = Path(directory) / "known_permits.json"
            existing_content = (
                '{"updated_at":"2026-10-19T00:00:00Z","systems":["Local"]}\n'
            )
            data_path.write_text(existing_content, encoding="utf-8")
            stale_timestamp = datetime.now(timezone.utc) - timedelta(days=36)
            response = Mock(
                json=Mock(
                    return_value={
                        "updated_at": stale_timestamp.isoformat(),
                        "systems": ["Stale"],
                    }
                )
            )

            with patch(
                f"{permit_service.__name__}.requests.get", return_value=response
            ):
                try:
                    PermitListService(data_path=data_path).refresh_from_github()
                except PermitListError:
                    pass
                else:
                    self.fail("Expected stale Action data to be rejected.")

            self.assertEqual(data_path.read_text(encoding="utf-8"), existing_content)


class PermitListLoadingTests(unittest.TestCase):
    """Verify the parking core accepts the metadata-bearing JSON format."""

    def test_loads_system_names_from_the_updated_json_schema(self) -> None:
        """Reads permit names from systems while ignoring update metadata."""
        base_path = MagicMock()
        base_path.parent = base_path
        data_directory = MagicMock()
        base_path.__truediv__.return_value = data_directory
        data_file = Mock()
        data_directory.__truediv__.return_value = data_file
        data_file.exists.return_value = True
        data_file.open = MagicMock()
        data_file.open.return_value.__enter__.return_value = mock_open(
            read_data='{"updated_at":"2026-10-20T00:00:00Z","systems":["Sol","Beta Hydri"]}'
        ).return_value
        finder = ParkingSystemFinder.__new__(ParkingSystemFinder)

        with patch.object(parking_finder, "Path", return_value=base_path):
            permits = finder._load_known_permits()

        self.assertEqual(permits, {"sol", "beta hydri"})


if __name__ == "__main__":
    unittest.main()
