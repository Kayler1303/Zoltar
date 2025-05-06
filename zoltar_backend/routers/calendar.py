from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import logging
from typing import Dict, Optional, List
import datetime # Need datetime for duration calculation

# Zoltar imports
import crud
import models
import schemas
import auth
import auth_utils_ms # Assuming this is also now at the /app level
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/calendar",
    tags=["Calendar Integration"],
    dependencies=[Depends(auth.get_current_active_user)], # Require Zoltar auth for all endpoints here
    responses={
        404: {"description": "Not found"},
        400: {"description": "Bad Request (e.g., MS account not linked)"},
        503: {"description": "Microsoft Graph API unavailable or error"}
    },
)

# Define required scopes for calendar operations
CALENDAR_READ_SCOPES = ["Calendars.Read"]
CALENDAR_WRITE_SCOPES = ["Calendars.ReadWrite"]

# --- Endpoint implementations will go here ---

@router.get("/test") # Simple test endpoint to check router setup
async def test_calendar_router(current_user: models.User = Depends(auth.get_current_active_user)):
    logger.info(f"Calendar test endpoint accessed by {current_user.email}")
    return {"message": "Calendar router is active", "user": current_user.email}

@router.post("/reminders/{reminder_id}", status_code=status.HTTP_201_CREATED)
async def sync_reminder_to_calendar(
    reminder_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
) -> Dict:
    """Creates a Microsoft Calendar event corresponding to a Zoltar Reminder."""
    logger.info(f"Request to sync reminder ID {reminder_id} to calendar for user {current_user.email}")

    # 1. Check if MS account is linked
    if not current_user.ms_oid:
        logger.warning(f"User {current_user.email} tried to sync reminder but has no linked Microsoft OID.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Microsoft account not linked. Please use the /auth/microsoft/login flow first."
        )

    # 2. Get the reminder from Zoltar DB
    reminder = crud.get_reminder(db=db, reminder_id=reminder_id)
    if reminder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Reminder with ID {reminder_id} not found.")
    
    # Check ownership
    if reminder.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this reminder.")
        
    # 3. Validate reminder data needed for calendar event
    if not reminder.trigger_datetime:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reminder must have a trigger_datetime to be synced to calendar.")
        
    if not reminder.title:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reminder must have a title to be synced to calendar.")

    # Ensure trigger_datetime is timezone-aware (should be UTC from DB)
    start_time = reminder.trigger_datetime
    if start_time.tzinfo is None:
        # This shouldn't happen if data is saved correctly, but handle defensively
        logger.warning(f"Reminder {reminder_id} trigger_datetime is timezone-naive. Assuming UTC.")
        start_time = start_time.replace(tzinfo=datetime.timezone.utc)
    else:
        # Convert to UTC just in case it was stored with a different offset
        start_time = start_time.astimezone(datetime.timezone.utc)
        
    # Set default duration (e.g., 15 minutes)
    end_time = start_time + datetime.timedelta(minutes=15)

    # 4. Format data for Microsoft Graph API event
    # https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0
    event_data = {
        "subject": reminder.title,
        "body": {
            "contentType": "Text", # Or "HTML"
            "content": reminder.description or ""
        },
        "start": {
            "dateTime": start_time.isoformat(),
            "timeZone": "UTC" # Specify timezone
        },
        "end": {
            "dateTime": end_time.isoformat(),
            "timeZone": "UTC" # Specify timezone
        },
        # Optional: Add a link back to the Zoltar reminder?
        # "webLink": f"http://your-zoltar-instance/reminders/{reminder_id}", 
        # Optional: Add reminder settings for the calendar event itself?
        # "isReminderOn": True,
        # "reminderMinutesBeforeStart": 15 
    }

    # 5. Call Graph API to create the event
    logger.debug(f"Calling Graph API to create event for reminder {reminder_id}")
    graph_result = auth_utils_ms.call_microsoft_graph_api(
        db=db,
        ms_oid=current_user.ms_oid,
        scopes=CALENDAR_WRITE_SCOPES, # Use write scopes
        method="POST",
        endpoint="/me/events",
        json_data=event_data
    )

    if graph_result is None:
        logger.error(f"Failed to create calendar event via Graph API for reminder {reminder_id}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not create calendar event via Microsoft Graph API. Check logs."
        )

    logger.info(f"Successfully created calendar event for reminder {reminder_id}. Graph Event ID: {graph_result.get('id')}")
    
    # Return the created event details from Graph API
    return graph_result 

