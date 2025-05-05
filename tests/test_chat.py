from fastapi.testclient import TestClient
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
import requests # Needed for mocking requests.post

from zoltar_backend import schemas
from zoltar_backend import crud # Import crud directly for patch.object
from zoltar_backend import llm_utils # Import llm_utils for patch.object
from zoltar_backend import models # Import models for mock objects

# Fixtures like auth_headers and test_client are now expected to come from conftest.py

def test_send_chat_message_unauthenticated(test_client: TestClient):
    response = test_client.post("/chat/message", json={"text": "Hello Zoltar"})
    assert response.status_code == 401

# === Test successful routing and response generation ===

# Re-introduce generate_response_text mock
@patch.object(llm_utils, 'generate_response_text') 
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_with_response(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test routing and response generation for create_reminder."""
    message_text = "Remind me about the report tomorrow 10am"
    # Use a slightly different description for testing
    reminder_desc = "the report" 
    iso_time = "2024-08-16T10:00:00"
    expected_dt = datetime.fromisoformat(iso_time)

    mock_llm_intent_response = {
        "intent": "create_reminder",
        # Ensure LLM mock provides description
        "entities": {"description": reminder_desc, "trigger_datetime_iso": iso_time} 
    }
    mock_created_reminder = MagicMock(spec=schemas.Reminder)
    mock_created_reminder.id = 123
    # Add description to the mock CRUD result object
    mock_created_reminder.description = reminder_desc 
    mock_created_reminder.trigger_datetime = expected_dt 
    
    # Expected entities passed TO the generator after successful creation
    expected_entities_for_generator = { 
        "description": reminder_desc, 
        "trigger_datetime_iso": iso_time,
        "created_reminder_id": 123,
        "created_description": reminder_desc,
        "created_trigger_datetime": expected_dt.isoformat()
    }
    # Mock the final text returned BY the generator
    mock_final_response_text = "Generated success message for reminder 123"

    mock_extract.return_value = mock_llm_intent_response
    mock_create.return_value = mock_created_reminder
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    
    # Verify CRUD call arguments
    mock_create.assert_called_once()
    args, kwargs = mock_create.call_args
    assert "db" in kwargs
    assert "owner_id" in kwargs
    reminder_schema = kwargs['reminder']
    assert isinstance(reminder_schema, schemas.ReminderCreate)
    # Check description passed to CRUD
    assert reminder_schema.description == reminder_desc 
    assert reminder_schema.trigger_datetime == expected_dt
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator # Router passes modified entities
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_task')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_task_with_response(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test routing and response generation for create_task."""
    message_text = "Create task: Submit expense report by Friday EOD"
    task_title = "Submit expense report"
    # Add description for testing
    task_desc = "Need to include receipts" 
    iso_date = "2024-08-16T17:00:00" # Changed to EOD-like time
    expected_dt = datetime.fromisoformat(iso_date)

    mock_llm_intent_response = {
        "intent": "create_task",
        # Ensure LLM mock provides title, description, and due_date
        "entities": {"title": task_title, "description": task_desc, "due_date_iso": iso_date} 
    }
    mock_created_task = MagicMock(spec=schemas.Task)
    mock_created_task.id = 456
    mock_created_task.title = task_title
    # Add description to the mock CRUD result object
    mock_created_task.description = task_desc 
    mock_created_task.due_date = expected_dt # Add due_date to mock result

    # Expected entities passed TO the generator after successful creation
    expected_entities_for_generator = { 
        "title": task_title, 
        "description": task_desc, 
        "due_date_iso": iso_date,
        "created_task_id": 456,
        "created_title": task_title,
        "created_description": task_desc,
        "created_due_date": expected_dt.isoformat()
    }
    # Mock the final text returned BY the generator
    mock_final_response_text = "Generated success message for task 456"

    mock_extract.return_value = mock_llm_intent_response
    mock_create.return_value = mock_created_task
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)

    # Verify CRUD call arguments
    mock_create.assert_called_once()
    args, kwargs = mock_create.call_args
    assert "db" in kwargs
    assert "owner_id" in kwargs
    task_schema = kwargs['task']
    assert isinstance(task_schema, schemas.TaskCreate)
    assert task_schema.title == task_title
    # Check description passed to CRUD
    assert task_schema.description == task_desc 
    # Check due_date passed to CRUD (this will fail until router is fixed)
    assert task_schema.due_date == expected_dt 

    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_task", expected_entities_for_generator)

    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_task"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

# --- Test LLM/Routing/Response Failures --- 

@patch.object(llm_utils, 'generate_response_text')
@patch.object(llm_utils, 'extract_intent_entities')
def test_send_chat_message_llm_failure(mock_extract, mock_generate_response, test_client: TestClient, auth_headers: dict):
    """Test scenario where the initial LLM intent extraction fails."""
    message_text = "This should fail"
    mock_extract.return_value = None 
    expected_response_text = "Sorry, I encountered an error trying to understand that." # Or similar generic failure message
    # Mock the generator for the failure case - it might still be called
    mock_generate_response.return_value = expected_response_text
    
    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )
    
    assert response.status_code == 503 # Original exception raised
    assert response.json() == {"detail": "LLM service unavailable or failed."}
    mock_extract.assert_called_once_with(message_text)
    # Generator should NOT be called if initial extraction fails and raises HTTP Exception
    mock_generate_response.assert_not_called()

def test_send_chat_message_invalid_input(test_client: TestClient, auth_headers: dict):
    """Test sending invalid JSON payload."""
    response = test_client.post(
        "/chat/message", json={"message": "This field is wrong"}, headers=auth_headers
    )
    assert response.status_code == 422 

@patch.object(llm_utils, 'generate_response_text') 
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text



