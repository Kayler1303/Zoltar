import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, ANY
from datetime import datetime, timezone
from typing import List, Optional

# Adjust the import path based on your project structure
from zoltar_backend.main import app # Import your FastAPI app instance
from zoltar_backend import schemas, models, auth, crud # Import relevant components

# Create a TestClient instance
client = TestClient(app)

# --- Test Data & Mocks ---

# Mock User Data
MOCK_USER = models.User(
    id=1,
    email="listtester@example.com",
    ms_oid=None,
    is_active=True,
    created_at=datetime.now(timezone.utc)
)

# Mock List Data
MOCK_LIST_ID = 101
MOCK_LIST_ITEM_ID = 201
NOW = datetime.now(timezone.utc)

MOCK_LIST_RESPONSE = models.List(
    id=MOCK_LIST_ID,
    name="Shopping List",
    user_id=MOCK_USER.id,
    created_at=NOW,
    updated_at=NOW,
    items=[] # Initialize with empty items
)

MOCK_LIST_ITEM_RESPONSE = models.ListItem(
    id=MOCK_LIST_ITEM_ID,
    text="Milk",
    list_id=MOCK_LIST_ID,
    is_checked=False,
    created_at=NOW,
    updated_at=NOW
)

# Populate items in the mock list response
MOCK_LIST_RESPONSE.items = [MOCK_LIST_ITEM_RESPONSE]

# Payloads
LIST_CREATE_PAYLOAD = {"name": "New List"}
LIST_UPDATE_PAYLOAD = {"name": "Updated List Name"}
LIST_ITEM_CREATE_PAYLOAD = {"text": "Eggs", "is_checked": False}
LIST_ITEM_UPDATE_PAYLOAD = {"text": "Bread", "is_checked": True}

# Helper to override the dependency
def override_get_current_active_user_lists():
    # This function will be replaced by the actual user in tests
    pass

# Apply the dependency override globally for tests in this module
# Use a different name to avoid conflicts if running all tests together
app.dependency_overrides[auth.get_current_active_user] = override_get_current_active_user_lists

# --- Test Cases ---

# --- List Endpoint Tests ---

@patch("zoltar_backend.crud.create_list")
def test_create_list_success(mock_crud_create):
    """Tests POST /lists/ success (200)."""
    mock_crud_create.return_value = MOCK_LIST_RESPONSE # Return a full model instance
    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER

    response = client.post("/lists/", json=LIST_CREATE_PAYLOAD)

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["name"] == MOCK_LIST_RESPONSE.name # Check against mock response
    assert response_data["id"] == MOCK_LIST_RESPONSE.id
    mock_crud_create.assert_called_once_with(db=ANY, list_data=schemas.ListCreate(**LIST_CREATE_PAYLOAD), user_id=MOCK_USER.id)
    app.dependency_overrides = {}

def test_create_list_unauthenticated():
    """Tests POST /lists/ without authentication (401)."""
    app.dependency_overrides = {}
    response = client.post("/lists/", json=LIST_CREATE_PAYLOAD)
    assert response.status_code == 401

@patch("zoltar_backend.crud.get_lists_by_user")
def test_read_lists_success(mock_crud_get_all):
    """Tests GET /lists/ success (200)."""
    mock_crud_get_all.return_value = [MOCK_LIST_RESPONSE]
    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER

    response = client.get("/lists/")

    assert response.status_code == 200
    response_data = response.json()
    assert len(response_data) == 1
    assert response_data[0]["id"] == MOCK_LIST_ID
    mock_crud_get_all.assert_called_once_with(db=ANY, user_id=MOCK_USER.id)
    app.dependency_overrides = {}

def test_read_lists_unauthenticated():
    """Tests GET /lists/ without authentication (401)."""
    app.dependency_overrides = {}
    response = client.get("/lists/")
    assert response.status_code == 401

@patch("zoltar_backend.crud.get_list")
def test_read_list_success(mock_crud_get):
    """Tests GET /lists/{list_id} success (200)."""
    mock_crud_get.return_value = MOCK_LIST_RESPONSE
    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER

    response = client.get(f"/lists/{MOCK_LIST_ID}")

    assert response.status_code == 200
    assert response.json()["id"] == MOCK_LIST_ID
    mock_crud_get.assert_called_once_with(db=ANY, list_id=MOCK_LIST_ID, user_id=MOCK_USER.id)
    app.dependency_overrides = {}

