"""Refresh and persist Spansh's complete known permit-system list."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from logger_utils import logger
from spansh_client import SpanshClient

PERMIT_LIST_REFRESH_INTERVAL = timedelta(days=30)
PERMIT_LIST_MAX_SOURCE_AGE = timedelta(days=35)
PERMIT_LIST_FUTURE_TOLERANCE = timedelta(minutes=5)
PERMIT_LIST_URL = (
    "https://raw.githubusercontent.com/GLWine/EDMC-FCParkingFinder/main/"
    "data/known_permits.json"
)
PERMIT_LIST_TIMEOUT = 15


class PermitListError(Exception):
    """Raised when the published permit list cannot be safely retrieved."""


class PermitListService:
    """Keep the local cache synchronized with Spansh data published on GitHub."""

    def __init__(
        self, client: SpanshClient | None = None, data_path: Path | None = None
    ) -> None:
        """Create the service with optional provider and JSON-file overrides."""
        self.client = client or SpanshClient()
        self.data_path = data_path or (
            Path(__file__).parent / "data" / "known_permits.json"
        )

    def seconds_until_refresh(self) -> float:
        """Return seconds until the saved list is due for refresh, or zero."""
        try:
            with self.data_path.open(encoding="utf-8") as data_file:
                data = json.load(data_file)
        except FileNotFoundError:
            return 0
        except (OSError, UnicodeError, json.JSONDecodeError):
            logger.warning("Permit list is unreadable; a refresh is due.")
            return 0

        if not isinstance(data, dict):
            return 0

        updated_at = data.get("updated_at")
        if not isinstance(updated_at, str):
            return 0
        try:
            timestamp = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        except ValueError:
            return 0
        if timestamp.tzinfo is None:
            return 0

        next_refresh = timestamp + PERMIT_LIST_REFRESH_INTERVAL
        return max(0.0, (next_refresh - datetime.now(timezone.utc)).total_seconds())

    def refresh_if_due(self) -> bool:
        """Download the GitHub-published list if the local copy is 30 days old."""
        if self.seconds_until_refresh() > 0:
            logger.debug("Local permit list is current; refresh is not due.")
            return False
        self.refresh_from_github()
        return True

    def refresh_from_github(self) -> None:
        """Download and validate the list published by the scheduled GitHub Action."""
        try:
            response = requests.get(PERMIT_LIST_URL, timeout=PERMIT_LIST_TIMEOUT)
            response.raise_for_status()
            document = response.json()
        except requests.RequestException as error:
            logger.exception("Failed to download the GitHub permit list.")
            raise PermitListError(
                "Unable to download the published permit list."
            ) from error
        except ValueError as error:
            logger.exception("The GitHub permit list is not valid JSON.")
            raise PermitListError(
                "The published permit list is not valid JSON."
            ) from error

        if not isinstance(document, dict):
            raise PermitListError("The published permit list has an invalid structure.")
        updated_at = document.get("updated_at")
        systems = document.get("systems")
        if (
            not isinstance(updated_at, str)
            or not isinstance(systems, list)
            or any(not isinstance(name, str) or not name.strip() for name in systems)
        ):
            raise PermitListError("The published permit list has invalid fields.")

        try:
            timestamp = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise PermitListError(
                "The published permit list has an invalid update timestamp."
            ) from error
        if timestamp.tzinfo is None:
            raise PermitListError(
                "The published permit list timestamp has no timezone."
            )
        age = datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)
        if age > PERMIT_LIST_MAX_SOURCE_AGE or age < -PERMIT_LIST_FUTURE_TOLERANCE:
            raise PermitListError(
                "The GitHub permit list is stale or has a future update timestamp."
            )

        normalized_names = [name.strip() for name in systems]
        if len({name.casefold() for name in normalized_names}) != len(normalized_names):
            raise PermitListError("The published permit list contains duplicates.")

        self._save_document(
            {
                "updated_at": timestamp.astimezone(timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
                "systems": sorted(normalized_names, key=str.casefold),
            }
        )
        logger.info(
            "Downloaded %d permit systems published by GitHub.",
            len(normalized_names),
        )

    def refresh_from_spansh(self) -> None:
        """Fetch the complete permit list from Spansh for the GitHub Action."""
        systems = self.client.search_permit_systems()
        document = {
            "updated_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "systems": sorted(systems, key=str.casefold),
        }
        self._save_document(document)
        logger.info(
            "Updated known_permits.json from Spansh with %d systems.",
            len(systems),
        )

    def _save_document(self, document: dict[str, object]) -> None:
        """Atomically replace the cached or repository permit-list file."""
        self.data_path.parent.mkdir(parents=True, exist_ok=True)

        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.data_path.parent,
                prefix=f".{self.data_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = temporary_file.name
                json.dump(document, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            Path(temporary_path).replace(self.data_path)
        except OSError:
            logger.exception("Failed to save the local permit list.")
            if temporary_path is not None:
                try:
                    Path(temporary_path).unlink(missing_ok=True)
                except OSError:
                    logger.exception("Failed to remove temporary permit-list file.")
            raise