@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text

@patch.object(llm_utils, 'generate_response_text')
@patch.object(crud, 'create_user_reminder')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_create_reminder_missing_entities(
    mock_extract, mock_create, mock_generate_response, # Added mock_generate_response
    test_client: TestClient, auth_headers: dict
):
    """Test create_reminder route calls generator with error context when entities missing."""
    message_text = "Remind me"
    mock_llm_response = {"intent": "create_reminder", "entities": {}}
    # Expected entities passed TO generator (includes error context)
    expected_entities_for_generator = { 
        "error": "missing_required_entities",
        "missing": ["description", "trigger_datetime_iso"]
    }
    # Mock the final text returned BY the generator for this error
    mock_final_response_text = "Generated response for missing reminder entities"

    mock_extract.return_value = mock_llm_response
    mock_generate_response.return_value = mock_final_response_text

    response = test_client.post(
        "/chat/message", json={"text": message_text}, headers=auth_headers
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_create.assert_not_called()
    
    # Assert generate_response_text was called correctly
    mock_generate_response.assert_called_once_with("create_reminder", expected_entities_for_generator)
    
    # Assert the actual response JSON uses the generator's output
    response_data = response.json()
    assert response_data["intent"] == "create_reminder"
    assert response_data["entities"] == expected_entities_for_generator
    assert response_data["response_text"] == mock_final_response_text
# --- Test File Association Trigger ---

@patch.object(crud, 'update_file_reference_links') # Mock the CRUD function
@patch.object(llm_utils, 'generate_response_text')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_associate_file_success(
    mock_extract, mock_generate_response, mock_crud_update,
    test_client: TestClient, auth_headers: dict
):
    """Test successful routing and response for associate_file."""
    message_text = "Link file 7 to task 15"
    file_id = 7
    target_type = "task"
    target_id = 15
    mock_task_title = "The Task Title"

    # Mock LLM extraction
    mock_extract.return_value = {
        "intent": "associate_file",
        "entities": {"file_id": file_id, "target_type": target_type, "target_id": target_id}
    }

    # Mock CRUD success
    mock_updated_file_ref = MagicMock(spec=models.FileReference)
    mock_updated_file_ref.id = file_id
    mock_updated_file_ref.task_id = target_id
    mock_updated_file_ref.task = MagicMock(spec=models.Task)
    mock_updated_file_ref.task.title = mock_task_title # Include linked item name
    # Add project attribute for completeness, even if None
    mock_updated_file_ref.project = None
    mock_crud_update.return_value = mock_updated_file_ref

    # Mock final response generation
    expected_final_response_text = f"Generated association success message for file {file_id}"
    mock_generate_response.return_value = expected_final_response_text

    # Send request
    response = test_client.post(
        "/chat/message", headers=auth_headers, json={"text": message_text}
    )

    # Assertions
    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)

    # Verify CRUD call
    mock_crud_update.assert_called_once()
    args, kwargs = mock_crud_update.call_args
    assert kwargs.get('file_id') == file_id
    assert kwargs.get('user_id') is not None # Should be passed from Depends
    update_data = kwargs.get('update_data')
    assert isinstance(update_data, schemas.FileReferenceUpdate)
    assert update_data.task_id == target_id
    assert update_data.project_id is None

    # Verify final response generation call
    expected_entities_for_generator = {
        "file_id": file_id,
        "target_type": target_type,
        "target_id": target_id,
        "association_details": {
            "file_id": file_id,
            "target_type": target_type,
            "target_id": target_id,
            "success": True,
            "task_title": mock_task_title,
            "project_name": None # Ensure this key exists even if None
        }
    }
    mock_generate_response.assert_called_once_with(
        "associate_file",
        expected_entities_for_generator
    )

    # Verify final API response
    assert response.json() == {
        "intent": "associate_file",
        "entities": expected_entities_for_generator,
        "response_text": expected_final_response_text
    }

@patch.object(crud, 'update_file_reference_links') # Mock the CRUD function
@patch.object(llm_utils, 'generate_response_text')
@patch.object(llm_utils, 'extract_intent_entities')
def test_route_associate_file_crud_error(
    mock_extract, mock_generate_response, mock_crud_update,
    test_client: TestClient, auth_headers: dict
):
    """Test handling when CRUD association returns an error string."""
    message_text = "Associate file 10 with project 50"
    file_id = 10
    target_type = "project"
    target_id = 50
    crud_error_code = "invalid_project" # Simulate project not found

    mock_extract.return_value = {
        "intent": "associate_file",
        "entities": {"file_id": file_id, "target_type": target_type, "target_id": target_id}
    }

    mock_crud_update.return_value = crud_error_code # Simulate CRUD error

    expected_final_response_text = "Generated CRUD error response"
    mock_generate_response.return_value = expected_final_response_text

    response = test_client.post(
        "/chat/message", headers=auth_headers, json={"text": message_text}
    )

    assert response.status_code == 200
    mock_extract.assert_called_once_with(message_text)
    mock_crud_update.assert_called_once() # Ensure CRUD was called

    # Verify response generator called with error context
    expected_entities_for_generator = {
        "file_id": file_id,
        "target_type": target_type,
        "target_id": target_id,
        "error": "invalid_target",
        "details": f"Project ID {target_id} not found or you don't own it."
    }
    mock_generate_response.assert_called_once_with(
        "associate_file",
        expected_entities_for_generator
    )

    assert response.json() == {
        "intent": "associate_file",
        "entities": expected_entities_for_generator,
        "response_text": expected_final_response_text
    }

# TODO: Add tests for other error cases:
# - Invalid file_id/target_type/target_id extracted by LLM
# - CRUD returns None (file not found)
# - CRUD returns "unauthorized_file"

