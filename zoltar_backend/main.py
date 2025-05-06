import logging # Add logging import
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload
from datetime import timedelta, datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler # Import APScheduler
from dateutil.tz import UTC # Import UTC for timezone handling
# Add SessionMiddleware import
# from starlette.middleware.session import SessionMiddleware 
from fastapi.middleware.cors import CORSMiddleware

# Revert to relative imports
from . import crud, models, schemas, auth, push_utils
from .database import SessionLocal, engine, get_db
# Keep router import absolute as it refers to a sub-package
from zoltar_backend.routers import (
    categories, projects, tasks, files, reminders, contacts, reports,
    auth_microsoft, calendar, notes, lists, chat # Added chat router
    # Removed llm_summary
    # Removed chat
)

# Configure basic logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Default persistence frequency if not set on reminder
DEFAULT_REMINDER_FREQUENCY_MINUTES = 15

# --- Comment out if you ran alembic upgrade head --- 
# Otherwise, this creates tables on startup (not recommended with Alembic)
# models.Base.metadata.create_all(bind=engine) 

app = FastAPI(
    title="Zoltar AI Assistant API",
    description="API for managing tasks, projects, reminders, files, and more.",
    version="0.1.0",
    # Add security schemes for Swagger UI
    openapi_tags=[
        {"name": "auth", "description": "Authentication"},
        {"name": "users", "description": "User operations"},
        {"name": "categories", "description": "Manage Categories"},
        {"name": "projects", "description": "Manage Projects"},
        {"name": "tasks", "description": "Manage Tasks"},
        {"name": "files", "description": "Manage Files"},
        {"name": "reminders", "description": "Manage Reminders"},
        {"name": "notes", "description": "Manage Notes"},
        {"name": "lists", "description": "Manage Lists"},
        {"name": "calendar", "description": "Calendar Integration"},
        {"name": "chat", "description": "Chat Interface"},
    ]
)

