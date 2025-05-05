import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, ANY
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple

# Adjust the import path based on your project structure
from zoltar_backend.main import app # Import your FastAPI app instance
from zoltar_backend import schemas, models, auth # Import relevant schemas and models

# Create a TestClient instance
client = TestClient(app)

# --- Test Data & Mocks ---

# Mock User Data (assuming same structure as in test_calendar)
MOCK_USER = models.User(
    id=1,
    email="notesuser@example.com",
    ms_oid=None, # Not relevant for this test but need a complete object
    is_active=True,
    created_at=datetime.now(timezone.utc)
)

# Mock CRUD responses
MOCK_CRUD_SUCCESS_RESPONSE: Tuple[List[int], str] = ([1, 3], "Note 1 content.\n---\nNote 3 content.")
MOCK_CRUD_EMPTY_RESPONSE: Tuple[List[int], str] = ([], "")

# Mock LLM responses
MOCK_LLM_SUCCESS_SUMMARY = "This is the generated summary."

# Valid Request Payload
VALID_SUMMARY_REQUEST = {"note_ids": [1, 3]}

# Invalid Request Payload (no filters)
INVALID_SUMMARY_REQUEST_NO_FILTER = {}


# Helper to override the dependency
def override_get_current_active_user_notes():
    # This function will be replaced by the actual user in tests
    pass

# Apply the dependency override globally for tests in this module
# Use a different name to avoid potential conflicts if running all tests
app.dependency_overrides[auth.get_current_active_user] = override_get_current_active_user_notes

# --- Test Cases ---

@pytest.mark.parametrize(
    "mock_crud_return, mock_llm_return, mock_crud_exception, expected_status, expected_summary, expected_ids",
    [
        # Success Case
        (MOCK_CRUD_SUCCESS_RESPONSE, MOCK_LLM_SUCCESS_SUMMARY, None, 200, MOCK_LLM_SUCCESS_SUMMARY, [1, 3]),
        # No Notes Found Case
        (MOCK_CRUD_EMPTY_RESPONSE, None, None, 200, "No notes match the filter criteria.", []),
        # LLM Failure Case
        (MOCK_CRUD_SUCCESS_RESPONSE, None, None, 503, None, None),
        # CRUD Failure Case
        (None, None, Exception("DB Error"), 500, None, None),
    ]
)
@patch("zoltar_backend.llm_utils.summarize_text_gemini")
@patch("zoltar_backend.crud.get_notes_content_by_filter")
def test_summarize_notes(
    mock_get_notes: MagicMock,
    mock_summarize: MagicMock,
    mock_crud_return: Optional[Tuple[List[int], str]],
    mock_llm_return: Optional[str],
    mock_crud_exception: Optional[Exception],
    expected_status: int,
    expected_summary: Optional[str],
    expected_ids: Optional[List[int]],
):
    """Tests POST /notes/summary for various scenarios."""
    # Configure mocks
    if mock_crud_exception:
        mock_get_notes.side_effect = mock_crud_exception
    else:
        mock_get_notes.return_value = mock_crud_return
        
    mock_summarize.return_value = mock_llm_return

    # Override user dependency
    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER

    response = client.post("/notes/summary", json=VALID_SUMMARY_REQUEST)

    assert response.status_code == expected_status

    if expected_status == 200:
        response_data = response.json()
        assert response_data["summary"] == expected_summary
        assert response_data["included_note_ids"] == expected_ids
    elif expected_status == 503:
        assert "LLM error" in response.json()["detail"]
    elif expected_status == 500:
         assert "Failed to retrieve notes" in response.json()["detail"]

    # Verify mocks were called appropriately
    # Use the schema for precise matching
    expected_filters = schemas.NoteSummaryRequest(**VALID_SUMMARY_REQUEST)
    mock_get_notes.assert_called_once_with(db=ANY, user_id=MOCK_USER.id, filters=expected_filters)
    if mock_crud_return and mock_crud_return[0]: # If CRUD was expected to return notes
        mock_summarize.assert_called_once_with(text_to_summarize=mock_crud_return[1])
    else:
        mock_summarize.assert_not_called()

    # Clean up override
    app.dependency_overrides = {}

def test_summarize_notes_unauthenticated():
    """Tests POST /notes/summary without authentication."""
    app.dependency_overrides = {}
    response = client.post("/notes/summary", json=VALID_SUMMARY_REQUEST)
    assert response.status_code == 401

def test_summarize_notes_invalid_payload():
    """Tests POST /notes/summary with invalid payload (no filter)."""
    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER
    response = client.post("/notes/summary", json=INVALID_SUMMARY_REQUEST_NO_FILTER)
    assert response.status_code == 422
    # Check Pydantic validation error detail
    assert "At least one filter" in response.json()["detail"][0]["msg"]
    app.dependency_overrides = {} 