@router.get("/agenda", response_model=List[schemas.CalendarEvent])
async def read_calendar_agenda(
    *,
    start_time: datetime.datetime = Query(..., description="Start time for the agenda query (ISO 8601 format)."),
    end_time: datetime.datetime = Query(..., description="End time for the agenda query (ISO 8601 format)."),
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db) # Inject DB session
):
    """
    Retrieve calendar events (agenda) for the authenticated user within a specified time range.

    Connects to the user's linked Outlook calendar via Microsoft Graph.
    """
    logger.info(f"Fetching agenda for user {current_user.email} from {start_time} to {end_time}")

    # 1. Check if MS account is linked
    if not current_user.ms_oid:
        logger.warning(f"User {current_user.email} tried to read agenda but has no linked Microsoft OID.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Microsoft account not linked. Cannot fetch calendar agenda."
        )

    # 2. Call the helper function to get events from Graph API
    raw_events = auth_utils_ms.get_outlook_calendar_events(
        db=db,
        ms_oid=current_user.ms_oid,
        start_time=start_time,
        end_time=end_time
    )

    # 3. Handle failure from the Graph API call
    if raw_events is None:
        logger.error(f"Failed to retrieve calendar events from Graph for user {current_user.email} (OID: {current_user.ms_oid}).")
        # Return 503 Service Unavailable as the external service failed
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not retrieve calendar events from Microsoft Graph."
        )
        
    # 4. Process the raw events and map to the response schema
    calendar_events: List[schemas.CalendarEvent] = []
    for event_data in raw_events:
        try:
            # Extract required fields - MS Graph returns start/end as dicts
            start_dt_str = event_data.get('start', {}).get('dateTime')
            end_dt_str = event_data.get('end', {}).get('dateTime')
            
            # Let Pydantic handle parsing ISO strings with timezone (should be UTC)
            parsed_event = schemas.CalendarEvent(
                id=event_data.get('id'),
                subject=event_data.get('subject'),
                body_preview=event_data.get('bodyPreview'),
                start_datetime=start_dt_str, # Pass the string directly
                end_datetime=end_dt_str      # Pass the string directly
            )
            calendar_events.append(parsed_event)
        except Exception as e: # Catch potential validation errors or missing keys
            event_id = event_data.get('id', 'unknown')
            logger.warning(f"Skipping event ID {event_id} due to processing error: {e}", exc_info=False) # Log less verbosely
            continue # Skip this event if parsing fails

    logger.info(f"Successfully processed {len(calendar_events)} events for user {current_user.email}")
    return calendar_events

