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


if __name__ == "__main__":
    unittest.main()
