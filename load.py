"""EDMC plugin lifecycle hooks and connections to the parking UI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import config

from logger_utils import logger
from parking_service import ParkingSearchService
from parking_ui import ParkingPluginUI

if TYPE_CHECKING:
    import tkinter as tk

__version__ = "1.3.1"

plugin_ui_instance: ParkingPluginUI | None = None
latest_carrier_journal_data: dict = {}


def plugin_start3(plugin_dir: str) -> str:
    """Initialize the plugin lifecycle when EDMC loads the plugin."""
    logger.info("Starting ED Parking Finder plugin v%s.", __version__)
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
    if plugin_ui_instance:
        plugin_ui_instance.shutdown()


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
