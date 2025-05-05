import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

# Adjust the import path based on your project structure
from zoltar_backend.main import app # Import your FastAPI app instance
from zoltar_backend import schemas, models, auth # Import relevant schemas, models, and auth module

# Create a TestClient instance
client = TestClient(app)

# --- Test Data & Mocks ---

# Mock User Data
MOCK_USER_LINKED = models.User(
    id=1,
    email="linked@example.com",
    ms_oid="mock_ms_oid_123", # Linked account
    is_active=True,
    created_at=datetime.now(timezone.utc)
)

MOCK_USER_NOT_LINKED = models.User(
    id=2,
    email="notlinked@example.com",
    ms_oid=None, # Not linked
    is_active=True,
    created_at=datetime.now(timezone.utc)
)

# Mock Calendar Event Data (as returned by MS Graph API helper)
MOCK_RAW_EVENT_1 = {
    "id": "event1",
    "subject": "Test Event 1",
    "bodyPreview": "Preview 1",
    "start": {"dateTime": "2024-07-30T10:00:00Z", "timeZone": "UTC"},
    "end": {"dateTime": "2024-07-30T11:00:00Z", "timeZone": "UTC"}
}
MOCK_RAW_EVENT_2 = {
    "id": "event2",
    "subject": "Test Event 2",
    "bodyPreview": "Preview 2",
    "start": {"dateTime": "2024-07-30T14:00:00Z", "timeZone": "UTC"},
    "end": {"dateTime": "2024-07-30T14:30:00Z", "timeZone": "UTC"}
}
MOCK_RAW_EVENTS_LIST = [MOCK_RAW_EVENT_1, MOCK_RAW_EVENT_2]

# Helper to override the dependency
def override_get_current_active_user():
    # This function will be replaced by the actual user in tests
    # Using a simple callable that can be easily patched per test
    pass

# Apply the dependency override globally for tests in this module
app.dependency_overrides[auth.get_current_active_user] = override_get_current_active_user

# --- Test Cases ---

@pytest.mark.parametrize("test_user, expected_status, mock_events, expected_response_length", [
    (MOCK_USER_LINKED, 200, MOCK_RAW_EVENTS_LIST, 2), # Success
    (MOCK_USER_LINKED, 200, [], 0),                 # Success - Empty list
    (MOCK_USER_NOT_LINKED, 400, None, None),         # Error - Account not linked
    (MOCK_USER_LINKED, 503, None, None),             # Error - Graph API failure
])
@patch("zoltar_backend.auth_utils_ms.get_outlook_calendar_events")
def test_read_calendar_agenda(
    mock_get_events: MagicMock,
    test_user: models.User,
    expected_status: int,
    mock_events: Optional[List[Dict[str, Any]]],
    expected_response_length: Optional[int],
):
    """Tests the GET /calendar/agenda endpoint with various scenarios."""
    # Configure the mock return value for get_outlook_calendar_events
    mock_get_events.return_value = mock_events

    # Override the user dependency for this specific test run
    app.dependency_overrides[auth.get_current_active_user] = lambda: test_user

    start_time_str = "2024-07-30T00:00:00Z"
    end_time_str = "2024-07-31T00:00:00Z"

    response = client.get(
        f"/calendar/agenda?start_time={start_time_str}&end_time={end_time_str}"
        # Authentication is handled by overriding the dependency
    )

    assert response.status_code == expected_status

    if expected_status == 200:
        assert isinstance(response.json(), list)
        assert len(response.json()) == expected_response_length
        if expected_response_length > 0:
            # Check structure of the first event
            event = response.json()[0]
            assert "id" in event
            assert "subject" in event
            assert "body_preview" in event
            assert "start_datetime" in event
            assert "end_datetime" in event
            # Optionally, check specific values if needed based on MOCK_RAW_EVENTS_LIST
            assert event["id"] == MOCK_RAW_EVENT_1["id"]
            assert event["start_datetime"] == MOCK_RAW_EVENT_1["start"]["dateTime"]
    elif expected_status == 400:
        assert "Microsoft account not linked" in response.json()["detail"]
    elif expected_status == 503:
        assert "Could not retrieve calendar events" in response.json()["detail"]

    # Clean up dependency override after test
    app.dependency_overrides = {}

