import pytest
from sqlalchemy.orm import Session
from unittest.mock import MagicMock, patch, call, ANY
from datetime import datetime, timezone

from zoltar_backend import crud, models, schemas

# --- Fixtures & Test Data ---

@pytest.fixture
def db_session_mock():
    """Provides a mock SQLAlchemy Session."""
    session = MagicMock(spec=Session)
    session.query.return_value.filter.return_value.first.return_value = None # Default: not found
    session.query.return_value.options.return_value.filter.return_value.first.return_value = None # Default for get_list
    session.query.return_value.options.return_value.filter.return_value.order_by.return_value.all.return_value = [] # Default for get_lists_by_user
    session.query.return_value.join.return_value.filter.return_value.first.return_value = None # Default for item lookups
    return session

@pytest.fixture
def test_user():
    """Provides a mock User object."""
    return models.User(id=1, email="listuser@example.com")

@pytest.fixture
def test_list_create_schema():
    """Provides a ListCreate schema object."""
    return schemas.ListCreate(name="Test List")

@pytest.fixture
def test_list_update_schema():
    """Provides a ListUpdate schema object."""
    return schemas.ListUpdate(name="Updated List Name")

@pytest.fixture
def test_list_item_create_schema():
    """Provides a ListItemCreate schema object."""
    return schemas.ListItemCreate(text="Test Item 1", is_checked=False)

@pytest.fixture
def test_list_item_update_schema():
    """Provides a ListItemUpdate schema object."""
    return schemas.ListItemUpdate(text="Updated Item Text", is_checked=True)

@pytest.fixture
def mock_list_db_obj(test_user):
    """Provides a mock List DB object."""
    now = datetime.now(timezone.utc)
    return models.List(
        id=101,
        name="Existing List",
        user_id=test_user.id,
        created_at=now,
        updated_at=now,
        items=[] # Start with no items for simplicity in list tests
    )

@pytest.fixture
def mock_list_item_db_obj(mock_list_db_obj):
    """Provides a mock ListItem DB object."""
    now = datetime.now(timezone.utc)
    return models.ListItem(
        id=201,
        text="Existing Item",
        list_id=mock_list_db_obj.id,
        is_checked=False,
        created_at=now,
        updated_at=now,
        list=mock_list_db_obj # Link back to parent list
    )

# --- List CRUD Unit Tests ---

def test_create_list(db_session_mock, test_user, test_list_create_schema):
    """Tests creating a list successfully."""
    created_list = crud.create_list(db=db_session_mock, list_data=test_list_create_schema, user_id=test_user.id)

    db_session_mock.add.assert_called_once()
    db_session_mock.commit.assert_called_once()
    db_session_mock.refresh.assert_called_once()
    assert created_list.name == test_list_create_schema.name
    assert created_list.user_id == test_user.id

def test_get_list_found(db_session_mock, test_user, mock_list_db_obj):
    """Tests getting an existing list owned by the user."""
    db_session_mock.query.return_value.options.return_value.filter.return_value.first.return_value = mock_list_db_obj

    found_list = crud.get_list(db=db_session_mock, list_id=mock_list_db_obj.id, user_id=test_user.id)

    assert found_list is not None
    assert found_list.id == mock_list_db_obj.id
    assert found_list.user_id == test_user.id
    # Check joinedload was attempted (exact call depends on SQLAlchemy internals, checking options() is indicative)
    db_session_mock.query.return_value.options.assert_called_once()

def test_get_list_not_found(db_session_mock, test_user):
    """Tests getting a non-existent list."""
    db_session_mock.query.return_value.options.return_value.filter.return_value.first.return_value = None
    found_list = crud.get_list(db=db_session_mock, list_id=999, user_id=test_user.id)
    assert found_list is None

def test_get_list_wrong_user(db_session_mock, test_user, mock_list_db_obj):
    """Tests getting a list owned by another user (should return None)."""
    # Setup mock to return None because the filter user_id wouldn't match
    db_session_mock.query.return_value.options.return_value.filter.return_value.first.return_value = None
    found_list = crud.get_list(db=db_session_mock, list_id=mock_list_db_obj.id, user_id=test_user.id + 1)
    assert found_list is None

def test_get_lists_by_user(db_session_mock, test_user, mock_list_db_obj):
    """Tests retrieving all lists for a user."""
    db_session_mock.query.return_value.options.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_list_db_obj]

    lists = crud.get_lists_by_user(db=db_session_mock, user_id=test_user.id)

    assert len(lists) == 1
    assert lists[0].id == mock_list_db_obj.id
    db_session_mock.query.return_value.options.assert_called_once()

def test_update_list_success(db_session_mock, test_user, mock_list_db_obj, test_list_update_schema):
    """Tests updating a list successfully."""
    # Mock get_list to return the object to be updated
    db_session_mock.query.return_value.options.return_value.filter.return_value.first.return_value = mock_list_db_obj

    updated_list = crud.update_list(db=db_session_mock, list_id=mock_list_db_obj.id, list_data=test_list_update_schema, user_id=test_user.id)

    assert updated_list is not None
    assert updated_list.name == test_list_update_schema.name
    assert updated_list.updated_at is not None # Check timestamp was set
    db_session_mock.commit.assert_called_once()
    db_session_mock.refresh.assert_called_once()

