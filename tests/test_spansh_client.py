"""Tests for the Spansh systems-search client."""

from __future__ import annotations

import sys
import types
import unittest
from importlib import import_module
from unittest.mock import Mock, patch

config_stub = types.ModuleType("config")
config_stub.__dict__.update(
    appname="EDMC",
    config=types.SimpleNamespace(shutting_down=False),
)
sys.modules.setdefault("config", config_stub)

spansh_client = import_module("spansh_client")
SpanshClient = spansh_client.SpanshClient
SpanshAPIError = spansh_client.SpanshAPIError
SpanshTimeoutError = spansh_client.SpanshTimeoutError


class SpanshSystemsSearchTests(unittest.TestCase):
    """Verify search requests exclude permit-required systems."""

    def test_search_filters_out_permit_required_systems(self) -> None:
        """The distance search includes Spansh's permit-free filter."""
        client = SpanshClient()
        response = Mock(
            status_code=200,
            json=Mock(
                return_value={
                    "count": 1,
                    "from": 0,
                    "results": [{"name": "Nearby System", "needs_permit": False}],
                }
            ),
        )

        with patch(
            f"{spansh_client.__name__}.requests.post", return_value=response
        ) as post:
            results = client.search_systems_around("Reference", radius=25, limit=20)

        self.assertEqual(results, [{"name": "Nearby System", "needs_permit": False}])
        payload = post.call_args.kwargs["json"]
        self.assertEqual(
            payload["filters"],
            {
                "distance": {
                    "min": 0,
                    "max": 25,
                    "reference_system": "Reference",
                },
                "needs_permit": {"value": False},
            },
        )
        self.assertEqual(payload["size"], 20)
        self.assertEqual(payload["sort"], [{"distance": {"direction": "asc"}}])
        self.assertEqual(post.call_args.args[0], SpanshClient.SEARCH_SYSTEMS_URL)
        self.assertEqual(post.call_args.kwargs["headers"], client.headers)
        self.assertEqual(post.call_args.kwargs["timeout"], client.timeout)

    def test_search_accepts_supported_response_shapes(self) -> None:
        """Raw lists and documented result containers yield system records."""
        systems = [{"name": "Nearby System"}]
        response_bodies = (
            (systems, systems),
            ({"results": systems}, systems),
            ({"systems": systems}, systems),
            ({"results": [], "systems": systems}, []),
        )

        for body, expected in response_bodies:
            with self.subTest(body=body):
                response = Mock(status_code=200, json=Mock(return_value=body))
                with patch(
                    f"{spansh_client.__name__}.requests.post",
                    return_value=response,
                ):
                    self.assertEqual(
                        SpanshClient().search_systems_around("Reference"), expected
                    )

    def test_search_rejects_malformed_response_structures(self) -> None:
        """Missing results and non-record list entries raise an API error."""
        response_bodies = (
            {},
            {"results": None},
            {"results": "not a list"},
            {"results": [{"name": "Valid"}, None]},
            "not a JSON object",
            None,
        )

        for body in response_bodies:
            with self.subTest(body=body):
                response = Mock(status_code=200, json=Mock(return_value=body))
                with patch(
                    f"{spansh_client.__name__}.requests.post",
                    return_value=response,
                ):
                    try:
                        SpanshClient().search_systems_around("Reference")
                    except SpanshAPIError:
                        continue
                    self.fail("Malformed response should raise SpanshAPIError")

    def test_search_converts_timeout_to_timeout_error(self) -> None:
        """Request timeouts are surfaced with their original exception as cause."""
        timeout = spansh_client.requests.Timeout("request timed out")

        with patch(
            f"{spansh_client.__name__}.requests.post",
            side_effect=timeout,
        ):
            try:
                SpanshClient(timeout=7).search_systems_around("Reference")
            except SpanshTimeoutError as raised:
                self.assertIs(raised.__cause__, timeout)
            else:
                self.fail("Request timeout should raise SpanshTimeoutError")

    def test_search_converts_http_errors_to_api_error(self) -> None:
        """Non-200 responses report the status and response text."""
        response = Mock(status_code=503, text="service unavailable")

        with patch(
            f"{spansh_client.__name__}.requests.post",
            return_value=response,
        ):
            try:
                SpanshClient().search_systems_around("Reference")
            except SpanshAPIError as error:
                self.assertIn("503: service unavailable", str(error))
            else:
                self.fail("Non-200 response should raise SpanshAPIError")

        response.json.assert_not_called()

    def test_search_converts_invalid_json_to_api_error(self) -> None:
        """JSON decoding failures are exposed as API errors with their cause."""
        invalid_json = ValueError("invalid JSON")
        response = Mock(
            status_code=200,
            json=Mock(side_effect=invalid_json),
        )

        with patch(
            f"{spansh_client.__name__}.requests.post",
            return_value=response,
        ):
            try:
                SpanshClient().search_systems_around("Reference")
            except SpanshAPIError as error:
                self.assertIn("Invalid JSON response", str(error))
                self.assertIs(error.__cause__, invalid_json)
            else:
                self.fail("Invalid JSON should raise SpanshAPIError")


if __name__ == "__main__":
    unittest.main()