def test_read_calendar_agenda_unauthenticated():
    """Tests GET /calendar/agenda without authentication (no override)."""
    # Ensure overrides are clear if previous test failed
    app.dependency_overrides = {}

    start_time_str = "2024-07-30T00:00:00Z"
    end_time_str = "2024-07-31T00:00:00Z"

    response = client.get(
        f"/calendar/agenda?start_time={start_time_str}&end_time={end_time_str}"
    )

    # FastAPI's dependency injection should handle this via the router dependency
    assert response.status_code == 401

# TODO: Add tests for invalid datetime query parameters (should result in 422)
# Example:
# def test_read_calendar_agenda_invalid_datetime():
#     app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER_LINKED
#     response = client.get("/calendar/agenda?start_time=invalid-date&end_time=invalid-date")
#     assert response.status_code == 422
#     app.dependency_overrides = {} 

app.dependency_overrides = {}


# --- Tests for POST /calendar/events ---

# Mock successful Graph API response for event creation
MOCK_GRAPH_CREATE_RESPONSE = {
    "id": "new_event_123",
    "subject": "Created Event",
    "bodyPreview": "Created Body",
    "start": {"dateTime": "2024-08-01T10:00:00Z", "timeZone": "UTC"},
    "end": {"dateTime": "2024-08-01T11:00:00Z", "timeZone": "UTC"}
}

# Mock bad Graph API responses
MOCK_GRAPH_CREATE_RESPONSE_NO_ID = {
    # Missing 'id'
    "subject": "Created Event",
    "bodyPreview": "Created Body",
    "start": {"dateTime": "2024-08-01T10:00:00Z", "timeZone": "UTC"},
    "end": {"dateTime": "2024-08-01T11:00:00Z", "timeZone": "UTC"}
}
MOCK_GRAPH_CREATE_RESPONSE_BAD_DATE = {
    "id": "bad_date_event",
    "subject": "Created Event",
    "bodyPreview": "Created Body",
    "start": {"dateTime": "INVALID-DATE-STRING", "timeZone": "UTC"},
    "end": {"dateTime": "2024-08-01T11:00:00Z", "timeZone": "UTC"}
}

# Valid request payload
VALID_EVENT_PAYLOAD = {
    "subject": "Test Create Event",
    "start_datetime": "2024-08-01T09:00:00+00:00", # TZ aware
    "end_datetime": "2024-08-01T10:00:00+00:00",   # TZ aware
    "body_content": "Event details here",
    "body_content_type": "Text"
}

# Invalid request payloads
INVALID_EVENT_PAYLOAD_NAIVE_DT = {
    "subject": "Naive DT Event",
    "start_datetime": "2024-08-01T09:00:00", # Not TZ aware
    "end_datetime": "2024-08-01T10:00:00+00:00"
}
INVALID_EVENT_PAYLOAD_END_BEFORE_START = {
    "subject": "End Before Start",
    "start_datetime": "2024-08-01T10:00:00+00:00",
    "end_datetime": "2024-08-01T09:00:00+00:00" # End is before start
}


@pytest.mark.parametrize("test_user, request_payload, mock_graph_response, expected_status, expected_detail_contains", [
    # Success Case
    (MOCK_USER_LINKED, VALID_EVENT_PAYLOAD, MOCK_GRAPH_CREATE_RESPONSE, 201, None),
    # Error: User not linked
    (MOCK_USER_NOT_LINKED, VALID_EVENT_PAYLOAD, None, 400, "Microsoft account not linked"),
    # Error: Graph API call fails (returns None)
    (MOCK_USER_LINKED, VALID_EVENT_PAYLOAD, None, 503, "Could not create calendar event"),
    # Error: Graph API response missing ID
    (MOCK_USER_LINKED, VALID_EVENT_PAYLOAD, MOCK_GRAPH_CREATE_RESPONSE_NO_ID, 502, "unexpected response format"),
    # Error: Graph API response has bad date (causes Pydantic error)
    (MOCK_USER_LINKED, VALID_EVENT_PAYLOAD, MOCK_GRAPH_CREATE_RESPONSE_BAD_DATE, 500, "Failed to process response"),
])
@patch("zoltar_backend.auth_utils_ms.call_microsoft_graph_api")
def test_create_calendar_event(
    mock_call_graph: MagicMock,
    test_user: models.User,
    request_payload: Dict[str, Any],
    mock_graph_response: Optional[Dict[str, Any]],
    expected_status: int,
    expected_detail_contains: Optional[str]
):
    """Tests POST /calendar/events for various success and error scenarios."""
    # Configure the mock for call_microsoft_graph_api
    mock_call_graph.return_value = mock_graph_response

    # Override the user dependency
    app.dependency_overrides[auth.get_current_active_user] = lambda: test_user

    response = client.post("/calendar/events", json=request_payload)

    assert response.status_code == expected_status

    if expected_detail_contains:
        assert expected_detail_contains.lower() in response.json()["detail"].lower()
    
    if expected_status == 201:
        # Check if Graph API was called correctly
        mock_call_graph.assert_called_once()
        call_args, call_kwargs = mock_call_graph.call_args
        assert call_kwargs["method"] == "POST"
        assert call_kwargs["endpoint"] == "/me/events"
        assert call_kwargs["ms_oid"] == test_user.ms_oid
        assert "Calendars.ReadWrite" in call_kwargs["scopes"]
        # Check response structure matches CalendarEvent schema
        response_data = response.json()
        assert response_data["id"] == MOCK_GRAPH_CREATE_RESPONSE["id"]
        assert response_data["subject"] == MOCK_GRAPH_CREATE_RESPONSE["subject"]
        assert response_data["start_datetime"] == MOCK_GRAPH_CREATE_RESPONSE["start"]["dateTime"]

    # Clean up override
    app.dependency_overrides = {}

