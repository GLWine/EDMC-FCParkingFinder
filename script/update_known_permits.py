"""Fetch Spansh's complete permit list for the scheduled GitHub Action."""

from __future__ import annotations

import sys
import types
from pathlib import Path

repository_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repository_root))

try:
    import config  # type: ignore[import-not-found]
except ImportError:
    config = types.ModuleType("config")
    config.__dict__["appname"] = "EDMC"
    sys.modules["config"] = config

from permit_service import PermitListService  # noqa: E402


def main() -> None:
    """Update the repository's tracked permit-list JSON from Spansh."""
    service = PermitListService(
        data_path=repository_root / "data" / "known_permits.json"
    )
    service.refresh_from_spansh()


if __name__ == "__main__":
    main()
