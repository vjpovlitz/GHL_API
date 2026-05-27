"""BatchExtractor framework: paginate -> shard -> checkpoint -> resume.

Design:
- Each entity has a subclass that implements `fetch_page(cursor)` and `map_row()`.
- Rows are sanitized via mappers BEFORE write (so the audit gate can't catch
  embedded newlines — they're already gone).
- Output is sharded: one CSV per `shard_size` rows, named `<Entity>_part_NNN.csv`.
- After every page write, the checkpoint JSON is rewritten atomically.
- On resume, the extractor picks up from the saved cursor and continues writing
  into the current shard (or rolls to the next one if it's already full).

CSV format (DATA_RULES §5):
- UTF-8 with BOM
- CRLF line terminator
- csv.QUOTE_MINIMAL
- One file per shard

The checkpoint is the source of truth for resumability. If it disagrees with
what's on disk (e.g. a partial shard from a crash), the extractor rolls
forward — it does NOT try to truncate. The audit gate catches truncation
issues; this code stays simple.
"""
from __future__ import annotations

import csv
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ghl_api.client import GHLClient
from ghl_api.mappers import (
    APPOINTMENT_COLUMNS,
    CONTACT_COLUMNS,
    CONVERSATION_COLUMNS,
    MESSAGE_COLUMNS,
    OPPORTUNITY_COLUMNS,
    map_appointment,
    map_contact,
    map_conversation,
    map_message,
    map_opportunity,
)

DEFAULT_SHARD_SIZE = 5_000


def _now_utc_iso() -> str:
    n = datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"


@dataclass
class Checkpoint:
    """Persistent extractor state. Rewritten after every page."""

    entity: str
    extracted_at_utc: str
    cursor: Any | None = None
    shard_index: int = 1
    rows_in_current_shard: int = 0
    rows_total: int = 0
    pages_fetched: int = 0
    finished: bool = False
    shard_files: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> Checkpoint | None:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            entity=data["entity"],
            extracted_at_utc=data["extracted_at_utc"],
            cursor=data.get("cursor"),
            shard_index=int(data.get("shard_index", 1)),
            rows_in_current_shard=int(data.get("rows_in_current_shard", 0)),
            rows_total=int(data.get("rows_total", 0)),
            pages_fetched=int(data.get("pages_fetched", 0)),
            finished=bool(data.get("finished", False)),
            shard_files=list(data.get("shard_files", [])),
        )

    def save(self, path: Path) -> None:
        payload = {
            "entity": self.entity,
            "extracted_at_utc": self.extracted_at_utc,
            "cursor": self.cursor,
            "shard_index": self.shard_index,
            "rows_in_current_shard": self.rows_in_current_shard,
            "rows_total": self.rows_total,
            "pages_fetched": self.pages_fetched,
            "finished": self.finished,
            "shard_files": self.shard_files,
            "updated_at_utc": _now_utc_iso(),
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, path)