def test_update_list_not_found(db_session_mock, test_user, test_list_update_schema):
    """Tests updating a non-existent list."""
    db_session_mock.query.return_value.options.return_value.filter.return_value.first.return_value = None
    updated_list = crud.update_list(db=db_session_mock, list_id=999, list_data=test_list_update_schema, user_id=test_user.id)
    assert updated_list is None
    db_session_mock.commit.assert_not_called()

def test_delete_list_success(db_session_mock, test_user, mock_list_db_obj):
    """Tests deleting a list successfully."""
    db_session_mock.query.return_value.options.return_value.filter.return_value.first.return_value = mock_list_db_obj

    deleted = crud.delete_list(db=db_session_mock, list_id=mock_list_db_obj.id, user_id=test_user.id)

    assert deleted is True
    db_session_mock.delete.assert_called_once_with(mock_list_db_obj)
    db_session_mock.commit.assert_called_once()

def test_delete_list_not_found(db_session_mock, test_user):
    """Tests deleting a non-existent list."""
    db_session_mock.query.return_value.options.return_value.filter.return_value.first.return_value = None
    deleted = crud.delete_list(db=db_session_mock, list_id=999, user_id=test_user.id)
    assert deleted is False
    db_session_mock.delete.assert_not_called()
    db_session_mock.commit.assert_not_called()


# --- ListItem CRUD Unit Tests ---

def test_create_list_item_success(db_session_mock, test_user, mock_list_db_obj, test_list_item_create_schema):
    """Tests creating a list item successfully."""
    # Mock get_list to return the parent list
    db_session_mock.query.return_value.options.return_value.filter.return_value.first.return_value = mock_list_db_obj

    created_item = crud.create_list_item(db=db_session_mock, item_data=test_list_item_create_schema, list_id=mock_list_db_obj.id, user_id=test_user.id)

    assert isinstance(created_item, models.ListItem) # Check it's not an error string
    assert created_item.text == test_list_item_create_schema.text
    assert created_item.list_id == mock_list_db_obj.id
    db_session_mock.add.assert_called_once()
    db_session_mock.commit.assert_called_once()
    db_session_mock.refresh.assert_called_once()

def test_create_list_item_list_not_found(db_session_mock, test_user, test_list_item_create_schema):
    """Tests creating an item when the parent list doesn't exist or isn't owned."""
    db_session_mock.query.return_value.options.return_value.filter.return_value.first.return_value = None

    result = crud.create_list_item(db=db_session_mock, item_data=test_list_item_create_schema, list_id=999, user_id=test_user.id)

    assert result == "list_not_found"
    db_session_mock.add.assert_not_called()
    db_session_mock.commit.assert_not_called()

def test_update_list_item_success(db_session_mock, test_user, mock_list_item_db_obj, test_list_item_update_schema):
    """Tests updating a list item successfully."""
    # Mock the join query to return the item
    db_session_mock.query.return_value.join.return_value.filter.return_value.first.return_value = mock_list_item_db_obj

    updated_item = crud.update_list_item(db=db_session_mock, item_id=mock_list_item_db_obj.id, item_data=test_list_item_update_schema, user_id=test_user.id)

    assert isinstance(updated_item, models.ListItem)
    assert updated_item.text == test_list_item_update_schema.text
    assert updated_item.is_checked == test_list_item_update_schema.is_checked
    assert updated_item.updated_at is not None
    db_session_mock.add.assert_called_once_with(mock_list_item_db_obj)
    db_session_mock.commit.assert_called_once()
    db_session_mock.refresh.assert_called_once_with(mock_list_item_db_obj)

def test_update_list_item_not_found(db_session_mock, test_user, test_list_item_update_schema):
    """Tests updating a non-existent item or one not owned by user."""
    db_session_mock.query.return_value.join.return_value.filter.return_value.first.return_value = None

    result = crud.update_list_item(db=db_session_mock, item_id=999, item_data=test_list_item_update_schema, user_id=test_user.id)

    assert result == "item_not_found"
    db_session_mock.add.assert_not_called()
    db_session_mock.commit.assert_not_called()

def test_delete_list_item_success(db_session_mock, test_user, mock_list_item_db_obj):
    """Tests deleting a list item successfully."""
    db_session_mock.query.return_value.join.return_value.filter.return_value.first.return_value = mock_list_item_db_obj

    deleted = crud.delete_list_item(db=db_session_mock, item_id=mock_list_item_db_obj.id, user_id=test_user.id)

    assert deleted is True
    db_session_mock.delete.assert_called_once_with(mock_list_item_db_obj)
    db_session_mock.commit.assert_called_once()

def test_delete_list_item_not_found(db_session_mock, test_user):
    """Tests deleting a non-existent item or one not owned by user."""
    db_session_mock.query.return_value.join.return_value.filter.return_value.first.return_value = None

    deleted = crud.delete_list_item(db=db_session_mock, item_id=999, user_id=test_user.id)

    assert deleted is False
    db_session_mock.delete.assert_not_called()
    db_session_mock.commit.assert_not_called() 