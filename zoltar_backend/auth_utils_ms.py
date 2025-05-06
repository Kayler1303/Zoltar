import msal
import os
import logging
import json # Needed for cache serialization
from typing import Optional, Union, Dict, List, Any
from sqlalchemy.orm import Session # Need Session for DB access
from . import models # Need User model
import requests # Add requests import if not already present
from datetime import datetime, timezone # Make sure datetime and timezone are imported
from . import schemas # Need CalendarEventCreate schema

logger = logging.getLogger(__name__)

# --- Configuration ---
# Load configuration from environment variables (replace placeholders with your actual values)
# Ensure these are set in your environment before running the app.
# DO NOT commit the client secret directly into the code.
MS_CLIENT_ID = os.environ.get("MS_CLIENT_ID", "YOUR_MS_CLIENT_ID_HERE")
MS_CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET", "YOUR_MS_CLIENT_SECRET_HERE")
# Use 'common' for multi-tenant + personal accounts, 'organizations' for multi-tenant work/school only,
# or a specific tenant ID (UUID) for single-tenant.
MS_TENANT_ID = os.environ.get("MS_TENANT_ID", "common") 
MS_AUTHORITY = f"https://login.microsoftonline.com/{MS_TENANT_ID}"
# Ensure this matches EXACTLY what you registered in Azure AD
MS_REDIRECT_URI = os.environ.get("MS_REDIRECT_URI", "http://localhost:8000/auth/microsoft/callback") 
# Scopes required for accessing calendar data and maintaining login
# MSAL handles offline_access implicitly for confidential clients
MS_SCOPES = ["User.Read", "Calendars.ReadWrite"] # Removed offline_access

# --- MSAL Client Initialization ---
# Use a SerializableTokenCache instance for easier loading/saving
token_cache = msal.SerializableTokenCache()
msal_client = msal.ConfidentialClientApplication(
    MS_CLIENT_ID,
    authority=MS_AUTHORITY,
    client_credential=MS_CLIENT_SECRET,
    # Optional: Configure token cache (useful for production, complex for now)
    # token_cache=msal.SerializableTokenCache() 
    token_cache=token_cache # Pass the cache instance here
)

# --- Placeholder for Token Storage ---
# WARNING: This is NOT production-ready. 
# For development only, stores tokens in memory.
# A proper solution would use a database or secure session storage.
# Key: User identifier (e.g., MS object ID or email), Value: MSAL token cache state
# We need to figure out how to map Zoltar users to MS users later.
# token_cache_store = {} # No longer used

# --- Function Stubs (to be implemented next) ---

def get_ms_auth_url(state: Optional[str] = None) -> str:
    """Generates the Microsoft authorization URL to redirect the user to."""
    # TODO: Implement this function
    auth_url = msal_client.get_authorization_request_url(
        scopes=MS_SCOPES,
        state=state, # Used to prevent CSRF attacks. Should be validated in callback.
        redirect_uri=MS_REDIRECT_URI
    )
    return auth_url

def acquire_ms_token_from_code(auth_code: str, scopes: List[str] = MS_SCOPES) -> Optional[Dict]:
    """Acquires tokens from Microsoft using the authorization code.
       Updates the shared MSAL token cache instance upon success.
    """
    logger.debug(f"Attempting to acquire token with auth code: {auth_code[:10]}...")
    # The result will update the token_cache instance passed to ConfidentialClientApplication
    result = msal_client.acquire_token_by_authorization_code(
        code=auth_code,
        scopes=scopes,
        redirect_uri=MS_REDIRECT_URI # Must match the redirect URI used in the auth request
    )
    
    if "error" in result:
        logger.error(f"Error acquiring token: {result.get('error_description', result)}")
        return None
    
    # TODO: Store the token response securely (e.g., in token_cache_store or database)
    # For now, just log and return it.
    logger.info(f"Successfully acquired token. Access token expires in: {result.get('expires_in')}")
    # Example of accessing user info (requires User.Read scope)
    if result.get('id_token_claims'):
        user_oid = result['id_token_claims'].get('oid') # Object ID
        user_email = result['id_token_claims'].get('preferred_username') # Often email
        logger.info(f"Token acquired for user OID: {user_oid}, Email: {user_email}")
        # Here you would link this OID/email to your internal Zoltar user ID 
        # and store the token cache state using that identifier.

    return result # The cache associated with msal_client is implicitly updated

