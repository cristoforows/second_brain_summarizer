from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from langchain_core.tools import tool

from second_brain.services.calendar import CalendarService

log = structlog.get_logger()

_calendar: CalendarService | None = None
_calendar_id: str = "primary"


def init_calendar_tools(calendar: CalendarService, calendar_id: str) -> None:
    """Initialize the module with a CalendarService instance.

    Must be called before any tool is invoked.
    """
    global _calendar, _calendar_id
    _calendar = calendar
    _calendar_id = calendar_id


def _get_calendar() -> CalendarService:
    if _calendar is None:
        raise RuntimeError("Calendar tools not initialized — call init_calendar_tools() first")
    return _calendar


# ------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------


@tool
def get_upcoming_events(days_ahead: int = 30) -> str:
    """List upcoming calendar events to check for duplicates or find event IDs for updates.

    Call this before creating an event (to avoid duplicates) or before updating/deleting
    one (to find its event_id).

    Args:
        days_ahead: How many days ahead to look. Defaults to 30.

    Returns a formatted list of events with their IDs, titles, and start times.
    """
    cal = _get_calendar()
    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    events = cal.get_events(_calendar_id, time_min=time_min, time_max=time_max)
    if not events:
        return f"No upcoming events in the next {days_ahead} days."

    lines = []
    for e in events:
        start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date", "unknown")
        lines.append(f"- [{e['id']}] {e.get('summary', '(no title)')} — {start}")
    return "\n".join(lines)


@tool
def create_event(
    title: str,
    start_datetime: str,
    end_datetime: str,
    description: str = "",
    location: str = "",
) -> str:
    """Create a new Google Calendar event.

    Use this for time-bounded events: appointments, flights, meetings, reservations.
    Always call get_upcoming_events first to check for duplicates.

    Args:
        title: Event title.
        start_datetime: ISO 8601 datetime (e.g. "2026-04-10T15:00:00"). Assumed UTC.
        end_datetime: ISO 8601 datetime. Assumed UTC.
        description: Optional details about the event.
        location: Optional location or address.

    Returns the new event ID.
    """
    cal = _get_calendar()
    event_id = cal.create_event(
        _calendar_id,
        title=title,
        start=start_datetime,
        end=end_datetime,
        description=description,
        location=location,
    )
    return f"Created event '{title}' (ID: {event_id})."


@tool
def update_event(
    event_id: str,
    title: str = "",
    start_datetime: str = "",
    end_datetime: str = "",
    description: str = "",
    location: str = "",
) -> str:
    """Update an existing calendar event.

    Only the fields you provide will be changed. Use get_upcoming_events to find the event_id.

    Args:
        event_id: The ID of the event to update (from get_upcoming_events).
        title: New title (leave empty to keep existing).
        start_datetime: New start datetime ISO 8601 (leave empty to keep existing).
        end_datetime: New end datetime ISO 8601 (leave empty to keep existing).
        description: New description (leave empty to keep existing).
        location: New location (leave empty to keep existing).
    """
    cal = _get_calendar()
    cal.update_event(
        _calendar_id,
        event_id=event_id,
        title=title or None,
        start=start_datetime or None,
        end=end_datetime or None,
        description=description or None,
        location=location or None,
    )
    return f"Updated event {event_id}."


@tool
def delete_event(event_id: str) -> str:
    """Delete a calendar event.

    Use get_upcoming_events to find the event_id before calling this.

    Args:
        event_id: The ID of the event to delete.
    """
    cal = _get_calendar()
    cal.delete_event(_calendar_id, event_id)
    return f"Deleted event {event_id}."


def get_all_calendar_tools() -> list:
    """Return all calendar LangChain tools."""
    return [get_upcoming_events, create_event, update_event, delete_event]