# Setup CORS
origins = [
    "http://localhost",
    "http://localhost:8080", # Example for a common frontend dev port
    "http://localhost:3000", # Example for React
    "http://localhost:5173", # Example for Vite/Svelte
    "http://localhost:5174", # Alternative Vite dev port
    "http://localhost:5175", # Add the new port
    # Add production frontend origins here later
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Add Session Middleware ---
# TODO: Use a more secure secret key, load from config/env
# app.add_middleware(SessionMiddleware, secret_key="YOUR_SUPER_SECRET_KEY_HERE") 

# --- Scheduler Setup ---
scheduler = AsyncIOScheduler(timezone="UTC") # Use UTC for consistency

def check_due_reminders_job():
    """Job function to check for due reminders and handle persistent reminders."""
    logger.info("Scheduler job: Checking for due reminders...")
    db = SessionLocal() # Create a new session for the job
    now_utc = datetime.now(timezone.utc)
    # Eager load owner relationship to get user object easily
    reminders_to_check = db.query(models.Reminder).options(
        joinedload(models.Reminder.owner)
    ).filter(
        models.Reminder.is_active == True,
        models.Reminder.trigger_datetime <= now_utc,
        (models.Reminder.snoozed_until == None) | (models.Reminder.snoozed_until <= now_utc)
    ).all()

    reminders_to_notify = []

    # Initial check for reminders that just became due
    for reminder in reminders_to_check:
        if reminder.last_notified_at is None or reminder.last_notified_at < reminder.trigger_datetime:
            reminders_to_notify.append(reminder)

    # Check for persistent reminders needing re-notification
    for reminder in reminders_to_check: # Iterate through already fetched reminders
        if reminder.remind_frequency_minutes is not None and reminder.last_notified_at is not None:
             # Check if frequency has elapsed since last notification
            last_notified_aware = reminder.last_notified_at.astimezone(UTC) # Ensure timezone aware
            frequency_delta = timedelta(minutes=reminder.remind_frequency_minutes)
            if last_notified_aware + frequency_delta <= now_utc:
                 if reminder not in reminders_to_notify: # Avoid duplicates
                    logger.info(f"  Adding reminder ID={reminder.id} for persistent notification.")
                    reminders_to_notify.append(reminder)

    if not reminders_to_notify:
        logger.info("Scheduler job: No reminders due for notification.")
    else:
        logger.info(f"Scheduler job: Found {len(reminders_to_notify)} unique reminders for notification.")
        for reminder in reminders_to_notify:
            # --- Prepare and Send Push Notification --- 
            owner = reminder.owner # Access eagerly loaded owner
            if owner and owner.device_token:
                alert_body = reminder.description or reminder.title or "Your Zoltar reminder is due!"
                # Prepare custom data (optional)
                custom_data = {
                    "reminder_id": reminder.id
                    # Add other relevant info for the app, e.g., deep link
                    # "deep_link": f"zoltar://reminders/{reminder.id}"
                }
                
                # Send the notification via push_utils
                success = push_utils.send_apns_notification(
                    device_token=owner.device_token,
                    alert_body=alert_body,
                    custom_data=custom_data
                    # badge_count can be managed client-side or calculated server-side if needed
                )
                if not success:
                    logger.error(f"Failed to send push notification for reminder ID={reminder.id} to user ID={owner.id}")
                else:
                     logger.info(f"Push notification sent successfully for reminder ID={reminder.id}")
            else:
                logger.warning(f"Cannot send push notification for reminder ID={reminder.id}: Owner or device token missing.")
            # --- End Push Notification --- 

            # Log TRIGGERED event (as before)
            trigger_event = models.ReminderEvent(
                reminder_id=reminder.id,
                expected_trigger_time=reminder.trigger_datetime, 
                action_time=now_utc,
                action_type=models.ReminderActionType.TRIGGERED
            )
            db.add(trigger_event)

            # Update last_notified_at on the reminder (as before)
            reminder.last_notified_at = now_utc
            db.add(reminder)

            # Original logging (keep for now)
            logger.info(f"NOTIFYING (Internal Log): ID={reminder.id}, Title='{reminder.title}', Due='{reminder.trigger_datetime}', LastNotified='{reminder.last_notified_at}'")
        
        db.commit() # Commit all events and updates

    db.close() # Close session

@app.on_event("startup")
async def startup_event():
    logger.info("Starting scheduler...")
    # Add the job to the scheduler to run every 60 seconds
    scheduler.add_job(check_due_reminders_job, 'interval', seconds=60, id="check_reminders")
    scheduler.start()
    logger.info("Scheduler started.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down scheduler...")
    scheduler.shutdown()
    logger.info("Scheduler shut down.")

# --- End Scheduler Setup ---

# Include routers
# app.include_router(auth.router) # Remove this line as auth routes are likely in main.py
app.include_router(categories.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(files.router)
app.include_router(reminders.router)
app.include_router(contacts.router)
app.include_router(reports.router)
app.include_router(auth_microsoft.router)
app.include_router(calendar.router)
app.include_router(notes.router)
app.include_router(lists.router)
app.include_router(chat.router) # Added chat router

# --- Add other routers here as they are created --- 

@app.post("/token", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, email=form_data.username) # Use email as username
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/users/", response_model=schemas.User)
def create_user_endpoint(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db=db, user=user)


@app.get("/", tags=["root"])
async def read_root():
    return {"message": "Welcome to Zoltar"}

# --- Added protected endpoint example --- 
@app.get("/users/me", response_model=schemas.User)
async def read_users_me(current_user: models.User = Depends(auth.get_current_active_user)):
    """Returns the details of the currently authenticated user."""
    return current_user
# --- End Added ---

# --- Add protected endpoint example later ---
# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
#
# @app.get("/users/me", response_model=schemas.User)
# async def read_users_me(token: str = Depends(oauth2_scheme)):
#     # Need to implement token decoding and user lookup here
#     # using auth.py functions
#     pass 

# --- Endpoint to register device token ---
@app.post("/users/me/device_token", status_code=status.HTTP_204_NO_CONTENT, tags=["users"])
async def register_device_token(
    token_data: schemas.UserDeviceTokenUpdate, # Use the schema for the request body
    current_user: models.User = Depends(auth.get_current_active_user), # Get authenticated user
    db: Session = Depends(get_db)
):
    """
    Registers or updates the device token for push notifications
    for the currently authenticated user.
    """
    logger.info(f"Received request to update device token for user {current_user.id} ({current_user.email})")
    updated_user = crud.update_user_device_token(
        db=db,
        user_id=current_user.id,
        device_token=token_data.device_token
    )
    if not updated_user:
        # This should technically not happen if get_current_active_user works,
        # but good practice to handle potential issues.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )
    logger.info(f"Successfully updated device token for user {current_user.id}")
    # No response body needed, return 204 No Content
    return 