def test_create_calendar_event_unauthenticated():
    """Tests POST /calendar/events without authentication."""
    app.dependency_overrides = {}
    response = client.post("/calendar/events", json=VALID_EVENT_PAYLOAD)
    assert response.status_code == 401

@pytest.mark.parametrize("payload, expected_detail_part", [
    (INVALID_EVENT_PAYLOAD_NAIVE_DT, "datetime must be timezone-aware"),
    (INVALID_EVENT_PAYLOAD_END_BEFORE_START, "end_datetime must be after start_datetime"),
    ({"subject": "Missing times"}, "Field required"), # Test missing required fields
])
def test_create_calendar_event_invalid_payload(payload: Dict, expected_detail_part: str):
    """Tests POST /calendar/events with invalid request bodies (422)."""
    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER_LINKED
    
    response = client.post("/calendar/events", json=payload)
    
    assert response.status_code == 422
    # Check if the expected validation error message is present
    assert any(expected_detail_part in error["msg"] for error in response.json()["detail"])

    app.dependency_overrides = {}



# # TODO: Add tests for invalid datetime query parameters (should result in 422)
# Example:

# Clean up dependency override after test
app.dependency_overrides = {} 

# --- Tests for PATCH /calendar/events/{event_id} ---

# Mock successful Graph API response for event update
MOCK_GRAPH_UPDATE_RESPONSE = {
    "id": "event_to_update_123",
    "subject": "Updated Event Subject",
    "bodyPreview": "Updated Body",
    "start": {"dateTime": "2024-08-02T11:00:00Z", "timeZone": "UTC"},
    "end": {"dateTime": "2024-08-02T12:00:00Z", "timeZone": "UTC"}
}

# Mock bad Graph API responses for update
MOCK_GRAPH_UPDATE_RESPONSE_NO_ID = {
    "subject": "Updated Event Subject",
    "bodyPreview": "Updated Body",
    "start": {"dateTime": "2024-08-02T11:00:00Z", "timeZone": "UTC"},
    "end": {"dateTime": "2024-08-02T12:00:00Z", "timeZone": "UTC"}
}
MOCK_GRAPH_UPDATE_RESPONSE_BAD_DATE = {
    "id": "event_to_update_123",
    "subject": "Updated Event Subject",
    "bodyPreview": "Updated Body",
    "start": {"dateTime": "NOT-A-DATE", "timeZone": "UTC"},
    "end": {"dateTime": "2024-08-02T12:00:00Z", "timeZone": "UTC"}
}

# Valid PATCH payload
VALID_UPDATE_PAYLOAD = {
    "subject": "Updated Event Subject",
    "start_datetime": "2024-08-02T11:00:00Z" # TZ aware string
}

# Invalid PATCH payloads
INVALID_UPDATE_PAYLOAD_NAIVE_DT = {
    "start_datetime": "2024-08-02T11:00:00" # Naive
}
INVALID_UPDATE_PAYLOAD_END_BEFORE_START = {
    "start_datetime": "2024-08-02T12:00:00Z",
    "end_datetime": "2024-08-02T11:00:00Z" # End before start
}


