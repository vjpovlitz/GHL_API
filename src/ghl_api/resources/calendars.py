from __future__ import annotations

from typing import Any

from ghl_api.resources._base import Resource


class Calendars(Resource):
    def list(
        self,
        *,
        location_id: str | None = None,
        group_id: str | None = None,
        show_drafted: bool | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"locationId": self._location(location_id)}
        if group_id:
            params["groupId"] = group_id
        if show_drafted is not None:
            params["showDrafted"] = str(show_drafted).lower()
        return self._request("GET", "/calendars/", params=params)

    def get(self, calendar_id: str) -> dict[str, Any]:
        return self._request("GET", f"/calendars/{calendar_id}")

    def free_slots(
        self,
        calendar_id: str,
        *,
        start_date: int,
        end_date: int,
        timezone: str | None = None,
        user_id: str | None = None,
        user_ids: list[str] | None = None,
        enable_look_busy: bool | None = None,
    ) -> dict[str, Any]:
        """Free slots between start_date and end_date.

        start_date / end_date are epoch milliseconds (GHL convention).
        """
        params: dict[str, Any] = {"startDate": start_date, "endDate": end_date}
        if timezone:
            params["timezone"] = timezone
        if user_id:
            params["userId"] = user_id
        if user_ids:
            params["userIds"] = user_ids
        if enable_look_busy is not None:
            params["enableLookBusy"] = str(enable_look_busy).lower()
        return self._request("GET", f"/calendars/{calendar_id}/free-slots", params=params)

    def events(
        self,
        *,
        location_id: str | None = None,
        start_time: int,
        end_time: int,
        calendar_id: str | None = None,
        user_id: str | None = None,
        group_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "locationId": self._location(location_id),
            "startTime": start_time,
            "endTime": end_time,
        }
        if calendar_id:
            params["calendarId"] = calendar_id
        if user_id:
            params["userId"] = user_id
        if group_id:
            params["groupId"] = group_id
        return self._request("GET", "/calendars/events", params=params)

    def get_appointment(self, event_id: str) -> dict[str, Any]:
        return self._request("GET", f"/calendars/events/appointments/{event_id}")

    def create_appointment(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "locationId" not in payload:
            payload = {"locationId": self._location(None), **payload}
        return self._request("POST", "/calendars/events/appointments", json=payload)

    def update_appointment(self, event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "PUT", f"/calendars/events/appointments/{event_id}", json=payload
        )

    def delete_event(self, event_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/calendars/events/{event_id}")
