"""EDMC plugin lifecycle hooks and connections to the parking UI."""

from __future__ import annotations

from pathlib import Path
from threading import Event, Thread
from typing import TYPE_CHECKING

from config import config

from logger_utils import logger
from parking_service import ParkingSearchService
from parking_ui import ParkingPluginUI
from permit_service import PermitListError, PermitListService

if TYPE_CHECKING:
    import tkinter as tk

__version__ = Path(__file__).with_name("version").read_text(encoding="utf-8").strip()

plugin_ui_instance: ParkingPluginUI | None = None
latest_carrier_journal_data: dict = {}
permit_update_stop_event: Event | None = None
permit_update_thread: Thread | None = None


def plugin_start3(plugin_dir: str) -> str:
    """Initialize the plugin lifecycle when EDMC loads the plugin."""
    global permit_update_stop_event, permit_update_thread
    logger.info("Starting ED Parking Finder plugin v%s.", __version__)
    permit_update_stop_event = Event()
    permit_update_thread = Thread(
        target=_update_known_permits,
        args=(permit_update_stop_event,),
        name="SpanshPermitListUpdater",
        daemon=True,
    )
    permit_update_thread.start()
    return "ED Parking Finder"


def plugin_app(parent: tk.Widget) -> tk.Widget:
    """Create the UI and connect it to the parking-search service."""
    global plugin_ui_instance
    plugin_ui_instance = ParkingPluginUI(
        parent,
        ParkingSearchService(),
        lambda: config.shutting_down,
    )
    if latest_carrier_journal_data:
        plugin_ui_instance.update_carrier_journal_data(latest_carrier_journal_data)
    return plugin_ui_instance.frame


def plugin_stop() -> None:
    """Stop UI-managed search threads during EDMC shutdown."""
    logger.info("Stopping ED Parking Finder plugin.")
    if permit_update_stop_event:
        permit_update_stop_event.set()
    if permit_update_thread:
        permit_update_thread.join(timeout=1)
    if plugin_ui_instance:
        plugin_ui_instance.shutdown()


def _update_known_permits(stop_event: Event) -> None:
    """Download the Action-published permit list without blocking EDMC startup."""
    permit_list_service = PermitListService()
    while not stop_event.is_set():
        try:
            permit_list_service.refresh_if_due()
            wait_seconds = permit_list_service.seconds_until_refresh()
            if wait_seconds <= 0:
                wait_seconds = 24 * 60 * 60
        except (OSError, ValueError, PermitListError):
            logger.exception("Unable to refresh the GitHub permit list.")
            wait_seconds = 24 * 60 * 60
        stop_event.wait(wait_seconds)


def journal_entry(
    cmdr: str, is_beta: bool, system: str, station: str, entry: dict, state: dict
) -> None:
    """Forward current-system and carrier journal updates to the UI."""
    global latest_carrier_journal_data
    if not system:
        return

    if plugin_ui_instance:
        plugin_ui_instance.update_current_system(system)

    event_type = entry.get("event")
    if event_type in ("CarrierJump", "CarrierStats", "Location"):
        latest_carrier_journal_data = {
            "system": system,
            "body_id": entry.get("BodyID"),
            "body_name": entry.get("Body"),
            "station": station,
            "saturation": entry.get("Saturation") or entry.get("CarrierSpace"),
        }
        if plugin_ui_instance:
            plugin_ui_instance.update_carrier_journal_data(latest_carrier_journal_data)
        logger.debug("Captured updated FC journal telemetry for system: %s", system)