class BatchExtractor(ABC):
    """Subclass to wire up a specific entity. See ContactsExtractor below."""

    entity: str = "Entity"
    columns: list[str] = []

    def __init__(
        self,
        client: GHLClient,
        *,
        output_dir: Path,
        shard_size: int = DEFAULT_SHARD_SIZE,
        page_limit: int = 100,
    ):
        self.client = client
        self.output_dir = output_dir
        self.shard_size = shard_size
        self.page_limit = page_limit
        self.checkpoint_path = output_dir / f"{self.entity}.checkpoint.json"

    @abstractmethod
    def fetch_page(self, cursor: Any | None) -> tuple[list[dict], Any | None]:
        """Return (api_rows, next_cursor). next_cursor=None means done."""

    @abstractmethod
    def map_row(self, api_row: dict, *, extracted_at: str) -> dict:
        """Map and sanitize one API row to a CSV row dict."""

    # ---- framework ----

    def run(self, *, max_rows: int | None = None, resume: bool = True) -> Checkpoint:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        cp = Checkpoint.load(self.checkpoint_path) if resume else None
        if cp is None:
            cp = Checkpoint(entity=self.entity, extracted_at_utc=_now_utc_iso())

        if cp.finished:
            print(f"[{self.entity}] checkpoint says finished — nothing to do "
                  f"({cp.rows_total:,} rows across {len(cp.shard_files)} shards).")
            return cp

        print(f"[{self.entity}] starting (resume={resume}, "
              f"rows_total={cp.rows_total:,}, shard={cp.shard_index}, "
              f"in_shard={cp.rows_in_current_shard}).")

        try:
            while True:
                if max_rows is not None and cp.rows_total >= max_rows:
                    break

                api_rows, next_cursor = self.fetch_page(cp.cursor)
                cp.pages_fetched += 1

                if not api_rows:
                    cp.finished = next_cursor is None
                    cp.cursor = next_cursor
                    cp.save(self.checkpoint_path)
                    break

                # Cap to max_rows if asked
                if max_rows is not None:
                    remaining = max_rows - cp.rows_total
                    if remaining <= 0:
                        break
                    if len(api_rows) > remaining:
                        api_rows = api_rows[:remaining]

                rows = [self.map_row(r, extracted_at=cp.extracted_at_utc) for r in api_rows]
                self._write_rows(rows, cp)

                cp.cursor = next_cursor
                if next_cursor is None:
                    cp.finished = True
                cp.save(self.checkpoint_path)

                print(f"[{self.entity}] page={cp.pages_fetched:>4} "
                      f"+{len(rows):>4} rows  total={cp.rows_total:>7,}  "
                      f"shard={cp.shard_index:>3}  "
                      f"burst_rem={self.client.throttle.burst_remaining}")

                if cp.finished:
                    break
        finally:
            cp.save(self.checkpoint_path)

        return cp

    def _write_rows(self, rows: Iterable[dict], cp: Checkpoint) -> None:
        """Append rows into the current shard, rolling when it fills."""
        pending = list(rows)
        i = 0
        while i < len(pending):
            room = self.shard_size - cp.rows_in_current_shard
            batch = pending[i:i + room]
            shard_path = self._shard_path(cp.shard_index)
            self._append_csv(shard_path, batch)
            if shard_path.name not in cp.shard_files:
                cp.shard_files.append(shard_path.name)

            cp.rows_in_current_shard += len(batch)
            cp.rows_total += len(batch)
            i += len(batch)

            if cp.rows_in_current_shard >= self.shard_size:
                cp.shard_index += 1
                cp.rows_in_current_shard = 0

    def _shard_path(self, index: int) -> Path:
        return self.output_dir / f"{self.entity}_part_{index:03d}.csv"

    def _append_csv(self, path: Path, rows: list[dict]) -> None:
        # utf-8-sig in "a" mode would write the BOM at end-of-file (mid-file).
        # Write BOM manually for new files, then use plain utf-8 thereafter.
        new_file = not path.exists()
        if new_file:
            path.write_bytes(b"\xef\xbb\xbf")
        with path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=self.columns,
                lineterminator="\r\n",
                quoting=csv.QUOTE_MINIMAL,
                extrasaction="ignore",
            )
            if new_file:
                writer.writeheader()
            for row in rows:
                writer.writerow({c: row.get(c, "") for c in self.columns})


# ---------- Per-entity extractors ----------

class ContactsExtractor(BatchExtractor):
    entity = "Contacts"
    columns = CONTACT_COLUMNS

    def fetch_page(self, cursor):
        # GET /contacts/ uses startAfter (epoch ms) + startAfterId pair.
        # We pass them through as a 2-tuple cursor: (start_after, start_after_id).
        start_after, start_after_id = (cursor or (None, None))
        resp = self.client.contacts.list(
            limit=min(self.page_limit, 100),  # GET caps at 100
            start_after=start_after,
            start_after_id=start_after_id,
        )
        rows = resp.get("contacts") or []
        meta = resp.get("meta") or {}
        next_cursor: tuple[str, str] | None
        nsa = meta.get("startAfter")
        nsi = meta.get("startAfterId")
        if rows and (nsa or nsi):
            next_cursor = (nsa, nsi)
        else:
            next_cursor = None
        return rows, next_cursor

    def map_row(self, api_row, *, extracted_at):
        return map_contact(api_row, extracted_at=extracted_at)


class ConversationsExtractor(BatchExtractor):
    entity = "Conversations"
    columns = CONVERSATION_COLUMNS

    def fetch_page(self, cursor):
        # /conversations/search returns lastMessageDate as epoch ms.
        # Sort by lastMessageDate asc, paginate with startAfterDate cursor.
        # We pass (startAfterDate, startAfterId) as the cursor.
        start_after_date, start_after_id = (cursor or (None, None))
        params = {
            "locationId": self.client.require_location_id(),
            "limit": min(self.page_limit, 100),
            "sortBy": "last_message_date",
            "sort": "asc",
        }
        if start_after_date:
            params["startAfterDate"] = start_after_date
        if start_after_id:
            params["startAfterId"] = start_after_id
        resp = self.client.request("GET", "/conversations/search", params=params)
        rows = resp.get("conversations") or []
        if not rows:
            return [], None
        last = rows[-1]
        next_date = last.get("lastMessageDate")
        next_id = last.get("id")
        # If we got fewer than page_limit rows, we're at the end.
        if len(rows) < params["limit"]:
            next_cursor = None
        elif next_date or next_id:
            next_cursor = (next_date, next_id)
        else:
            next_cursor = None
        return rows, next_cursor

    def map_row(self, api_row, *, extracted_at):
        return map_conversation(api_row, extracted_at=extracted_at)


