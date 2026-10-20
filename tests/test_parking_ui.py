"""Tests for localized parking UI results and thread-safe updates."""

from __future__ import annotations

import sys
import threading
import types
import unittest
from importlib import import_module
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

if TYPE_CHECKING:
    from collections.abc import Callable

config_stub = types.ModuleType("config")
config_stub.__dict__.update(
    appname="EDMC",
    config=types.SimpleNamespace(shutting_down=False),
)
sys.modules.setdefault("config", config_stub)

l10n_stub = types.ModuleType("l10n")


def translate(text: str, context: str | None = None) -> str:
    """Provide identity translation in UI unit tests."""
    del context
    return text


l10n_stub.__dict__.update(
    translations=types.SimpleNamespace(tl=translate),
)
sys.modules.setdefault("l10n", l10n_stub)

parking_ui = import_module("parking_ui")
ParkingPluginUI = parking_ui.ParkingPluginUI
ParkingServiceError = import_module("parking_service").ParkingServiceError
spansh_client = import_module("spansh_client")


def capture_scheduled(
    callbacks: list[tuple[int, Callable[[], None]]],
    scheduling_threads: list[int],
) -> Callable[[int, Callable[[], None]], None]:
    """Capture a Tk callback and the thread that queued it."""

    def schedule(delay: int, callback: Callable[[], None]) -> None:
        scheduling_threads.append(threading.get_ident())
        callbacks.append((delay, callback))

    return schedule


def capture_error_update(
    update_threads: list[tuple[int, str]],
) -> Callable[[str], None]:
    """Capture the thread and message used by an error callback."""

    def update(message: str) -> None:
        update_threads.append((threading.get_ident(), message))

    return update


