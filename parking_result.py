"""Shared result contract for the parking finder core, service, and UI.

``ParkingResult`` describes a selected system, not a confirmed reservation.
``parking.confirmed_available_slots`` is ``None`` when occupancy data is
unknown; a reported value of ``0`` means occupancy was measured and no slots
were confirmed available. Spansh carrier listings provide only a theoretical
occupancy estimate: ``estimated_available_slots`` is theoretical capacity
minus the number of carrier stations reported by Spansh. It does not confirm a
carrier-to-body location or reservation. ``provider_data_stale`` indicates
whether the system record is older than 24 hours; stale records are not used
alone to reject a system as full.
``parking.slots``, ``body_name_list``, and ``is_empirical`` remain as
compatibility fields for existing consumers.
"""

from __future__ import annotations

from typing import Literal, TypedDict

AccessStatus = Literal["allowed", "restricted", "unknown"]


class ParkingDetails(TypedDict):
    """Parking capacity and body information for one selected system."""

    theoretical_slots: int
    confirmed_available_slots: int | None
    spansh_reported_carrier_count: int | None
    estimated_available_slots: int | None
    body_assignment_complete: bool | None
    provider_data_stale: bool | None
    body_details: list[dict[str, object]]
    slots: int
    body_name_list: str | None
    is_empirical: bool


class ParkingResult(TypedDict):
    """Normalized result shared by the core, service, and UI.

    ``access_reason`` is a stable reason code when access is unknown or
    restricted, and ``None`` when the provider explicitly reports access.
    Currently selected results have ``allowed`` or ``unknown`` access status;
    restricted systems are excluded by the finder.
    """

    name: str
    distance: float
    access_status: AccessStatus
    access_reason: str | None
    parking: ParkingDetails
