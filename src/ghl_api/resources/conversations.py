from __future__ import annotations

from typing import Any

from ghl_api.resources._base import Resource


class Conversations(Resource):
    def search(
        self,
        *,
        location_id: str | None = None,
        contact_id: str | None = None,
        query: str | None = None,
        status: str | None = None,
        limit: int = 20,
        last_message_type: str | None = None,
        sort_by: str | None = None,
        sort: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "locationId": self._location(location_id),
            "limit": limit,
        }
        if contact_id:
            params["contactId"] = contact_id
        if query:
            params["query"] = query
        if status:
            params["status"] = status
        if last_message_type:
            params["lastMessageType"] = last_message_type
        if sort_by:
            params["sortBy"] = sort_by
        if sort:
            params["sort"] = sort
        return self._request("GET", "/conversations/search", params=params)

    def get(self, conversation_id: str) -> dict[str, Any]:
        return self._request("GET", f"/conversations/{conversation_id}")

    def messages(
        self,
        conversation_id: str,
        *,
        limit: int = 20,
        last_message_id: str | None = None,
        message_type: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if last_message_id:
            params["lastMessageId"] = last_message_id
        if message_type:
            params["type"] = message_type
        return self._request(
            "GET", f"/conversations/{conversation_id}/messages", params=params
        )

    def send_message(
        self,
        *,
        contact_id: str,
        message_type: str,
        message: str | None = None,
        html: str | None = None,
        subject: str | None = None,
        attachments: list[str] | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": message_type,
            "contactId": contact_id,
        }
        if message is not None:
            body["message"] = message
        if html is not None:
            body["html"] = html
        if subject is not None:
            body["subject"] = subject
        if attachments is not None:
            body["attachments"] = attachments
        body.update(extra)
        return self._request("POST", "/conversations/messages", json=body)

    def send_sms(self, *, contact_id: str, message: str, **extra: Any) -> dict[str, Any]:
        return self.send_message(
            contact_id=contact_id, message_type="SMS", message=message, **extra
        )

    def send_email(
        self,
        *,
        contact_id: str,
        subject: str,
        html: str | None = None,
        message: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        return self.send_message(
            contact_id=contact_id,
            message_type="Email",
            subject=subject,
            html=html,
            message=message,
            **extra,
        )
