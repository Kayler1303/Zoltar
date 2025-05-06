import os
import uuid
import msal
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import logging
from typing import Optional, Dict

# Change to direct imports
import crud
import models
import schemas
import auth
from database import get_db

# Import the utility functions directly
import auth_utils_ms 

logger = logging.getLogger(__name__)

# TODO: Load these securely from environment variables or config
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID", "YOUR_MS_CLIENT_ID_HERE")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET", "YOUR_MS_CLIENT_SECRET_HERE")
# Make sure the redirect URI matches *exactly* what's in Azure AD
MS_REDIRECT_URI = "http://localhost:8000/auth/microsoft/callback"
MS_SCOPES = ["User.Read", "Calendars.ReadWrite"] # Base scopes, offline_access added automatically by MSAL for confidential client flow
MS_AUTHORITY = "https://login.microsoftonline.com/common" # For multi-tenant + personal

router = APIRouter(
    prefix="/auth/microsoft",
    tags=["Auth - Microsoft"], # Add tags for OpenAPI docs
    responses={404: {"description": "Not found"}},
)

# Store state temporarily (replace with more robust method, e.g., session)
# WARNING: Simple global state is NOT suitable for multi-user/production!
# For demo purposes only.
temp_state_store = {}

# Helper function to build MSAL confidential client application
def _build_msal_app(authority=MS_AUTHORITY):
    return msal.ConfidentialClientApplication(
        MS_CLIENT_ID,
        authority=authority,
        client_credential=MS_CLIENT_SECRET,
    )

@router.get("/login")
async def login_microsoft(request: Request):
    """Initiates the Microsoft OAuth2 login flow."""
    # logger.info("Microsoft login endpoint called")
    # return {"message": "Microsoft login endpoint placeholder"}
    
    # Generate a unique state value for CSRF protection
    state = str(uuid.uuid4())
    # Store the state temporarily to validate it on callback
    # This needs a better storage mechanism (e.g., session, database)
    # keyed potentially by browser session ID if not user ID yet
    # temp_state_store[state] = True # Or store user context if available
    # For now, we might just log it or skip validation for simplicity 
    logger.info(f"Generated state for login: {state}") 
    
    auth_url = auth_utils_ms.get_ms_auth_url(state=state)
    logger.info(f"Redirecting user to Microsoft login: {auth_url}")
    return RedirectResponse(auth_url)

@router.get("/callback")
async def callback_microsoft(request: Request, db: Session = Depends(get_db), code: str = None, state: str = None, error: str = None, error_description: str = None):
    """Handles the redirect callback from Microsoft after authentication."""
    logger.info(f"Microsoft callback endpoint called. State: {state}, Code provided: {code is not None}, Error: {error}")
    # logger.info(f"Full request query params: {request.query_params}")
    # return {"message": "Microsoft callback endpoint placeholder", "code": code, "state": state}
    
    # 1. Handle potential errors from Microsoft
    if error:
        logger.error(f"Microsoft login error: {error} - {error_description}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Microsoft login failed: {error_description or error}"
        )
        
    # 2. Validate state (basic check - needs improvement)
    # stored_state = temp_state_store.pop(state, None)
    # if not stored_state:
    #     logger.error(f"Invalid or expired state received: {state}")
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter.")
    # logger.info(f"State validation passed for: {state}")

    # 3. Check if authorization code is present
    if not code:
         logger.error("Authorization code missing in callback.")
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Authorization code missing.")
         
    # 4. Exchange code for tokens (this also populates auth_utils_ms.token_cache)
    token_result = auth_utils_ms.acquire_ms_token_from_code(auth_code=code)
    
    if not token_result:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to acquire token from Microsoft.")

    # 5. Process/Store token: Link to user and save cache
    id_claims = token_result.get("id_token_claims", {})
    ms_oid = id_claims.get("oid")
    email = id_claims.get("preferred_username") # Or other claim like 'email' if preferred_username isn't reliable

    if not ms_oid or not email:
        logger.error("Could not extract OID or email from token claims.", extra={"claims": id_claims})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not identify user from Microsoft token.")

    # Find Zoltar user by email
    user = db.query(models.User).filter(models.User.email == email).first()

    if not user:
        logger.warning(f"Received successful Microsoft login for email {email} (OID: {ms_oid}), but no matching Zoltar user found.")
        # In a real app, you might redirect to a page explaining this,
        # or allow on-the-fly user creation/linking if the user was already logged into Zoltar.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No Zoltar user account found for email {email}. Please register first or ensure emails match.")

    logger.info(f"Linking Microsoft account (OID: {ms_oid}) to Zoltar user: {user.email} (ID: {user.id})")
    
    # Update user's OID (if needed) and token cache
    user.ms_oid = ms_oid
    user.ms_token_cache = auth_utils_ms.token_cache.serialize() # Get serialized cache from the shared instance
    
    try:
        db.commit()
        logger.info(f"Successfully saved token cache and OID for user {user.email}")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error saving token cache/OID for user {user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save authentication details.")

    # Return a simple success message or redirect to a frontend page
    return {"message": f"Successfully linked Microsoft account for {email}. You can now close this window."}
    # Old verbose response:
    # return { 
    #     "message": "Microsoft login successful (development only - token details below)",
    #     "access_token_preview": token_result.get("access_token")[:10] + "...", # Don't expose full token
    #     "refresh_token_provided": "refresh_token" in token_result,
    #     "expires_in": token_result.get("expires_in"),
    #     "id_token_claims": token_result.get("id_token_claims", {}) # Contains user info (oid, preferred_username, etc.)
    # } 

@router.get("/me", response_model=Optional[Dict]) # Use Dict for arbitrary JSON response from Graph
async def get_microsoft_me(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user) # Use Zoltar's auth
):
    """Fetches the profile of the linked Microsoft account using the Graph API (/me endpoint).
       Requires the user to be logged into Zoltar and to have previously linked their Microsoft account.
    """
    logger.info(f"Request received for /auth/microsoft/me by Zoltar user: {current_user.email}")
    
    if not current_user.ms_oid:
        logger.warning(f"User {current_user.email} tried to access /me but has no linked Microsoft OID.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Microsoft account not linked. Please use the /auth/microsoft/login flow first."
        )
        
    logger.debug(f"Fetching /me data for MS OID: {current_user.ms_oid}")
    
    # Define the required scopes for the /me endpoint
    required_scopes = ["User.Read"]
    
    graph_data = auth_utils_ms.call_microsoft_graph_api(
        db=db,
        ms_oid=current_user.ms_oid,
        scopes=required_scopes,
        method="GET",
        endpoint="/me"
    )
    
    if graph_data is None:
        logger.error(f"Failed to retrieve /me data from Graph API for user {current_user.email} (OID: {current_user.ms_oid})")
        # The error is already logged in call_microsoft_graph_api
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="Could not retrieve data from Microsoft Graph API. Check logs for details."
        )
        
    logger.info(f"Successfully retrieved /me data for user {current_user.email}")
    return graph_data 