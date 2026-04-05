from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from second_brain.services.auth import load_credentials

log = structlog.get_logger()


class CalendarService:
    """Google Calendar CRUD operations via shared OAuth2 credentials.

    Reuses the same token as DriveService — no separate auth flow needed.
    """

    def __init__(self, token_path: str) -> None:
        creds = load_credentials(token_path)
        self._service = build("calendar", "v3", credentials=creds)
        log.info("calendar_service_initialized", token_path=token_path)

    def create_event(
        self,
        calendar_id: str,
        title: str,
        start: str,
        end: str,
        description: str = "",
        location: str = "",
    ) -> str:
        """Create a calendar event. Returns the new event ID.

        Args:
            calendar_id: Calendar to write to (e.g. "primary").
            title: Event title.
            start: ISO 8601 datetime string (e.g. "2026-04-10T15:00:00").
            end: ISO 8601 datetime string.
            description: Optional event description.
            location: Optional event location.
        """
        body: dict[str, Any] = {
            "summary": title,
            "start": {"dateTime": start, "timeZone": "UTC"},
            "end": {"dateTime": end, "timeZone": "UTC"},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location

        try:
            event = (
                self._service.events()
                .insert(calendarId=calendar_id, body=body)
                .execute()
            )
        except HttpError as e:
            log.error("calendar_create_event_failed", title=title, status=e.status_code, error=str(e))
            raise

        event_id = event["id"]
        log.info("calendar_event_created", title=title, event_id=event_id)
        return event_id

    def get_events(
        self,
        calendar_id: str,
        time_min: str | None = None,
        time_max: str | None = None,
    ) -> list[dict[str, Any]]:
        """List events in a time range.

        Args:
            calendar_id: Calendar to query.
            time_min: ISO 8601 lower bound (inclusive). Defaults to now.
            time_max: ISO 8601 upper bound (exclusive).
        """
        if time_min is None:
            time_min = datetime.now(timezone.utc).isoformat()

        kwargs: dict[str, Any] = {
            "calendarId": calendar_id,
            "timeMin": time_min,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if time_max:
            kwargs["timeMax"] = time_max

        try:
            resp = self._service.events().list(**kwargs).execute()
        except HttpError as e:
            log.error("calendar_get_events_failed", calendar_id=calendar_id, status=e.status_code, error=str(e))
            raise

        return resp.get("items", [])

    def update_event(
        self,
        calendar_id: str,
        event_id: str,
        title: str | None = None,
        start: str | None = None,
        end: str | None = None,
        description: str | None = None,
        location: str | None = None,
    ) -> None:
        """Patch an existing event with only the provided fields."""
        patch: dict[str, Any] = {}
        if title is not None:
            patch["summary"] = title
        if start is not None:
            patch["start"] = {"dateTime": start, "timeZone": "UTC"}
        if end is not None:
            patch["end"] = {"dateTime": end, "timeZone": "UTC"}
        if description is not None:
            patch["description"] = description
        if location is not None:
            patch["location"] = location

        if not patch:
            return

        try:
            self._service.events().patch(
                calendarId=calendar_id, eventId=event_id, body=patch
            ).execute()
        except HttpError as e:
            log.error("calendar_update_event_failed", event_id=event_id, status=e.status_code, error=str(e))
            raise

        log.info("calendar_event_updated", event_id=event_id, fields=list(patch.keys()))

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        """Delete a calendar event."""
        try:
            self._service.events().delete(
                calendarId=calendar_id, eventId=event_id
            ).execute()
        except HttpError as e:
            log.error("calendar_delete_event_failed", event_id=event_id, status=e.status_code, error=str(e))
            raise

        log.info("calendar_event_deleted", event_id=event_id)
