"""
EDMC Standalone Plugin: Fleet Carrier Parking Finder.
Adapts the EDR parking search logic to identify available parking slots nearby.
"""

import threading
import tkinter as tk
from tkinter import ttk
import plug

from parking_finder import EDRParkingSystemFinder

# Initialization of EDMC standards for logging and translations
_ = plug.get_translation(__file__)
logger = plug.get_logger(__name__)

# Global plugin user interface instance
plugin_ui_instance = None


class ParkingPluginUI:
    """
    Manages the EDMC user interface frame and asynchronous parking queries.
    """

    def __init__(self, parent_frame: tk.Widget) -> None:
        """
        Initialize the parking plugin UI component.

        Args:
            parent_frame (tk.Widget): The parent frame provided by EDMC.
        """
        self.parent = parent_frame
        self.current_system = "Unknown"
        self.frame = None
        self.system_entry = None
        self.search_btn = None
        self.result_label = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the layout and widgets following EDMC styling guidelines."""
        self.frame = ttk.LabelFrame(self.parent, text=_("Carrier Parking Finder"))
        self.frame.pack(fill=tk.X, padx=5, pady=5, ipadx=5, ipady=5)

        # Star system input field
        ttk.Label(self.frame, text=_("System:")).grid(row=0, column=0, sticky=tk.W, padx=2, pady=2)
        self.system_entry = ttk.Entry(self.frame, width=18)
        self.system_entry.grid(row=0, column=1, padx=2, pady=2)

        # Button to trigger manual search
        self.search_btn = ttk.Button(self.frame, text=_("Search"), command=self.start_search)
        self.search_btn.grid(row=0, column=2, padx=2, pady=2)

        # Label to display search status and results
        self.result_label = ttk.Label(self.frame, text=_("Waiting for game data..."), foreground="gray")
        self.result_label.grid(row=1, column=0, columnspan=3, sticky=tk.W, padx=2, pady=4)

    def update_current_system(self, system_name: str) -> None:
        """
        Automatically update the system entry field when the commander jumps.

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
            text=_("Searching around {system}...").format(system=system_name),
            foreground="blue"
        )
        self.search_btn.config(state="disabled")

        # Asynchronous execution of the search
        threading.Thread(
            target=self._run_query,
            args=(system_name,),
            daemon=True
        ).start()

    def _run_query(self, system_name: str) -> None:
        """
        Execute the synchronous search query via the finder logic.

        Args:
            system_name (str): The target star system to search around.
        """
        finder = EDRParkingSystemFinder(system_name, callback=None)
        result = finder.search_sync()
        # Safe UI update on the main Tkinter thread
        self.frame.after(0, lambda: self._update_result(result))

    def _update_result(self, result: dict) -> None:
        """
        Update the UI label with the search outcome.

        Args:
            result (dict): The system information dictionary or None if not found.
        """
        self.search_btn.config(state="normal")
        if result:
            name = result.get("name", "Unknown")
            dist = result.get("distance", 0.0)
            slots = result.get("parking", {}).get("slots", 0)
            text = _("Found: {name} ({dist:.1f} ly) - Slots: {slots}").format(
                name=name, dist=dist, slots=slots
            )
            self.result_label.config(text=text, foreground="green")
        else:
            self.result_label.config(
                text=_("No suitable parking system found within range."),
                foreground="red"
            )


def plugin_start3(plugin_dir: str) -> str:
    """
    Called by EDMC when the plugin is started (Python 3 standard).

    Args:
        plugin_dir (str): Path to the plugin directory.

    Returns:
        str: Name of the plugin.
    """
    global plugin_ui_instance
    logger.info(_("Starting EDR Parking Finder plugin."))
    return "EDR Parking Finder"


def plugin_app(parent: tk.Widget) -> tk.Widget:
    """
    Create and return the UI frame embedded inside the EDMC main window.

    Args:
        parent (tk.Widget): Parent container widget.

    Returns:
        tk.Widget: The initialized plugin UI frame.
    """
    global plugin_ui_instance
    plugin_ui_instance = ParkingPluginUI(parent)
    return plugin_ui_instance.frame


def journal_entry(cmdr: str, is_beta: bool, system: str, station: str, entry: dict, state: dict) -> None:
    """
    Hook called by EDMC on every journal event (e.g., FSDJump, Location).

    Args:
        cmdr (str): Commander name.
        is_beta (bool): True if running in beta context.
        system (str): Current star system name.
        station (str): Current station name.
        entry (dict): Raw journal event payload.
        state (dict): Current game state snapshot.
    """
    global plugin_ui_instance
    if plugin_ui_instance and system:
        plugin_ui_instance.update_current_system(system)
