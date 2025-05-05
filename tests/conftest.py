import pytest
from fastapi.testclient import TestClient
import uuid

# It's common practice to put shared fixtures, especially those needing imports
# like TestClient, into a conftest.py file.
# Pytest automatically discovers fixtures defined in conftest.py files.

# Assuming app is importable this way. Adjust if necessary.
# If app creation itself is complex, you might need another fixture for the client.
try:
    from zoltar_backend.main import app
except ImportError:
    # Handle case where zoltar_backend might not be directly in PYTHONPATH
    # This depends on how pytest is run and the project structure.
    # For now, assume the import works based on `pythonpath = .` in pytest.ini
    app = None # Or raise a configuration error

if app:
    client = TestClient(app)
else:
    client = None # Client needs the app

# Use a fixed test user email + password for simplicity in this example
# If tests run in parallel or interfere, use unique emails (e.g., with uuid)
TEST_USER_EMAIL = f"testuser_conftest_{uuid.uuid4()}@example.com"
TEST_USER_PASSWORD = "testpassword_conftest"

@pytest.fixture(scope="session") # Use session scope for efficiency if user persists across tests
def test_user_token() -> str:
    """
    Fixture to create a test user (if not exists) and return an auth token.
    Session-scoped for efficiency.
    """
    if not client:
        pytest.fail("TestClient could not be initialized. Check FastAPI app import in conftest.py")

    # 1. Attempt to create user
    try:
        user_data = {"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        response = client.post("/users/", json=user_data)
        if response.status_code == 200:
            print(f"Test user {TEST_USER_EMAIL} created (session scope).")
        elif response.status_code == 400 and "already registered" in response.text:
            print(f"Test user {TEST_USER_EMAIL} already exists (session scope).")
        else:
            # Print unexpected errors for better diagnostics
            print(f"Unexpected user creation status: {response.status_code}")
            print(f"Response body: {response.text}")
            response.raise_for_status()
    except Exception as e:
        pytest.fail(f"Failed to create or verify test user in conftest: {e}")

    # 2. Log in to get token
    login_data = {"username": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
    response = client.post("/token", data=login_data) # Use 'data' for form data

    if response.status_code != 200:
         pytest.fail(f"Failed to log in test user {TEST_USER_EMAIL} in conftest. Status: {response.status_code}, Response: {response.text}")

    token_data = response.json()
    token = token_data.get("access_token")

    if not token:
         pytest.fail("Failed to get access_token from /token response in conftest.")

    print(f"Obtained token for {TEST_USER_EMAIL} (session scope)")
    return token

# Fixture for authenticated headers directly, depends on test_user_token
@pytest.fixture(scope="session")
def auth_headers(test_user_token: str) -> dict:
    """Provides authorization headers for authenticated requests."""
    return {"Authorization": f"Bearer {test_user_token}"}

# Fixture to provide the TestClient instance itself
@pytest.fixture(scope="session")
def test_client() -> TestClient:
    """Provides the FastAPI TestClient."""
    if not client:
        pytest.fail("TestClient could not be initialized in conftest.py.")
    return client 