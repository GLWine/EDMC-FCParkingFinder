"""EDMC Standalone Plugin: Fleet Carrier Parking Finder.

Adapts the EDR parking search logic to identify available parking slots nearby.
"""

from __future__ import annotations

import functools
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING

import l10n

from logger_utils import logger
from parking_service import ParkingSearchService, ParkingServiceError
from spansh_client import SpanshAPIError, SpanshTimeoutError

if TYPE_CHECKING:
    from collections.abc import Callable

    from parking_result import ParkingResult

plugin_tl = functools.partial(
    l10n.translations.tl, context=str(Path(__file__).with_name("load.py"))
)


class ToolTip:
    """Lightweight tooltip management integrated with EDMC's native style."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        """Bind a tooltip to a widget.

        Args:
            widget: Widget whose enter and leave events control the tooltip.
            text: Text displayed in the tooltip window.

        """
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event: tk.Event | None = None) -> None:
        """Display the tooltip below the widget unless it is already visible.

        Args:
            event: Tkinter event supplied by the widget binding.

        """
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

    def hide_tooltip(self, event: tk.Event | None = None) -> None:
        """Destroy the tooltip window when it is open.

        Args:
            event: Tkinter event supplied by the widget binding.

        """
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

    def update_text(self, new_text: str) -> None:
        """Replace the text displayed the next time the tooltip is shown.

        Args:
            new_text: New tooltip content.

        """
        self.text = new_text


class ParkingPluginUI:
    """Manages the EDMC user interface frame and asynchronous parking queries."""

    def __init__(
        self,
        parent_frame: tk.Widget,
        service: ParkingSearchService,
        is_shutting_down: Callable[[], bool],
    ) -> None:
        """Initialize the parking plugin UI component.

        Args:
            parent_frame (tk.Widget): The parent frame provided by EDMC.
            service: Component that acquires and evaluates system data.
            is_shutting_down: Callback reporting EDMC's shutdown state.

        """
        self.parent = parent_frame
        self.service = service
        self.is_shutting_down = is_shutting_down
        self.current_system = "Unknown"
        self.carrier_journal_data: dict = {}
        self.active_threads: list[threading.Thread] = []
        # LANG: Placeholder text for the star system entry field
        self.placeholder = plugin_tl("Enter system name...")

        # Main container frame strictly complying with EDMC plugin_app return standards (tk.Frame)
        self.frame: tk.Frame = tk.Frame(self.parent)

        # StringVar to track input changes reactively
        self.system_var = tk.StringVar()
        self.system_var.trace_add("write", self._on_system_var_changed)

        self.system_entry: ttk.Entry = ttk.Entry(
            self.frame, width=18, textvariable=self.system_var
        )
        self.search_btn: ttk.Button = ttk.Button(
            self.frame,
            # LANG: Button or action label to trigger a search
            text=plugin_tl("Search"),
            command=self.start_search,
            state="disabled",  # Starts disabled because field starts with placeholder
        )
        self.result_label: ttk.Label = ttk.Label(
            self.frame,
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
        self.frame.pack(fill=tk.X, padx=0, pady=0)
        self.frame.grid_columnconfigure(1, weight=1)

        # Star system input field
        # LANG: Label for star system input or display
        ttk.Label(self.frame, text=plugin_tl("System:")).grid(
            row=0, column=0, sticky=tk.W, padx=(0, 4), pady=2
        )
        self.system_entry.grid(row=0, column=1, sticky=tk.EW, padx=(0, 4), pady=2)

        # Button to trigger manual search
        self.search_btn.grid(row=0, column=2, sticky=tk.W, pady=2)

        # Label to display search status and results
        self.result_label.grid(
            row=1, column=0, columnspan=3, sticky=tk.W, pady=(2, 2)
        )

    def _on_system_var_changed(self, *args: object) -> None:
        """Keep the search button and field width synced with the current text."""
        self._validate_input(*args)
        self._sync_entry_width()

    def _sync_entry_width(self) -> None:
        """Match EDMC's compact UI by keeping the field readable without making it too narrow."""
        value = self.system_var.get().strip()
        if not value or value == self.placeholder:
            width = 18
        else:
            width = max(18, min(len(value) + 2, 34))
        self.system_entry.configure(width=width)

    def _init_placeholder(self) -> None:
        """Initialize placeholder text and event bindings for the system entry field."""
        self.system_var.set(self.placeholder)
        self.system_entry.config(foreground="gray")

        self.system_entry.bind("<FocusIn>", self._on_entry_focus_in)
        self.system_entry.bind("<FocusOut>", self._on_entry_focus_out)
        self.system_entry.bind("<Return>", self._on_entry_return)

    def _on_entry_return(self, event: tk.Event) -> str:
        """Start a search on Enter when the Search button is enabled."""
        if self.search_btn.instate(["!disabled"]):
            self.start_search()
        return "break"

    def _on_entry_focus_in(self, event: tk.Event) -> None:
        """Handle entry focus-in event to clear placeholder text."""
        if self.system_var.get() == self.placeholder:
            self.system_var.set("")
            self.system_entry.config(foreground="black")
        self._sync_entry_width()

    def _on_entry_focus_out(self, event: tk.Event) -> None:
        """Handle entry focus-out event to restore placeholder if empty."""
        if not self.system_var.get().strip():
            self.system_var.set(self.placeholder)
            self.system_entry.config(foreground="gray")
        self._sync_entry_width()

    def _validate_input(self, *args: object) -> None:
        """Enable or disable the search button based on whether the entry has valid text."""
        val = self.system_var.get().strip()
        if not val or val == self.placeholder:
            self.search_btn.config(state="disabled")
        else:
            self.search_btn.config(state="normal")

    @staticmethod
    def _access_status_label(status: str | None, reason: str | None) -> str:
        """Return the localized access status for the selected system."""
        if status == "restricted":
            if reason == "spansh_requires_permit":
                # LANG: Access status shown when the provider explicitly rejects a system due to a permit requirement.
                return plugin_tl("Restricted (permit required)")
            # LANG: Access status shown when a system is explicitly blocked.
            return plugin_tl("Restricted")
        if status == "allowed":
            # LANG: Access status shown when a system is permitted without restriction.
            return plugin_tl("Allowed")
        # LANG: Access status shown when the provider did not report permit status.
        return plugin_tl("Unknown")

    @staticmethod
    def _access_status_detail(status: str | None) -> str:
        """Describe why access is allowed, restricted, or still uncertain."""
        if status == "restricted":
            # LANG: Detail explaining a provider-reported permit block.
            return plugin_tl("Spansh flagged this system as requiring a permit.")
        if status == "allowed":
            # LANG: Detail explaining that the provider explicitly reports access.
            return plugin_tl("Spansh explicitly reports access is allowed.")
        # LANG: Detail explaining that permit status was not reported by the provider.
        return plugin_tl("Permit status was not reported by the provider.")

    @staticmethod
    def _describe_slot_value(value: int | None) -> str:
        """Convert slot values and unknown states to user-readable text."""
        if value is None:
            # LANG: Placeholder text for unknown parking occupancy values.
            return plugin_tl("unknown")
        return str(value)

    def update_current_system(self, system_name: str) -> None:
        """Automatically update the system entry field when the commander jumps.

        Args:
            system_name (str): The name of the current star system.

        """
        if system_name and system_name != self.current_system:
            self.current_system = system_name
            self.system_var.set(system_name)
            self.system_entry.config(foreground="black")
            self._sync_entry_width()

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
        self.active_threads.append(thread)
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
            self.carrier_journal_data
            and system_name.strip().lower() == self.current_system.strip().lower()
        ):
            fc_filter_data = self.carrier_journal_data

        try:
            result = self.service.search(system_name, fc_data=fc_filter_data)
        except ParkingServiceError as exc:
            logger.exception("Parking search failed for '%s'.", system_name)
            if not self.is_shutting_down() and self.frame:
                cause = exc.__cause__
                if isinstance(cause, SpanshTimeoutError):
                    # LANG: Error message for a timed-out Spansh request.
                    message = plugin_tl(
                        "Search failed: timeout while contacting Spansh."
                    )
                elif isinstance(cause, SpanshAPIError):
                    # LANG: Error message for a Spansh API response failure.
                    message = plugin_tl("Search failed: Spansh API error.")
                else:
                    # LANG: Error message for a generic provider or network failure.
                    message = plugin_tl("Search failed: provider or network error.")
                try:
                    self.frame.after(0, lambda: self._update_error(message))
                except RuntimeError:
                    logger.exception("RuntimeError scheduling UI error update")
            return

        # Check shutdown state before triggering tkinter updates to avoid hanging
        if not self.is_shutting_down() and self.frame:
            try:
                self.frame.after(0, lambda: self._update_result(result))
            except RuntimeError:
                logger.exception("RuntimeError scheduling UI update on main thread")
        else:
            logger.warning("EDMC is shutting down; skipping UI result update.")

    def _update_result(self, result: ParkingResult | None) -> None:
        """Update the UI label with the search outcome.

        Args:
            result (dict | None): The system information dictionary or None if not found.

        """
        # Re-enable button only if there is valid text in the entry
        self._validate_input()

        if result:
            name = result.get("name", "Unknown")
            dist = result.get("distance", 0.0)
            access_status = result.get("access_status", "unknown")
            access_reason = result.get("access_reason")
            parking = result.get("parking", {})
            slots = parking.get("theoretical_slots", parking.get("slots", 0))
            confirmed = parking.get("confirmed_available_slots")
            estimated = parking.get("estimated_available_slots")
            carrier_count = parking.get("spansh_reported_carrier_count")
            provider_stale = parking.get("provider_data_stale")
            body_name_list = parking.get("body_name_list")
            body_details = parking.get("body_details", [])
            is_empirical = parking.get("is_empirical", False)

            logger.debug(
                "Search successful: Found parking at '%s' (%s Ly, Slots: %s, Bodies: %s)",
                name,
                dist,
                slots,
                body_name_list or body_details,
            )

            access_label = self._access_status_label(access_status, access_reason)
            access_detail = self._access_status_detail(access_status)
            lines = [
                # LANG: Result header showing the selected system and distance.
                plugin_tl("System: {name} ({distance:.1f} Ly)").format(
                    name=name, distance=dist
                ),
                # LANG: Access status line for the selected system result.
                plugin_tl("Access: {status}").format(status=access_label),
                # LANG: Additional access-detail line for the selected system result.
                plugin_tl("Access detail: {detail}").format(detail=access_detail),
                # LANG: Theoretical capacity line for the selected system result.
                plugin_tl("Theoretical capacity: {slots}").format(slots=slots),
                # LANG: Confirmed-availability line for the selected system result.
                plugin_tl("Confirmed availability: {slots}").format(
                    slots=self._describe_slot_value(confirmed)
                ),
                # LANG: Estimated-availability line for the selected system result.
                plugin_tl("Estimated availability: {slots}").format(
                    slots=self._describe_slot_value(estimated)
                ),
            ]

            if carrier_count is not None:
                # LANG: Provider-reported carrier count for the selected system result.
                carrier_text = plugin_tl("Spansh carrier count: {count}").format(
                    count=carrier_count
                )
                if provider_stale:
                    # LANG: Marker shown when the provider data is older than 24 hours.
                    stale_text = plugin_tl("(stale data)")
                    carrier_text = f"{carrier_text} {stale_text}"
                lines.append(carrier_text)

            if body_name_list:
                lines.append(
                    # LANG: Body list taken from provider data without claiming an exact landing location.
                    plugin_tl("Provider body data: {bodies}").format(
                        bodies=body_name_list
                    )
                )
            elif is_empirical and body_details:
                body_names = ", ".join(
                    str(body.get("name", "Unknown")) for body in body_details if body
                )
                if body_names:
                    lines.append(
                        # LANG: Body names taken from journal data without claiming confirmed player-slot placement.
                        plugin_tl("Journal body data: {bodies}").format(
                            bodies=body_names
                        )
                    )

            text = "\n".join(lines)
            self.result_label.config(text=text, foreground="green")

            tooltip_lines = [
                # LANG: Tooltip line summarizing the provider's access status.
                plugin_tl("Access status from the provider: {status}").format(
                    status=access_label
                ),
                self._access_status_detail(access_status),
            ]
            if provider_stale:
                tooltip_lines.append(
                    # LANG: Tooltip warning that provider data is stale and therefore heuristic.
                    plugin_tl(
                        "Spansh data is older than 24 hours, so this is only a heuristic estimate."
                    )
                )
            if confirmed is None:
                tooltip_lines.append(
                    # LANG: Tooltip explaining why confirmed availability cannot be asserted.
                    plugin_tl(
                        "Confirmed availability remains unknown because the plugin did not receive occupancy data."
                    )
                )
            if estimated is None:
                tooltip_lines.append(
                    # LANG: Tooltip explaining why the estimated availability is unknown.
                    plugin_tl(
                        "Estimated availability is unknown because Spansh did not provide station data."
                    )
                )
            self.result_tooltip.update_text(" ".join(tooltip_lines))
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

    def update_carrier_journal_data(self, data: dict) -> None:
        """Store the latest carrier telemetry received from EDMC's journal."""
        self.carrier_journal_data = data

    def _update_error(self, message: str) -> None:
        """Show a search error after its details have been logged."""
        self._validate_input()
        self.result_label.config(
            text=message,
            foreground="red",
        )
        self.result_tooltip.update_text(
            # LANG: Tooltip explaining where to find details about search failures
            plugin_tl("See the EDMC log for technical details.")
        )

    def shutdown(self) -> None:
        """Wait briefly for active background searches during plugin shutdown."""
        for thread in self.active_threads:
            if thread.is_alive():
                thread.join(timeout=1.0)