class ParkingPluginUITests(unittest.TestCase):
    """Check user-facing results and main-thread Tkinter scheduling."""

    def make_ui(self, service: Mock | None = None) -> ParkingPluginUI:
        """Create a UI instance without initializing a display server."""
        ui = ParkingPluginUI.__new__(ParkingPluginUI)
        ui.service = service or Mock()
        ui.is_shutting_down = lambda: False
        ui.current_system = "Reference"
        ui.carrier_journal_data = {}
        ui.placeholder = "Enter system name..."
        ui.frame = Mock()
        ui.system_var = Mock()
        ui.system_var.get.return_value = "Reference"
        ui.search_btn = Mock()
        ui.result_label = Mock()
        ui.result_tooltip = Mock()
        return ui

    def test_enter_starts_search_only_when_search_button_is_enabled(self) -> None:
        """Enter mirrors the button and cannot bypass its disabled state."""
        ui = self.make_ui()
        ui.start_search = Mock()

        ui.search_btn.instate.return_value = True
        self.assertEqual(ui._on_entry_return(Mock()), "break")
        ui.start_search.assert_called_once_with()

        ui.start_search.reset_mock()
        ui.search_btn.instate.return_value = False
        self.assertEqual(ui._on_entry_return(Mock()), "break")
        ui.start_search.assert_not_called()

    @staticmethod
    def make_result(**overrides: object) -> dict:
        """Build a contract-shaped result with conservative availability data."""
        parking = {
            "theoretical_slots": 32,
            "confirmed_available_slots": None,
            "spansh_reported_carrier_count": None,
            "estimated_available_slots": None,
            "body_assignment_complete": None,
            "provider_data_stale": None,
            "body_details": [],
            "slots": 32,
            "body_name_list": None,
            "is_empirical": False,
        }
        result = {
            "name": "Candidate",
            "distance": 2.5,
            "parking": parking,
        }
        result.update(overrides)
        return result

    def render(self, result: dict | None) -> str:
        """Render one result and return the visible label text."""
        ui = self.make_ui()
        ui._update_result(result)
        return ui.result_label.config.call_args.kwargs["text"]

    def test_theoretical_result_keeps_unknown_availability_explicit(self) -> None:
        """Unknown values are shown as unknown, not as zero or confirmed."""
        result = self.make_result()
        result["parking"]["body_name_list"] = "A 1"

        ui = self.make_ui()
        ui._update_result(result)
        text = ui.result_label.config.call_args.kwargs["text"]
        tooltip = ui.result_tooltip.update_text.call_args.args[0]

        self.assertIn("Theoretical capacity: 32", text)
        self.assertIn("Confirmed availability: unknown", text)
        self.assertIn("Estimated availability: unknown", text)
        self.assertIn("Provider body data: A 1", text)
        self.assertNotIn("access", text.casefold())
        self.assertNotIn("access", tooltip.casefold())
        self.assertNotIn("confirmed location", text.casefold())
        self.assertNotIn("confirmed landing", text.casefold())

    def test_confirmed_zero_is_distinguished_from_unknown(self) -> None:
        """A measured zero remains numeric while estimates stay independent."""
        result = self.make_result()
        result["parking"]["confirmed_available_slots"] = 0
        result["parking"]["estimated_available_slots"] = 12

        text = self.render(result)

        self.assertIn("Confirmed availability: 0", text)
        self.assertIn("Estimated availability: 12", text)

    def test_no_result_is_presented_as_no_suitable_system(self) -> None:
        """An empty valid search has its own result text, not an error."""
        text = self.render(None)

        self.assertIn("No suitable parking system found within range.", text)
        self.assertNotIn("Search failed", text)

    def test_worker_schedules_result_and_updates_widgets_only_in_ui_callback(
        self,
    ) -> None:
        """The worker queues result rendering for the Tkinter event loop."""
        service = Mock()
        service.search.return_value = self.make_result()
        ui = self.make_ui(service)
        callbacks: list[tuple[int, Callable[[], None]]] = []
        scheduling_threads: list[int] = []
        update_threads: list[int] = []
        ui.frame.after.side_effect = capture_scheduled(callbacks, scheduling_threads)

        def record_update(_result: dict | None) -> None:
            update_threads.append(threading.get_ident())

        ui._update_result = Mock(side_effect=record_update)
        main_thread = threading.get_ident()

        worker = threading.Thread(target=ui._run_query, args=("Reference",))
        worker.start()
        worker.join(timeout=2)

        self.assertFalse(worker.is_alive())
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(callbacks[0][0], 0)
        self.assertNotEqual(scheduling_threads[0], main_thread)
        self.assertEqual(update_threads, [])

        callbacks[0][1]()

        self.assertEqual(update_threads, [main_thread])

    def test_error_types_are_localized_and_queued_for_ui_thread(self) -> None:
        """Timeout, API, and network errors have distinct scheduled messages."""
        cases = (
            (
                spansh_client.SpanshTimeoutError("timeout"),
                "Search failed: timeout while contacting Spansh.",
            ),
            (
                spansh_client.SpanshAPIError("api"),
                "Search failed: Spansh API error.",
            ),
            (
                spansh_client.SpanshError("network"),
                "Search failed: provider or network error.",
            ),
        )
        main_thread = threading.get_ident()

        for provider_error, expected_message in cases:
            with self.subTest(error=type(provider_error).__name__):
                service_error = ParkingServiceError("search failed")
                service_error.__cause__ = provider_error
                service = Mock()
                service.search.side_effect = service_error

                ui = self.make_ui(service)
                callbacks: list[tuple[int, Callable[[], None]]] = []
                scheduling_threads: list[int] = []
                update_threads: list[tuple[int, str]] = []
                ui.frame.after.side_effect = capture_scheduled(
                    callbacks, scheduling_threads
                )
                ui._update_error = Mock(
                    side_effect=capture_error_update(update_threads)
                )

                worker = threading.Thread(target=ui._run_query, args=("Reference",))
                with patch.object(parking_ui.logger, "exception"):
                    worker.start()
                    worker.join(timeout=2)

                self.assertFalse(worker.is_alive())
                self.assertEqual(len(callbacks), 1)
                self.assertNotEqual(scheduling_threads[0], main_thread)
                self.assertEqual(update_threads, [])

                callbacks[0][1]()

                self.assertEqual(update_threads, [(main_thread, expected_message)])

    def test_error_message_is_displayed_without_losing_log_guidance(self) -> None:
        """The selected error category reaches the label with standard guidance."""
        ui = self.make_ui()

        ui._update_error("Search failed: timeout while contacting Spansh.")

        ui.result_label.config.assert_called_once_with(
            text="Search failed: timeout while contacting Spansh.",
            foreground="red",
        )
        self.assertIn(
            "EDMC log",
            ui.result_tooltip.update_text.call_args.args[0],
        )


if __name__ == "__main__":
    unittest.main()