def get_cached_ms_token(db: Session, ms_oid: str, scopes: List[str] = MS_SCOPES) -> Optional[Dict]:
    """Retrieves cached tokens for a user by ms_oid, attempting refresh if necessary."""
    logger.debug(f"Attempting to get cached token for MS OID: {ms_oid} with scopes: {scopes}")
    user = db.query(models.User).filter(models.User.ms_oid == ms_oid).first()

    if not user:
        logger.warning(f"No user found with MS OID: {ms_oid}")
        return None
    if not user.ms_token_cache:
        logger.warning(f"User {user.email} (OID: {ms_oid}) has no stored MS token cache.")
        return None

    # Load the cache from the database into our shared cache instance
    try:
        token_cache.deserialize(user.ms_token_cache)
    except json.JSONDecodeError:
        logger.error(f"Failed to deserialize token cache for user OID: {ms_oid}. Cache may be corrupt.")
        # Optionally clear the corrupt cache
        # user.ms_token_cache = None
        # db.commit()
        return None

    # Find the specific account associated with this OID in the cache
    accounts = msal_client.get_accounts()
    target_account = None
    for acc in accounts:
        # OID is usually the first part of home_account_id (e.g., OID.TenantID)
        if acc.get("home_account_id") and acc["home_account_id"].startswith(ms_oid):
            target_account = acc
            break

    if not target_account:
        logger.warning(f"No account found in cache for MS OID: {ms_oid}. Cache might be corrupted or for a different user.")
        # It might be prudent to clear the cache here if it's unusable
        # user.ms_token_cache = None
        # db.commit()
        return None

    logger.debug(f"Found account in cache: {target_account.get('username')}")

    # Attempt to acquire token silently (checks cache, refreshes if needed)
    result = msal_client.acquire_token_silent(scopes, account=target_account)

    # Check if the cache was modified (e.g., by a token refresh)
    if token_cache.has_state_changed:
        logger.info(f"MSAL token cache state changed for user OID: {ms_oid}, updating DB.")
        user.ms_token_cache = token_cache.serialize()
        try:
            db.commit()
            logger.debug("Token cache updated in DB.")
        except Exception as e:
            logger.error(f"Failed to update token cache in DB for user OID: {ms_oid} - {e}", exc_info=True)
            db.rollback()
            # Return None or raise? If DB fails, token might be valid but won't be saved.
            # Let's return None for now to indicate failure.
            return None
            
    if not result:
        logger.warning(f"Could not acquire token silently for user OID: {ms_oid}. Re-authentication might be required.")
        # This could happen if refresh token expired or permissions changed.
        return None

    if "error" in result:
        logger.error(f"Error acquiring silent token for user OID: {ms_oid} - {result.get('error_description')}")
        return None

    logger.info(f"Successfully acquired silent token for user OID: {ms_oid}")
    return result

# --- Graph API Client Helper ---
GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"

def call_microsoft_graph_api(
    db: Session, 
    ms_oid: str, 
    scopes: List[str], 
    method: str, 
    endpoint: str, 
    json_data: Optional[Dict] = None,
    params: Optional[Dict] = None, # Add params argument
    headers_extra: Optional[Dict] = None # Add headers_extra
) -> Optional[Dict]:
    """Calls the Microsoft Graph API after obtaining a valid token."""
    token_result = get_cached_ms_token(db=db, ms_oid=ms_oid, scopes=scopes)
    
    if not token_result or not token_result.get("access_token"):
        logger.error(f"Could not obtain Graph API token for user OID {ms_oid} and scopes {scopes}")
        return None
        
    access_token = token_result["access_token"]
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json" # Default content type
    }
    if headers_extra:
        headers.update(headers_extra) # Merge extra headers
    
    url = f"{GRAPH_API_ENDPOINT}{endpoint}"
    logger.debug(f"Calling Graph API: {method} {url} with params {params}")
    
    try:
        # Pass params to requests.request
        response = requests.request(method, url, headers=headers, json=json_data, params=params)
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        
        # Handle cases with no content response (e.g., 204 No Content for DELETE)
        if response.status_code == 204:
            logger.info(f"Graph API call successful ({method} {url}), status code 204 (No Content).")
            return {"status": "success", "status_code": 204}
            
        logger.info(f"Graph API call successful ({method} {url}), status code {response.status_code}.")
        return response.json()
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling Graph API endpoint {endpoint}: {e}", exc_info=True)
        # Log response body if available for more details
        if e.response is not None:
            logger.error(f"Graph API Response Status: {e.response.status_code}")
            try:
                logger.error(f"Graph API Response Body: {e.response.json()}")
            except json.JSONDecodeError:
                logger.error(f"Graph API Response Body: {e.response.text}")
        return None

