"""
EDMC Standalone Plugin: Fleet Carrier Parking Finder.

Adapts the EDR parking search logic to identify available parking slots nearby.
"""

from __future__ import annotations

import functools
import logging
import os
import threading
import tkinter as tk
from tkinter import ttk

from config import appname, config

import l10n
from parking_finder import EDParkingSystemFinder

# Semantic Versioning compliance for EDMC Plugin Registry
__version__ = "1.1.2"

# Official EDMC localization setup for plugins
plugin_tl = functools.partial(l10n.translations.tl, context=__file__)

# Official EDMC logging configuration for plugins
plugin_name = os.path.basename(os.path.dirname(__file__))
logger = logging.getLogger(f"{appname}.{plugin_name}")

# Global plugin user interface instance
plugin_ui_instance: ParkingPluginUI | None = None
active_threads: list[threading.Thread] = []


class ParkingPluginUI:
    """Manages the EDMC user interface frame and asynchronous parking queries."""

    def __init__(self, parent_frame: tk.Widget) -> None:
        """Initialize the parking plugin UI component.

        Args:
            parent_frame (tk.Widget): The parent frame provided by EDMC.
        """
        self.parent = parent_frame
        self.current_system = "Unknown"

        # Main container frame strictly complying with EDMC plugin_app return standards (tk.Frame)
        self.frame: tk.Frame = tk.Frame(self.parent)

        # Styled LabelFrame inside the base frame
        self.labelframe: ttk.LabelFrame = ttk.LabelFrame(
            self.frame,
            # LANG: Name of the plugin or UI title
            text=plugin_tl("Carrier Parking Finder"),
        )
        self.system_entry: ttk.Entry = ttk.Entry(self.labelframe, width=18)
        self.search_btn: ttk.Button = ttk.Button(
            self.labelframe,
            # LANG: Button or action label to trigger a search
            text=plugin_tl("Search"),
            command=self.start_search,
        )
        self.result_label: ttk.Label = ttk.Label(
            self.labelframe,
            # LANG: Status message while waiting for client/journal updates
            text=plugin_tl("Waiting for game data..."),
            foreground="gray",
        )

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the layout and widgets following EDMC styling guidelines."""
        self.frame.pack(fill=tk.X, padx=5, pady=5)
        self.labelframe.pack(fill=tk.X, padx=2, pady=2, ipadx=5, ipady=5)

        # Star system input field
        # LANG: Label for star system input or display
        ttk.Label(self.labelframe, text=plugin_tl("System:")).grid(
            row=0, column=0, sticky=tk.W, padx=2, pady=2
        )
        self.system_entry.grid(row=0, column=1, padx=2, pady=2)

        # Button to trigger manual search
        self.search_btn.grid(row=0, column=2, padx=2, pady=2)

        # Label to display search status and results
        self.result_label.grid(
            row=1, column=0, columnspan=3, sticky=tk.W, padx=2, pady=4
        )

    def update_current_system(self, system_name: str) -> None:
        """Automatically update the system entry field when the commander jumps.

        Args:
            system_name (str): The name of the current star system.
        """
        if system_name and system_name != self.current_system:
            self.current_system = system_name
            self.system_entry.delete(0, tk.END)
            self.system_entry.insert(0, system_name)

    def start_search(self) -> None:
        """Initiate the parking search in a separate background thread to avoid freezing EDMC."""
        system_name = self.system_entry.get().strip()
        if not system_name:
            return

        self.result_label.config(
            # LANG: Status message shown while querying around a specific star system
            text=plugin_tl("Searching around {system}...").format(system=system_name),
            foreground="blue",
        )
        self.search_btn.config(state="disabled")

        # Asynchronous execution of the search via a managed worker thread
        thread = threading.Thread(
            target=self._run_query, args=(system_name,), daemon=True
        )
        active_threads.append(thread)
        thread.start()

    def _run_query(self, system_name: str) -> None:
        """Execute the synchronous search query via the finder logic.

        Args:
            system_name (str): The target star system to search around.
        """
        finder = EDParkingSystemFinder(system_name, callback=None)
        result = finder.search_sync()

        # Check shutdown state before triggering tkinter updates to avoid hanging
        if not config.shutting_down and self.frame:
            try:
                self.frame.after(0, lambda: self._update_result(result))
            except RuntimeError as e:
                logger.debug(f"Error scheduling UI update: {e}")

    def _update_result(self, result: dict | None) -> None:
        """Update the UI label with the search outcome.

        Args:
            result (dict | None): The system information dictionary or None if not found.
        """
        self.search_btn.config(state="normal")
        if result:
            name = result.get("name", "Unknown")
            dist = result.get("distance", 0.0)
            slots = result.get("parking", {}).get("slots", 0)
            # LANG: Result format showing carrier name, distance, and available slots
            text = plugin_tl("Found: {name} ({dist:.1f} Ly) - Slots: {slots}").format(
                name=name, dist=dist, slots=slots
            )
            self.result_label.config(text=text, foreground="green")
        else:
            self.result_label.config(
                # LANG: Error message when no valid parking location is found in range
                text=plugin_tl("No suitable parking system found within range."),
                foreground="red",
            )


def plugin_start3(plugin_dir: str) -> str:
    """Called by EDMC when the plugin is started (Python 3 standard).

    Args:
        plugin_dir (str): Path to the plugin directory.

    Returns:
        str: Name of the plugin.
    """
    logger.info("Starting ED Parking Finder plugin.")
    return "ED Parking Finder"


def plugin_app(parent: tk.Widget) -> tk.Widget:
    """Create and return the UI frame embedded inside the EDMC main window.

    Args:
        parent (tk.Widget): Parent container widget.

    Returns:
        tk.Widget: The initialized plugin UI frame.
    """
    global plugin_ui_instance
    plugin_ui_instance = ParkingPluginUI(parent)
    return plugin_ui_instance.frame


def plugin_stop() -> None:
    """Called when EDMC is closing down. Joins active background threads safely."""
    logger.info("Stopping ED Parking Finder plugin.")
    for thread in active_threads:
        if thread.is_alive():
            thread.join(timeout=1.0)


def journal_entry(
    cmdr: str, is_beta: bool, system: str, station: str, entry: dict, state: dict
) -> None:
    """Hook called by EDMC on every journal event (e.g., FSDJump, Location).

    Args:
        cmdr (str): Commander name.
        is_beta (bool): True if running in beta context.
        system (str): Current star system name.
        station (str): Current station name.
        entry (dict): Raw journal event payload.
        state (dict): Current game state snapshot.
    """
    if plugin_ui_instance and system:
        plugin_ui_instance.update_current_system(system)