@router.post("/events", response_model=schemas.CalendarEvent, status_code=status.HTTP_201_CREATED)
async def create_calendar_event(
    event: schemas.CalendarEventCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Creates a new event directly in the user's linked Microsoft Calendar."""
    logger.info(f"Received request to create calendar event: '{event.subject}' for user {current_user.email}")
    
    # 1. Check if user has ms_oid
    if not current_user.ms_oid:
        logger.warning(f"User {current_user.email} tried to create calendar event but has no linked Microsoft OID.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Microsoft account not linked. Cannot create calendar event."
        )

    # 2. Create Graph API payload using helper (Sub-task 26.3)
    try:
        payload = auth_utils_ms.create_outlook_calendar_event_payload(event_data=event)
    except Exception as e:
        # Catch potential errors during payload creation (e.g., datetime issues missed by validator?)
        logger.error(f"Error creating Graph API payload for event '{event.subject}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error processing event data: {e}")

    # 3. Call Graph API POST /me/events using auth_utils_ms.call_microsoft_graph_api
    logger.debug(f"Calling Graph API to create event for user {current_user.email}")
    graph_response = auth_utils_ms.call_microsoft_graph_api(
        db=db,
        ms_oid=current_user.ms_oid,
        scopes=CALENDAR_WRITE_SCOPES, # Ensure correct scopes are used
        method="POST",
        endpoint="/me/events",
        json_data=payload
    )

    # 4. Handle Graph API errors (returns None)
    if graph_response is None:
        logger.error(f"Failed to create calendar event '{event.subject}' via Graph API for user {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not create calendar event via Microsoft Graph API. Check logs."
        )

    # 5. Parse successful Graph API response (Sub-task 26.5)
    # 6. Map response to schemas.CalendarEvent and return (Sub-task 26.5)
    try:
        # Extract the necessary fields from the Graph API response
        # The response typically includes the created event details
        start_info = graph_response.get("start", {})
        end_info = graph_response.get("end", {})
        
        # Create the CalendarEvent response object using the data from Graph API
        # Pydantic will validate and parse the datetime strings
        created_event_response = schemas.CalendarEvent(
            id=graph_response["id"], # ID is expected to be present on success
            subject=graph_response.get("subject"),
            body_preview=graph_response.get("bodyPreview"), # Use bodyPreview for consistency
            start_datetime=start_info.get("dateTime"),
            end_datetime=end_info.get("dateTime")
        )
        
        logger.info(f"Successfully created and parsed calendar event ID: {created_event_response.id}")
        return created_event_response
        
    except KeyError as e:
        # Handle cases where the Graph API response is missing expected keys
        logger.error(f"Graph API response missing expected key: {e}. Response: {graph_response}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, # Indicate error communicating with upstream server
            detail=f"Received unexpected response format from Microsoft Graph API after creating event."
        )
    except Exception as e: # Catch potential Pydantic validation errors or other issues
        logger.error(f"Error parsing Graph API response: {e}. Response: {graph_response}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process response from Microsoft Graph API after creating event."
        )

    # logger.info(f"Successfully created calendar event '{event.subject}' via Graph. Raw response: {graph_response.get('id')}") # Log ID
    # # For now, just return a placeholder until parsing is done
    # # This will fail validation until Sub-task 26.5 is done
    # return {
    #     "id": graph_response.get("id", "UNKNOWN_ID"),
    #     "subject": graph_response.get("subject", event.subject),
    #     "body_preview": graph_response.get("bodyPreview", event.body_content or ""),
    #     "start_datetime": graph_response.get("start", {}).get("dateTime", event.start_datetime.isoformat()),
    #     "end_datetime": graph_response.get("end", {}).get("dateTime", event.end_datetime.isoformat())
    # }
    # # raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Event parsing not yet implemented.")

@router.patch("/events/{event_id}", response_model=schemas.CalendarEvent, status_code=status.HTTP_200_OK)
async def update_calendar_event(
    event_id: str,
    update_data: schemas.CalendarEventUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Updates an existing event in the user's linked Microsoft Calendar."""
    logger.info(f"Received request to update calendar event ID: {event_id} for user {current_user.email}")

    # 1. Check if user has ms_oid
    if not current_user.ms_oid:
        logger.warning(f"User {current_user.email} tried to update calendar event but has no linked Microsoft OID.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Microsoft account not linked. Cannot update calendar event."
        )
        
    # Prevent sending empty updates
    if update_data.model_dump(exclude_unset=True) == {}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update data provided."
        )

    # 2. Create Graph API PATCH payload using helper (Sub-task 27.3)
    try:
        payload = auth_utils_ms.create_outlook_calendar_update_payload(update_data=update_data)
    except Exception as e:
        logger.error(f"Error creating Graph API PATCH payload for event {event_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error processing update data: {e}")

    # 3. Call Graph API PATCH /me/events/{event_id}
    logger.debug(f"Calling Graph API PATCH for event {event_id} for user {current_user.email}")
    graph_endpoint = f"/me/events/{event_id}"
    graph_response = auth_utils_ms.call_microsoft_graph_api(
        db=db,
        ms_oid=current_user.ms_oid,
        scopes=CALENDAR_WRITE_SCOPES, # Use write scopes
        method="PATCH",
        endpoint=graph_endpoint,
        json_data=payload
    )

    # 4. Handle Graph API errors (returns None)
    # Note: The helper currently returns None for all errors, including 404 Not Found.
    # A more specific error handling might involve catching HTTPError here or modifying the helper.
    if graph_response is None:
        # Could be 404 Not Found, 401/403, 5xx, or other connection issue.
        logger.error(f"Graph API call failed for PATCH {graph_endpoint} for user {current_user.email}")
        # Returning 503 is a general "upstream service failed" indicator.
        # If distinguishing 404 is critical, further refinement is needed.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, # Or potentially 404 if we could detect it
            detail=f"Could not update calendar event via Microsoft Graph API (it might not exist or an error occurred). Check logs."
        )

    # 5. Parse successful Graph API response (Sub-task 27.5)
    # 6. Map response to schemas.CalendarEvent and return (Sub-task 27.5)
    try:
        # Extract fields from the updated event returned by Graph API
        start_info = graph_response.get("start", {})
        end_info = graph_response.get("end", {})
        
        # Create the response object using the potentially updated data
        updated_event_response = schemas.CalendarEvent(
            id=graph_response["id"], # ID should always be present
            subject=graph_response.get("subject"),
            body_preview=graph_response.get("bodyPreview"),
            start_datetime=start_info.get("dateTime"),
            end_datetime=end_info.get("dateTime")
        )
        
        logger.info(f"Successfully updated and parsed calendar event ID: {updated_event_response.id}")
        return updated_event_response

    except KeyError as e:
        logger.error(f"Graph API PATCH response missing expected key: {e}. Response: {graph_response}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Received unexpected response format from Microsoft Graph API after updating event."
        )
    except Exception as e:
        logger.error(f"Error parsing Graph API PATCH response: {e}. Response: {graph_response}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process response from Microsoft Graph API after updating event."
        )

    # logger.info(f"Successfully updated calendar event {event_id} via Graph.")
    # # PATCH usually returns the updated object
    # # Temporary placeholder until parsing is implemented
    # return {
    #     "id": graph_response.get("id", event_id),
    #     "subject": graph_response.get("subject", "UNKNOWN"),
    #     "body_preview": graph_response.get("bodyPreview", ""),
    #     "start_datetime": graph_response.get("start", {}).get("dateTime", datetime.datetime.now(datetime.timezone.utc).isoformat()),
    #     "end_datetime": graph_response.get("end", {}).get("dateTime", datetime.datetime.now(datetime.timezone.utc).isoformat())
    # }
    # # raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Event update response parsing not yet implemented.")

# Add other calendar endpoints (delete?) later as needed 