def get_outlook_calendar_events(
    db: Session,
    ms_oid: str,
    start_time: datetime,
    end_time: datetime
) -> Optional[List[Dict]]:
    """Fetches calendar events from Microsoft Graph /me/calendarview.

    Args:
        db: SQLAlchemy Session.
        ms_oid: The Microsoft Object ID of the user.
        start_time: The start of the time window (timezone-aware recommended).
        end_time: The end of the time window (timezone-aware recommended).

    Returns:
        A list of event dictionaries from the Graph API response, or None on failure.
    """
    logger.info(f"Fetching Outlook calendar events for user OID {ms_oid} from {start_time} to {end_time}")

    # Ensure datetimes are timezone-aware and in UTC ISO format for Graph API
    if start_time.tzinfo is None:
        logger.warning("Start time is timezone-naive. Assuming UTC.")
        start_time = start_time.replace(tzinfo=timezone.utc)
    else:
        start_time = start_time.astimezone(timezone.utc)

    if end_time.tzinfo is None:
        logger.warning("End time is timezone-naive. Assuming UTC.")
        end_time = end_time.replace(tzinfo=timezone.utc)
    else:
        end_time = end_time.astimezone(timezone.utc)
        
    start_str = start_time.isoformat(timespec='seconds')
    end_str = end_time.isoformat(timespec='seconds')

    # Define query parameters for the Graph API
    params = {
        "startDateTime": start_str,
        "endDateTime": end_str,
        "$select": "id,subject,bodyPreview,start,end", # Select only necessary fields
        "$orderby": "start/dateTime asc" # Order by start time
    }

    # Define headers to request UTC timezone for response times
    headers = {
        "Prefer": 'outlook.timezone="UTC"'
    }
    
    # Define required scopes for reading calendar view
    scopes = ["Calendars.Read"]

    # Call the generic Graph API helper
    graph_response = call_microsoft_graph_api(
        db=db,
        ms_oid=ms_oid,
        scopes=scopes,
        method="GET",
        endpoint="/me/calendarview",
        params=params,
        headers_extra=headers
    )

    if graph_response and "value" in graph_response:
        logger.info(f"Successfully retrieved {len(graph_response['value'])} events from Graph API.")
        return graph_response["value"] # Return the list of events
    else:
        logger.error(f"Failed to retrieve calendar events for user OID {ms_oid}. Response: {graph_response}")
        return None

def create_outlook_calendar_event_payload(event_data: schemas.CalendarEventCreate) -> Dict[str, Any]:
    """Creates the payload dictionary for POST /me/events from CalendarEventCreate schema."""
    # Ensure datetimes are in UTC for Graph API
    # The schema validator already ensures they are timezone-aware
    start_utc = event_data.start_datetime.astimezone(timezone.utc)
    end_utc = event_data.end_datetime.astimezone(timezone.utc)
    
    payload = {
        "subject": event_data.subject,
        "body": {
            "contentType": event_data.body_content_type or "Text",
            "content": event_data.body_content or ""
        },
        "start": {
            "dateTime": start_utc.isoformat(timespec='seconds'), # Use 'seconds' precision
            "timeZone": "UTC"
        },
        "end": {
            "dateTime": end_utc.isoformat(timespec='seconds'), # Use 'seconds' precision
            "timeZone": "UTC"
        }
        # Can add other fields like location, attendees later if needed
    }
    return payload

def create_outlook_calendar_update_payload(update_data: schemas.CalendarEventUpdate) -> Dict[str, Any]:
    """Creates the payload dictionary for PATCH /me/events/{id} from CalendarEventUpdate.
    Only includes fields that are not None in the input data.
    """
    payload = {}

    def format_utc_iso_z(dt: datetime) -> str:
        """Formats a timezone-aware datetime to ISO 8601 UTC string with Z suffix."""
        if dt.tzinfo is None:
             # This shouldn't happen due to schema validation, but handle defensively
             logger.warning("Received naive datetime unexpectedly, assuming UTC.")
             dt_utc = dt.replace(tzinfo=timezone.utc)
        else:
             dt_utc = dt.astimezone(timezone.utc)
        iso_str = dt_utc.isoformat(timespec='seconds')
        # Replace +00:00 offset with Z for cleaner UTC representation
        return iso_str.replace("+00:00", "Z")

    if update_data.subject is not None:
        payload["subject"] = update_data.subject

    # Handle body update - requires content
    if update_data.body_content is not None:
        payload["body"] = {
            "content": update_data.body_content,
            # Use provided type, default to Text if content is given but type is not
            "contentType": update_data.body_content_type or "Text" 
        }
    # Note: No need for elif for body_content_type alone, as Graph API requires content.

    # Handle start time update
    if update_data.start_datetime is not None:
        payload["start"] = {
            "dateTime": format_utc_iso_z(update_data.start_datetime),
            "timeZone": "UTC"
        }

    # Handle end time update
    if update_data.end_datetime is not None:
        payload["end"] = {
            "dateTime": format_utc_iso_z(update_data.end_datetime),
            "timeZone": "UTC"
        }
        
    # Note: If adding other updatable fields (e.g., location, attendees), handle them similarly.

    logger.debug(f"Generated PATCH payload: {payload}")
    return payload

# You might also need functions to manage the token_cache_store (save/load)

# logger.info(f"MSAL Helper configured. Client ID: {MS_CLIENT_ID[:5]}... Authority: {MS_AUTHORITY}") 
# Commenting out the final info log as it might interfere with edits 