@patch("zoltar_backend.crud.get_list")
def test_read_list_not_found(mock_crud_get):
    """Tests GET /lists/{list_id} not found (404)."""
    mock_crud_get.return_value = None
    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER

    response = client.get(f"/lists/{MOCK_LIST_ID + 99}")

    assert response.status_code == 404
    mock_crud_get.assert_called_once_with(db=ANY, list_id=MOCK_LIST_ID + 99, user_id=MOCK_USER.id)
    app.dependency_overrides = {}

def test_read_list_unauthenticated():
    """Tests GET /lists/{list_id} without authentication (401)."""
    app.dependency_overrides = {}
    response = client.get(f"/lists/{MOCK_LIST_ID}")
    assert response.status_code == 401

@patch("zoltar_backend.crud.update_list")
def test_update_list_success(mock_crud_update):
    """Tests PUT /lists/{list_id} success (200)."""
    # Create a response object reflecting the update by copying attributes
    updated_mock_response = models.List(
        id=MOCK_LIST_RESPONSE.id,
        name=LIST_UPDATE_PAYLOAD["name"], # Use updated name
        user_id=MOCK_LIST_RESPONSE.user_id,
        created_at=MOCK_LIST_RESPONSE.created_at,
        updated_at=datetime.now(timezone.utc), # Simulate update time
        items=MOCK_LIST_RESPONSE.items
    )
    mock_crud_update.return_value = updated_mock_response

    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER

    response = client.put(f"/lists/{MOCK_LIST_ID}", json=LIST_UPDATE_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["name"] == LIST_UPDATE_PAYLOAD["name"]
    mock_crud_update.assert_called_once_with(db=ANY, list_id=MOCK_LIST_ID, list_data=schemas.ListUpdate(**LIST_UPDATE_PAYLOAD), user_id=MOCK_USER.id)
    app.dependency_overrides = {}

@patch("zoltar_backend.crud.update_list")
def test_update_list_not_found(mock_crud_update):
    """Tests PUT /lists/{list_id} not found (404)."""
    mock_crud_update.return_value = None
    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER

    response = client.put(f"/lists/{MOCK_LIST_ID + 99}", json=LIST_UPDATE_PAYLOAD)

    assert response.status_code == 404
    app.dependency_overrides = {}

def test_update_list_unauthenticated():
    """Tests PUT /lists/{list_id} without authentication (401)."""
    app.dependency_overrides = {}
    response = client.put(f"/lists/{MOCK_LIST_ID}", json=LIST_UPDATE_PAYLOAD)
    assert response.status_code == 401

@patch("zoltar_backend.crud.delete_list")
def test_delete_list_success(mock_crud_delete):
    """Tests DELETE /lists/{list_id} success (200)."""
    mock_crud_delete.return_value = True
    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER

    response = client.delete(f"/lists/{MOCK_LIST_ID}")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    mock_crud_delete.assert_called_once_with(db=ANY, list_id=MOCK_LIST_ID, user_id=MOCK_USER.id)
    app.dependency_overrides = {}

@patch("zoltar_backend.crud.delete_list")
def test_delete_list_not_found(mock_crud_delete):
    """Tests DELETE /lists/{list_id} not found (404)."""
    mock_crud_delete.return_value = False
    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER

    response = client.delete(f"/lists/{MOCK_LIST_ID + 99}")

    assert response.status_code == 404
    app.dependency_overrides = {}

def test_delete_list_unauthenticated():
    """Tests DELETE /lists/{list_id} without authentication (401)."""
    app.dependency_overrides = {}
    response = client.delete(f"/lists/{MOCK_LIST_ID}")
    assert response.status_code == 401

# --- ListItem Endpoint Tests ---

@patch("zoltar_backend.crud.create_list_item")
def test_create_list_item_success(mock_crud_create_item):
    """Tests POST /{list_id}/items/ success (200)."""
    mock_crud_create_item.return_value = MOCK_LIST_ITEM_RESPONSE
    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER

    response = client.post(f"/lists/{MOCK_LIST_ID}/items/", json=LIST_ITEM_CREATE_PAYLOAD)

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["text"] == MOCK_LIST_ITEM_RESPONSE.text
    assert response_data["id"] == MOCK_LIST_ITEM_ID
    mock_crud_create_item.assert_called_once_with(
        db=ANY,
        item_data=schemas.ListItemCreate(**LIST_ITEM_CREATE_PAYLOAD),
        list_id=MOCK_LIST_ID,
        user_id=MOCK_USER.id
    )
    app.dependency_overrides = {}

@patch("zoltar_backend.crud.create_list_item")
def test_create_list_item_list_not_found(mock_crud_create_item):
    """Tests POST /{list_id}/items/ parent list not found (404)."""
    mock_crud_create_item.return_value = "list_not_found"
    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER

    response = client.post(f"/lists/{MOCK_LIST_ID + 99}/items/", json=LIST_ITEM_CREATE_PAYLOAD)

    assert response.status_code == 404
    assert "Parent list not found" in response.json()["detail"]
    app.dependency_overrides = {}

def test_create_list_item_unauthenticated():
    """Tests POST /{list_id}/items/ without authentication (401)."""
    app.dependency_overrides = {}
    response = client.post(f"/lists/{MOCK_LIST_ID}/items/", json=LIST_ITEM_CREATE_PAYLOAD)
    assert response.status_code == 401

@patch("zoltar_backend.crud.update_list_item")
def test_update_list_item_success(mock_crud_update_item):
    """Tests PUT /items/{item_id} success (200)."""
    # Create a response reflecting the update by copying attributes
    updated_item_response = models.ListItem(
        id=MOCK_LIST_ITEM_RESPONSE.id,
        text=LIST_ITEM_UPDATE_PAYLOAD["text"], # Use updated text
        list_id=MOCK_LIST_ITEM_RESPONSE.list_id,
        is_checked=LIST_ITEM_UPDATE_PAYLOAD["is_checked"], # Use updated status
        created_at=MOCK_LIST_ITEM_RESPONSE.created_at,
        updated_at=datetime.now(timezone.utc) # Simulate update time
    )
    mock_crud_update_item.return_value = updated_item_response

    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER

    response = client.put(f"/lists/items/{MOCK_LIST_ITEM_ID}", json=LIST_ITEM_UPDATE_PAYLOAD)

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["text"] == LIST_ITEM_UPDATE_PAYLOAD["text"]
    assert response_data["is_checked"] == LIST_ITEM_UPDATE_PAYLOAD["is_checked"]
    mock_crud_update_item.assert_called_once_with(
        db=ANY,
        item_id=MOCK_LIST_ITEM_ID,
        item_data=schemas.ListItemUpdate(**LIST_ITEM_UPDATE_PAYLOAD),
        user_id=MOCK_USER.id
    )
    app.dependency_overrides = {}

@patch("zoltar_backend.crud.update_list_item")
def test_update_list_item_not_found(mock_crud_update_item):
    """Tests PUT /items/{item_id} item not found (404)."""
    mock_crud_update_item.return_value = "item_not_found"
    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER

    response = client.put(f"/lists/items/{MOCK_LIST_ITEM_ID + 99}", json=LIST_ITEM_UPDATE_PAYLOAD)

    assert response.status_code == 404
    assert "List item not found" in response.json()["detail"]
    app.dependency_overrides = {}

def test_update_list_item_unauthenticated():
    """Tests PUT /items/{item_id} without authentication (401)."""
    app.dependency_overrides = {}
    response = client.put(f"/lists/items/{MOCK_LIST_ITEM_ID}", json=LIST_ITEM_UPDATE_PAYLOAD)
    assert response.status_code == 401

@patch("zoltar_backend.crud.delete_list_item")
def test_delete_list_item_success(mock_crud_delete_item):
    """Tests DELETE /items/{item_id} success (200)."""
    mock_crud_delete_item.return_value = True
    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER

    response = client.delete(f"/lists/items/{MOCK_LIST_ITEM_ID}")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    mock_crud_delete_item.assert_called_once_with(db=ANY, item_id=MOCK_LIST_ITEM_ID, user_id=MOCK_USER.id)
    app.dependency_overrides = {}

@patch("zoltar_backend.crud.delete_list_item")
def test_delete_list_item_not_found(mock_crud_delete_item):
    """Tests DELETE /items/{item_id} item not found (404)."""
    mock_crud_delete_item.return_value = False
    app.dependency_overrides[auth.get_current_active_user] = lambda: MOCK_USER

    response = client.delete(f"/lists/items/{MOCK_LIST_ITEM_ID + 99}")

    assert response.status_code == 404
    assert "List item not found" in response.json()["detail"]
    app.dependency_overrides = {}

def test_delete_list_item_unauthenticated():
    """Tests DELETE /items/{item_id} without authentication (401)."""
    app.dependency_overrides = {}
    response = client.delete(f"/lists/items/{MOCK_LIST_ITEM_ID}")
    assert response.status_code == 401 