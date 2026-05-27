"""Sanity tests for the new mappers — opportunity, pipeline, user, appointment.

These verify column shape + key field plumbing. They don't exercise every
permutation (sanitize tests already cover the value-cleaning paths).
"""
from __future__ import annotations

from ghl_api.mappers import (
    APPOINTMENT_COLUMNS,
    OPPORTUNITY_COLUMNS,
    PIPELINE_COLUMNS,
    PIPELINE_STAGE_COLUMNS,
    USER_COLUMNS,
    map_appointment,
    map_opportunity,
    map_pipeline,
    map_pipeline_stage,
    map_user,
)


def _has_audit_cols(row: dict, sysid_field: str) -> None:
    assert row["SourceSystem"] == "GoHighLevel"
    assert row["SourceSystemId"] == row[sysid_field]
    assert row["ExtractedAtUtc"] == "2026-01-01T00:00:00.000Z"


def test_map_opportunity_minimal():
    o = {"id": "opp123", "locationId": "loc1", "pipelineId": "pl1",
         "pipelineStageId": "ps1", "contactId": "c1", "monetaryValue": "1500",
         "status": "open", "name": "Test deal"}
    row = map_opportunity(o, extracted_at="2026-01-01T00:00:00.000Z")
    assert set(row.keys()) == set(OPPORTUNITY_COLUMNS)
    assert row["OpportunityId"] == "opp123"
    assert row["PipelineStageId"] == "ps1"
    assert row["Status"] == "open"
    assert row["MonetaryValue"] == "1500"
    _has_audit_cols(row, "OpportunityId")


def test_map_opportunity_handles_alt_field_names():
    """API sometimes returns createdAt/updatedAt/stageId — mapper accepts both."""
    o = {"id": "opp1", "locationId": "loc1", "stageId": "ps2",
         "createdAt": "2025-06-01T12:00:00Z", "updatedAt": "2025-06-02T13:00:00Z"}
    row = map_opportunity(o, extracted_at="2026-01-01T00:00:00.000Z")
    assert row["PipelineStageId"] == "ps2"
    assert row["DateAddedUtc"] == "2025-06-01T12:00:00.000Z"
    assert row["DateUpdatedUtc"] == "2025-06-02T13:00:00.000Z"


def test_map_pipeline_columns():
    p = {"id": "pl1", "locationId": "loc1", "name": "Sales pipeline"}
    row = map_pipeline(p, extracted_at="2026-01-01T00:00:00.000Z")
    assert set(row.keys()) == set(PIPELINE_COLUMNS)
    assert row["PipelineId"] == "pl1"
    assert row["Name"] == "Sales pipeline"


def test_map_pipeline_stage_inherits_pipeline_id():
    s = {"id": "ps1", "name": "Qualified", "position": 2}
    row = map_pipeline_stage(s, pipeline_id="pl1", location_id="loc1",
                             extracted_at="2026-01-01T00:00:00.000Z")
    assert set(row.keys()) == set(PIPELINE_STAGE_COLUMNS)
    assert row["PipelineId"] == "pl1"
    assert row["LocationId"] == "loc1"
    assert row["Position"] == "2"


def test_map_user_full_name_fallback():
    u = {"id": "u1", "firstName": "Alice", "lastName": "Smith",
         "email": "ALICE@example.com", "deleted": False}
    row = map_user(u, extracted_at="2026-01-01T00:00:00.000Z")
    assert set(row.keys()) == set(USER_COLUMNS)
    assert row["FullName"] == "Alice Smith"
    assert row["Email"] == "alice@example.com"
    assert row["IsActive"] == "1"


def test_map_user_inactive_when_deleted():
    u = {"id": "u2", "firstName": "Bob", "deleted": True}
    row = map_user(u, extracted_at="2026-01-01T00:00:00.000Z")
    assert row["IsActive"] == "0"


def test_map_appointment_extracts_assigned_from_users_array():
    a = {"id": "appt1", "locationId": "loc1", "calendarId": "cal1",
         "contactId": "c1", "users": ["u-agent-1", "u-helper-2"],
         "appointmentStatus": "showed", "title": "Listing meeting",
         "startTime": "2026-05-01T15:00:00Z", "endTime": "2026-05-01T16:00:00Z"}
    row = map_appointment(a, extracted_at="2026-01-01T00:00:00.000Z")
    assert set(row.keys()) == set(APPOINTMENT_COLUMNS)
    assert row["AssignedToUserId"] == "u-agent-1"  # first in array
    assert row["AppointmentStatus"] == "showed"
    assert row["StartTimeUtc"] == "2026-05-01T15:00:00.000Z"


def test_map_appointment_handles_dict_user_entries():
    a = {"id": "appt2", "locationId": "loc1", "calendarId": "cal1",
         "users": [{"id": "u-agent-A"}], "title": "x"}
    row = map_appointment(a, extracted_at="2026-01-01T00:00:00.000Z")
    assert row["AssignedToUserId"] == "u-agent-A"


def test_no_embedded_newlines_in_any_mapped_row():
    """Defense-in-depth: every value emitted must be SQL-Server safe."""
    o = {"id": "opp", "name": "Hello\nworld\twith\rstuff"}
    row = map_opportunity(o, extracted_at="2026-01-01T00:00:00.000Z")
    for v in row.values():
        assert "\n" not in v and "\r" not in v and "\t" not in v
