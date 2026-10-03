"""EDMC Standalone Plugin: Fleet Carrier Parking Finder.

Adapts the EDR parking search logic to identify available parking slots nearby.
"""

from __future__ import annotations

import functools
import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import l10n
from config import appname, config

from parking_finder import ParkingSystemFinder

# Semantic Versioning compliance for EDMC Plugin Registry
__version__ = "1.3.0"

# Official EDMC localization setup for plugins
plugin_tl = functools.partial(l10n.translations.tl, context=__file__)

# Official EDMC logging configuration for plugins
plugin_name = Path(__file__).parent.name
logger = logging.getLogger(f"{appname}.{plugin_name}")

# Global plugin user interface instance and runtime journal state for FC data
plugin_ui_instance: ParkingPluginUI | None = None
active_threads: list[threading.Thread] = []
latest_carrier_journal_data: dict = {}


class ToolTip:
    """Lightweight tooltip management integrated with EDMC's native style."""

    def __init__(self, widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event=None) -> None:
        if self.tooltip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 2

        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")

        # Uses standard widgets to correctly inherit the graphic theme context
        label = ttk.Label(
            self.tooltip_window,
            text=self.text,
            relief="solid",
            borderwidth=1,
            padding=3,
        )
        label.pack()

    def hide_tooltip(self, event=None) -> None:
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

    def update_text(self, new_text: str) -> None:
        self.text = new_text