@pytest.mark.parametrize("test_user, event_id, request_payload, mock_graph_response, expected_status, expected_detail_contains", [
    # Success Case
    (MOCK_USER_LINKED, "event123", VALID_UPDATE_PAYLOAD, MOCK_GRAPH_UPDATE_RESPONSE, 200, None),
    # Error: User not linked
    (MOCK_USER_NOT_LINKED, "event123", VALID_UPDATE_PAYLOAD, None, 400, "Microsoft account not linked"),
    # Error: Graph API call fails (returns None - could be 404, 5xx etc.)
    (MOCK_USER_LINKED, "event_not_found", VALID_UPDATE_PAYLOAD, None, 503, "Could not update calendar event"),
    # Error: Graph API response missing ID
    (MOCK_USER_LINKED, "event123", VALID_UPDATE_PAYLOAD, MOCK_GRAPH_UPDATE_RESPONSE_NO_ID, 502, "unexpected response format"),
    # Error: Graph API response has bad date (causes Pydantic error)
    (MOCK_USER_LINKED, "event123", VALID_UPDATE_PAYLOAD, MOCK_GRAPH_UPDATE_RESPONSE_BAD_DATE, 500, "Failed to process response"),
    # Error: Empty update payload
    (MOCK_USER_LINKED, "event123", {}, None, 400, "No update data provided"),
])
@patch("zoltar_backend.auth_utils_ms.call_microsoft_graph_api")
def test_update_calendar_event(
    mock_call_graph: MagicMock,
    test_user: models.User,
    event_id: str,
    request_payload: Dict[str, Any],
    mock_graph_response: Optional[Dict[str, Any]],
    expected_status: int,
    expected_detail_contains: Optional[str]
):
    """Tests PATCH /calendar/events/{event_id} for various scenarios."""
    mock_call_graph.return_value = mock_graph_response
    app.dependency_overrides[auth.get_current_active_user] = lambda: test_user

    response = client.patch(f"/calendar/events/{event_id}", json=request_payload)

    assert response.status_code == expected_status

    if expected_detail_contains:
        assert expected_detail_contains.lower() in response.json()["detail"].lower()

    if expected_status == 200:
        mock_call_graph.assert_called_once()
        call_args, call_kwargs = mock_call_graph.call_args
        assert call_kwargs["method"] == "PATCH"
        assert call_kwargs["endpoint"] == f"/me/events/{event_id}"
        assert call_kwargs["ms_oid"] == test_user.ms_oid
        assert "Calendars.ReadWrite" in call_kwargs["scopes"]
        assert call_kwargs["json_data"]["subject"] == VALID_UPDATE_PAYLOAD["subject"] # Check payload generated correctly
        assert call_kwargs["json_data"]["start"]["dateTime"] == VALID_UPDATE_PAYLOAD["start_datetime"]
        
        response_data = response.json()
        assert response_data["id"] == MOCK_GRAPH_UPDATE_RESPONSE["id"]
        assert response_data["subject"] == MOCK_GRAPH_UPDATE_RESPONSE["subject"]
        assert response_data["start_datetime"] == MOCK_GRAPH_UPDATE_RESPONSE["start"]["dateTime"]

    app.dependency_overrides = {}

def test_update_calendar_event_unauthenticated():
    """Tests PATCH /calendar/events/{event_id} without authentication."""
    app.dependency_overrides = {}
    response = client.patch("/calendar/events/event123", json=VALID_UPDATE_PAYLOAD)
    assert response.status_code == 401

@pytest.mark.parametrize("payload, expected_detail_part", [
    (INVALID_UPDATE_PAYLOAD_NAIVE_DT, "datetime must be timezone-aware"),
    (INVALID_UPDATE_PAYLOAD_END_BEFORE_START, "end_datetime must be after start_datetime"),
])
def test_update_calendar_event_invalid_payload(payload: Dict, expected_detail_part: str):
    """Tests PATCH /calendar/events/{event_id} with invalid request bodies (422)."""
    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER_LINKED
    
    response = client.patch("/calendar/events/event123", json=payload)
    
    assert response.status_code == 422
    assert any(expected_detail_part in error["msg"] for error in response.json()["detail"])

    app.dependency_overrides = {}



# Example: 