class MessagesExtractor(BatchExtractor):
    """Fetches messages for a list of conversation IDs.

    Unlike the other extractors, the 'cursor' here is an index into the
    conversation-list driver — we iterate conversations, and for each one
    pull all messages. The driver list is loaded once at construction time
    and persisted into the checkpoint via the cursor.
    """

    entity = "ConversationMessages"
    columns = MESSAGE_COLUMNS

    def __init__(self, client, *, conversations: list[dict], **kwargs):
        super().__init__(client, **kwargs)
        # Each entry: {"id": "...", "contactId": "...", "locationId": "..."}.
        self.conversations = conversations

    def fetch_page(self, cursor):
        # cursor = next conversation index (int)
        idx = int(cursor or 0)
        if idx >= len(self.conversations):
            return [], None
        conv = self.conversations[idx]
        cid = conv.get("id")
        if not cid:
            return [], idx + 1

        all_msgs: list[dict] = []
        last_msg_id: str | None = None
        # Pull every page of messages for this conversation.
        while True:
            resp = self.client.conversations.messages(
                cid, limit=100, last_message_id=last_msg_id
            )
            inner = resp.get("messages")
            msgs = inner.get("messages") if isinstance(inner, dict) else inner
            msgs = msgs or []
            if not msgs:
                break
            all_msgs.extend(
                {
                    **m,
                    "_driver_conversation_id": cid,
                    "_driver_contact_id": conv.get("contactId", ""),
                    "_driver_location_id": conv.get("locationId", ""),
                }
                for m in msgs
            )
            next_id = (inner.get("nextPage") if isinstance(inner, dict) else None) or msgs[-1].get("id")
            has_more = bool(inner.get("nextPage")) if isinstance(inner, dict) else (len(msgs) >= 100)
            if not has_more or not next_id or next_id == last_msg_id:
                break
            last_msg_id = next_id

        next_cursor = idx + 1
        if next_cursor >= len(self.conversations):
            next_cursor = None
        return all_msgs, next_cursor

    def map_row(self, api_row, *, extracted_at):
        return map_message(
            api_row,
            conversation_id=api_row.get("_driver_conversation_id", ""),
            contact_id=api_row.get("_driver_contact_id", ""),
            location_id=api_row.get("_driver_location_id", ""),
            extracted_at=extracted_at,
        )


class OpportunitiesExtractor(BatchExtractor):
    entity = "Opportunities"
    columns = OPPORTUNITY_COLUMNS

    def fetch_page(self, cursor):
        # /opportunities/search uses startAfter (epoch ms of updatedAt) + startAfterId
        start_after, start_after_id = (cursor or (None, None))
        resp = self.client.opportunities.search(
            limit=min(self.page_limit, 100),
            start_after=start_after,
            start_after_id=start_after_id,
        )
        rows = resp.get("opportunities") or []
        meta = resp.get("meta") or {}
        nsa = meta.get("startAfter")
        nsi = meta.get("startAfterId")
        next_cursor: tuple | None
        if rows and (nsa or nsi) and len(rows) >= min(self.page_limit, 100):
            next_cursor = (nsa, nsi)
        else:
            next_cursor = None
        return rows, next_cursor

    def map_row(self, api_row, *, extracted_at):
        return map_opportunity(api_row, extracted_at=extracted_at)


class AppointmentsExtractor(BatchExtractor):
    """Pulls appointment events across one or more calendars in a date window.

    Driver list: calendar_ids — each one queried for events in [start_ms, end_ms].
    Cursor = next calendar index. Each calendar yields a flat events list.
    """

    entity = "Appointments"
    columns = APPOINTMENT_COLUMNS

    def __init__(
        self,
        client,
        *,
        calendar_ids: list[str],
        start_ms: int,
        end_ms: int,
        **kwargs,
    ):
        super().__init__(client, **kwargs)
        self.calendar_ids = calendar_ids
        self.start_ms = start_ms
        self.end_ms = end_ms

    def fetch_page(self, cursor):
        idx = int(cursor or 0)
        if idx >= len(self.calendar_ids):
            return [], None
        cal_id = self.calendar_ids[idx]
        try:
            resp = self.client.calendars.events(
                start_time=self.start_ms,
                end_time=self.end_ms,
                calendar_id=cal_id,
            )
        except Exception as e:
            print(f"[Appointments] WARN cal={cal_id}: {e}")
            return [], idx + 1
        rows = resp.get("events") or []
        next_cursor = idx + 1 if idx + 1 < len(self.calendar_ids) else None
        return rows, next_cursor

    def map_row(self, api_row, *, extracted_at):
        return map_appointment(api_row, extracted_at=extracted_at)