class ParkingPluginUI:
    """Manages the EDMC user interface frame and asynchronous parking queries."""

    def __init__(self, parent_frame: tk.Widget) -> None:
        """Initialize the parking plugin UI component.

        Args:
            parent_frame (tk.Widget): The parent frame provided by EDMC.

        """
        self.parent = parent_frame
        self.current_system = "Unknown"
        # LANG: Placeholder text for the star system entry field
        self.placeholder = plugin_tl("Enter system name...")

        # Main container frame strictly complying with EDMC plugin_app return standards (tk.Frame)
        self.frame: tk.Frame = tk.Frame(self.parent)

        # Styled LabelFrame inside the base frame
        self.labelframe: ttk.LabelFrame = ttk.LabelFrame(
            self.frame,
            # LANG: Name of the plugin or UI title
            text=plugin_tl("Carrier Parking Finder"),
        )

        # StringVar to track input changes reactively
        self.system_var = tk.StringVar()
        self.system_var.trace_add("write", self._validate_input)

        self.system_entry: ttk.Entry = ttk.Entry(
            self.labelframe, width=18, textvariable=self.system_var
        )
        self.search_btn: ttk.Button = ttk.Button(
            self.labelframe,
            # LANG: Button or action label to trigger a search
            text=plugin_tl("Search"),
            command=self.start_search,
            state="disabled",  # Starts disabled because field starts with placeholder
        )
        self.result_label: ttk.Label = ttk.Label(
            self.labelframe,
            # LANG: Status message while waiting for client/journal updates
            text=plugin_tl("Waiting for game data..."),
            foreground="gray",
        )

        # Explanatory default tooltip detailing how theoretical slot fallback works
        self.result_tooltip = ToolTip(
            self.result_label,
            # LANG: Explanatory tooltip for theoretical max slots fallback
            plugin_tl(
                "Live carrier telemetry is unavailable for this system. The slot count reflects maximum theoretical body capacity without filtering out currently occupied slots."
            ),
        )

        self._setup_ui()
        self._init_placeholder()

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

    def _init_placeholder(self) -> None:
        """Initialize placeholder text and event bindings for the system entry field."""
        self.system_var.set(self.placeholder)
        self.system_entry.config(foreground="gray")

        self.system_entry.bind("<FocusIn>", self._on_entry_focus_in)
        self.system_entry.bind("<FocusOut>", self._on_entry_focus_out)

    def _on_entry_focus_in(self, event) -> None:
        """Handle entry focus-in event to clear placeholder text."""
        if self.system_var.get() == self.placeholder:
            self.system_var.set("")
            self.system_entry.config(foreground="black")

    def _on_entry_focus_out(self, event) -> None:
        """Handle entry focus-out event to restore placeholder if empty."""
        if not self.system_var.get().strip():
            self.system_var.set(self.placeholder)
            self.system_entry.config(foreground="gray")

    def _validate_input(self, *args) -> None:
        """Enable or disable the search button based on whether the entry has valid text."""
        val = self.system_var.get().strip()
        if not val or val == self.placeholder:
            self.search_btn.config(state="disabled")
        else:
            self.search_btn.config(state="normal")

    def update_current_system(self, system_name: str) -> None:
        """Automatically update the system entry field when the commander jumps.

        Args:
            system_name (str): The name of the current star system.
        """
        if system_name and system_name != self.current_system:
            self.current_system = system_name
            self.system_var.set(system_name)
            self.system_entry.config(foreground="black")

    def start_search(self) -> None:
        """Initiate the parking search in a separate background thread to avoid freezing EDMC."""
        system_name = self.system_var.get().strip()
        if not system_name or system_name == self.placeholder:
            logger.debug(
                "Manual search triggered with empty or placeholder system name. Ignoring."
            )
            return

        logger.debug("Triggering manual search for system: '%s'", system_name)
        self.result_label.config(
            # LANG: Status message shown while querying around a specific star system
            text=plugin_tl("Searching around {system}...").format(system=system_name),
            foreground="blue",
        )
        self.search_btn.config(state="disabled")

        # Explanatory tooltip for ongoing search process
        self.result_tooltip.update_text(
            # LANG: Explanatory tooltip during background search query
            plugin_tl(
                "Querying regional databases and evaluating gravitational body capacities in the background."
            )
        )

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
        # Insert Fleet Carrier position and saturation info from the journal as filters
        # only if the current system matches the one being verified.
        fc_filter_data = None
        if (
            latest_carrier_journal_data
            and system_name.strip().lower() == self.current_system.strip().lower()
        ):
            fc_filter_data = latest_carrier_journal_data

        finder = ParkingSystemFinder(system_name, callback=None, fc_data=fc_filter_data)
        result = finder.search_sync()

        # Check shutdown state before triggering tkinter updates to avoid hanging
        if not config.shutting_down and self.frame:
            try:
                self.frame.after(0, lambda: self._update_result(result))
            except RuntimeError:
                logger.exception("RuntimeError scheduling UI update on main thread")
        else:
            logger.warning("EDMC is shutting down; skipping UI result update.")

    def _update_result(self, result: dict | None) -> None:
        """Update the UI label with the search outcome.

        Args:
            result (dict | None): The system information dictionary or None if not found.
        """
        # Re-enable button only if there is valid text in the entry
        self._validate_input()

        if result:
            # Show a clear warning if the input system is permit-locked
            if result.get("permit_locked", False):
                name = result.get("name", "Unknown")
                logger.debug("Search result: System '%s' is permit-locked.", name)
                # LANG: Warning message when the system is permit-locked and parking is impossible
                text = plugin_tl(
                    "System {name} is permit-locked: parking is not possible here!"
                ).format(name=name)
                self.result_label.config(text=text, foreground="orange")
                self.result_tooltip.update_text(
                    # LANG: Explanatory tooltip for permit-locked restriction
                    plugin_tl(
                        "Access to this star system is restricted by a regional permit. You cannot jump or park here without acquiring it first."
                    )
                )
                return

            name = result.get("name", "Unknown")
            dist = result.get("distance", 0.0)
            parking = result.get("parking", {})
            slots = parking.get("slots", 0)
            body_name_list = parking.get("body_name_list")
            is_empirical = parking.get("is_empirical", False)

            logger.debug(
                "Search successful: Found parking at '%s' (%s Ly, Slots: %s, Bodies: %s)",
                name,
                dist,
                slots,
                body_name_list,
            )

            # Inform user about specific short body list if available, otherwise show theoretical max slots
            if is_empirical and body_name_list:
                # LANG: Status message showing the found parking body name and distance
                text = plugin_tl(
                    "Found: {name} ({dist:.1f} Ly) - Park at body: {body_name_list}"
                ).format(name=name, dist=dist, body_name_list=body_name_list)
                self.result_tooltip.update_text(
                    # LANG: Explanatory tooltip for empirical data confirmation
                    plugin_tl(
                        "Verified using precise, real-time player journal telemetry reported for specific celestial bodies in this system."
                    )
                )
            else:
                # LANG: Status message showing the max theoretical parking slots and distance
                text = plugin_tl(
                    "Found: {name} ({dist:.1f} Ly) - Max Theoretical Slots: {slots}"
                ).format(name=name, dist=dist, slots=slots)

                self.result_tooltip.update_text(
                    # LANG: Explanatory tooltip for theoretical max slots fallback
                    plugin_tl(
                        "Live carrier telemetry is unavailable for this system. The slot count reflects maximum theoretical body capacity without filtering out currently occupied slots."
                    )
                )

            self.result_label.config(text=text, foreground="green")
        else:
            logger.debug("Search finished with no suitable parking locations found.")
            # LANG: Error message when no valid parking location is found in range
            text = plugin_tl("No suitable parking system found within range.")
            self.result_label.config(text=text, foreground="red")
            self.result_tooltip.update_text(
                # LANG: Explanatory tooltip when search yields no matches
                plugin_tl(
                    "No systems matching safety and distance criteria were found within your configured jump radius."
                )
            )


def plugin_start3(plugin_dir: str) -> str:
    """Called by EDMC when the plugin is started (Python 3 standard).

    Args:
        plugin_dir (str): Path to the plugin directory.

    Returns:
        str: Name of the plugin.
    """
    logger.info("Starting ED Parking Finder plugin v%s.", __version__)
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
    logger.info("Stopping ED Parking Finder plugin. Cleaning up background threads...")
    for thread in active_threads:
        if thread.is_alive():
            thread.join(timeout=1.0)
    logger.info("ED Parking Finder plugin successfully stopped.")


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
    global latest_carrier_journal_data
    if system:
        if plugin_ui_instance:
            plugin_ui_instance.update_current_system(system)

        # Extract Fleet Carrier information (e.g., CarrierJump or CarrierStats events) if available
        event_type = entry.get("event")
        if event_type in ("CarrierJump", "CarrierStats", "Location"):
            position_info = {
                "system": system,
                "body_id": entry.get("BodyID"),
                "body_name": entry.get("Body"),
                "station": station,
                "saturation": entry.get("Saturation") or entry.get("CarrierSpace"),
            }
            latest_carrier_journal_data = position_info
            logger.debug("Captured updated FC journal telemetry for system: %s", system)
