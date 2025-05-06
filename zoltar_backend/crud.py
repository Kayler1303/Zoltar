from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timezone, timedelta # Need datetime for completed_at
from typing import Optional, List, Union, Tuple, Dict, Any # Import Optional, List, and Union

# Import for recurrence rule validation and calculation
from dateutil.rrule import rrulestr, rrule
from dateutil.tz import UTC # Import UTC for timezone awareness

# Change relative imports to absolute imports
from zoltar_backend import models, schemas, auth

from sqlalchemy import func, or_, and_ # Import func for count, or_ for combining filters
import sqlalchemy.orm # Import orm for joinedload
import logging

# Set up logging
logger = logging.getLogger(__name__)

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(email=user.email, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# --- Category CRUD Functions ---

def get_category(db: Session, category_id: int):
    return db.query(models.Category).filter(models.Category.id == category_id).first()

def get_user_categories(db: Session, user_id: int, skip: int = 0, limit: int = 100):
    return db.query(models.Category).filter(models.Category.owner_id == user_id).offset(skip).limit(limit).all()

def create_user_category(db: Session, category: schemas.CategoryCreate, user_id: int):
    db_category = models.Category(**category.model_dump(), owner_id=user_id)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category

def delete_category(db: Session, category_id: int, user_id: int):
    db_category = db.query(models.Category).filter(models.Category.id == category_id, models.Category.owner_id == user_id).first()
    if db_category:
        db.delete(db_category)
        db.commit()
        return True
    return False

# --- Project CRUD Functions ---

def get_project(db: Session, project_id: int):
    return db.query(models.Project).filter(models.Project.id == project_id).first()

def get_user_projects(db: Session, user_id: int, skip: int = 0, limit: int = 100):
    return db.query(models.Project).filter(models.Project.owner_id == user_id).offset(skip).limit(limit).all()

def create_user_project(db: Session, project: schemas.ProjectCreate, user_id: int):
    # Validate category if provided
    if project.category_id is not None:
        category = get_category(db, project.category_id)
        if not category or category.owner_id != user_id:
            return None # Indicate invalid category

    db_project = models.Project(**project.model_dump(), owner_id=user_id)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

def update_project(db: Session, project_id: int, project_update: schemas.ProjectUpdate, user_id: int):
    """Updates a project and checks/updates status of dependent projects if this one is completed.
    
    Returns:
        A dictionary containing the updated project and a list of unblocked dependent projects, 
        or None if project not found, or 'invalid_category' if category invalid.
    """
    db_project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.owner_id == user_id).first()
    if not db_project:
        return None # Project not found or not owned by user

    update_data = project_update.model_dump(exclude_unset=True)

    # Validate category if it's being changed
    if 'category_id' in update_data and update_data['category_id'] is not None:
        category = get_category(db, update_data['category_id'])
        if not category or category.owner_id != user_id:
            return "invalid_category" # Specific signal for invalid category during update

    original_status = db_project.status # Store original status

    project_completed = False # Flag if status changed to COMPLETED
    if 'status' in update_data:
        if update_data['status'] == models.ProjectStatus.COMPLETED and original_status != models.ProjectStatus.COMPLETED:
            project_completed = True
    
    # Apply updates from project_update
    for key, value in update_data.items():
        setattr(db_project, key, value)

    # Commit the primary project update *first*
    db.add(db_project)
    db.commit()
    db.refresh(db_project)

    unblocked_projects = [] # List to store projects that were unblocked
    # --- Check Status of Projects Dependent on This One --- 
    if project_completed:
        # Query dependent projects using the relationship (more efficient)
        # Note: ensure relationship is loaded or handle potential SELECT N+1 if large numbers
        # For moderate numbers, this is fine.
        projects_dependent_on_this = db_project.dependent_projects # Uses backref
        
        print(f"Project {project_id} completed. Checking status for {len(projects_dependent_on_this)} dependent projects.") # Debug
        for dependent_project in projects_dependent_on_this:
            was_unblocked = check_and_update_project_status(db, dependent_project)
            if was_unblocked:
                unblocked_projects.append(dependent_project)
            # Helper no longer commits
            
        # Commit changes to dependent projects' status if any were made
        # (check_and_update... adds to session if status changed)
        if len(unblocked_projects) > 0 or any(p in db.dirty for p in projects_dependent_on_this):
             # Check db.dirty as status might have changed TO ON_HOLD, not just unblocked
             print(f"Committing status updates for dependent projects of {project_id}.") # Debug
             db.commit()
        else:
             print(f"No status changes to commit for dependents of project {project_id}.") # Debug

    # Refresh the primary project again in case its dependent relationships were touched indirectly?
    # Usually not necessary unless complex triggers exist, but safe.
    db.refresh(db_project)
    
    # Refresh unblocked projects to get their latest state after commit
    for proj in unblocked_projects:
        try:
            db.refresh(proj)
        except Exception as e:
            print(f"Error refreshing unblocked project {proj.id}: {e}")
            # Handle case where project might have been deleted concurrently? Unlikely.
            pass

    return {"updated_project": db_project, "unblocked_projects": unblocked_projects}

def delete_project(db: Session, project_id: int, user_id: int):
    db_project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.owner_id == user_id).first()
    if db_project:
        db.delete(db_project)
        db.commit()
        return True
    return False

# --- Task CRUD Functions ---

def get_task(db: Session, task_id: int):
    return db.query(models.Task).filter(models.Task.id == task_id).first()

def get_user_tasks(db: Session, user_id: int, skip: int = 0, limit: int = 100):
    # Add filtering/sorting later (e.g., by project, status, due_date)
    return db.query(models.Task).filter(models.Task.owner_id == user_id).offset(skip).limit(limit).all()

def create_user_task(db: Session, task: schemas.TaskCreate, owner_id: int):
    # Validate project if provided
    if task.project_id is not None:
        project = get_project(db, task.project_id)
        # Ensure project belongs to the *same user* trying to create the task
        if not project or project.owner_id != owner_id: # Check against owner_id
            return "invalid_project" # Return error code

    # Validate contact if provided
    if task.contact_id is not None:
        contact = get_contact(db, task.contact_id, owner_id) # Pass owner_id
        if not contact: # get_contact already checks ownership
            return "invalid_contact" # Return error code

    # Prepare data, excluding completed_at initially
    task_data = task.model_dump()
    if 'completed_at' in task_data: # Ensure completed_at isn't set via create schema
        del task_data['completed_at']

    # owner_id is already available as a parameter, no need to pass in **task_data
    db_task = models.Task(**task_data, owner_id=owner_id)

    # Set completed_at if status is COMPLETED on creation (unlikely but possible)
    if db_task.status == models.TaskStatus.COMPLETED:
        db_task.completed_at = datetime.now(timezone.utc)

    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task # Return the created task object on success

def update_task(db: Session, task_id: int, task_update: schemas.TaskUpdate, user_id: int):
    """Updates a task, triggers relative reminders, and checks/updates status of dependent tasks if this one is completed.
    
    Returns:
        A dictionary containing the updated task and a list of unblocked dependent tasks, 
        or None if task not found, or a string error code ('invalid_project', 'invalid_contact').
    """
    db_task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.owner_id == user_id).first()
    if not db_task:
        return None # Task not found or not owned by user

    update_data = task_update.model_dump(exclude_unset=True)
    original_status = db_task.status # Store original status

    # Validate project if it's being changed
    if 'project_id' in update_data and update_data['project_id'] is not None:
        project = get_project(db, update_data['project_id'])
        if not project or project.owner_id != user_id:
            return "invalid_project" # Specific signal for invalid project
    
    # Validate contact if it's being changed
    if 'contact_id' in update_data and update_data['contact_id'] is not None:
        contact = get_contact(db, update_data['contact_id'], user_id)
        if not contact:
            return "invalid_contact"

    task_completed_time = None # Variable to store completion time
    task_was_completed = False # Flag if status changed to COMPLETED

    # Handle completed_at based on status change
    if 'status' in update_data:
        new_status = update_data['status']
        if new_status == models.TaskStatus.COMPLETED and original_status != models.TaskStatus.COMPLETED:
            task_completed_time = datetime.now(timezone.utc)
            update_data['completed_at'] = task_completed_time
            task_was_completed = True
        elif new_status != models.TaskStatus.COMPLETED and original_status == models.TaskStatus.COMPLETED:
            update_data['completed_at'] = None # Nullify if moving away from completed

    # Apply updates from task_update
    for key, value in update_data.items():
        setattr(db_task, key, value)

    # Commit the primary task update *first*
    db.add(db_task)
    db.commit()
    db.refresh(db_task) 

    unblocked_tasks = [] # List to store tasks that were unblocked
    relative_reminders_updated = False
    # --- Trigger Relative Reminders --- 
    if task_was_completed: 
        relative_reminders = db.query(models.Reminder).filter(
            models.Reminder.relative_to_task_completion_id == task_id,
            models.Reminder.reminder_type == models.ReminderType.RECURRING_RELATIVE,
            models.Reminder.is_active == True
        ).all()
        for reminder in relative_reminders:
            delay_minutes = reminder.relative_delay_minutes or 0
            reminder.trigger_datetime = task_completed_time + timedelta(minutes=delay_minutes)
            # We just set the trigger time; the scheduler will pick it up when due.
            # Ensure last_notified_at is cleared if it was somehow set?
            reminder.last_notified_at = None # Reset notification status
            db.add(reminder) 
            relative_reminders_updated = True
        # No commit here yet

    # --- Check Status of Tasks Dependent on This One --- 
    if task_was_completed:
        # Use the relationship defined in models.py
        tasks_dependent_on_this = db_task.dependent_tasks # Uses backref

        print(f"Task {task_id} completed. Checking status for {len(tasks_dependent_on_this)} dependent tasks.") # Debug
        for dependent_task in tasks_dependent_on_this:
            was_unblocked = check_and_update_task_status(db, dependent_task)
            if was_unblocked:
                unblocked_tasks.append(dependent_task)
            # Helper no longer commits

    # Commit changes to dependent tasks' status AND relative reminders together
    if task_was_completed and (len(unblocked_tasks) > 0 or relative_reminders_updated or any(t in db.dirty for t in tasks_dependent_on_this)):
        # Check db.dirty as status might have changed TO BLOCKED, not just unblocked
        print(f"Committing status/reminder updates triggered by completion of task {task_id}.") # Debug
        db.commit()
    else:
        print(f"No dependent status/reminder changes to commit for task {task_id}.") # Debug

    # Refresh objects after final commit if needed
    db.refresh(db_task) # Refresh primary task again
    if relative_reminders_updated and 'relative_reminders' in locals():
        for r in relative_reminders:
             try: db.refresh(r)
             except Exception: pass
    
    # Refresh unblocked tasks
    for task_item in unblocked_tasks:
        try:
            db.refresh(task_item)
        except Exception as e:
            print(f"Error refreshing unblocked task {task_item.id}: {e}")
            pass

    return {"updated_task": db_task, "unblocked_tasks": unblocked_tasks}

def delete_task(db: Session, task_id: int, user_id: int):
    db_task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.owner_id == user_id).first()
    if db_task:
        db.delete(db_task)
        db.commit()
        return True
    return False

# --- FileReference CRUD Functions ---

def create_file_reference(
    db: Session, 
    owner_id: int, 
    original_filename: str, 
    storage_path: str, 
    file_type: Optional[str] = None,
    file_size: Optional[int] = None
) -> models.FileReference:
    """Creates a FileReference record in the database."""
    db_file_ref = models.FileReference(
        owner_id=owner_id,
        original_filename=original_filename,
        storage_path=storage_path,
        file_type=file_type,
        file_size=file_size
        # project_id and task_id will be linked later
    )
    db.add(db_file_ref)
    db.commit()
    db.refresh(db_file_ref)
    return db_file_ref

def get_file_reference(db: Session, file_id: int) -> Optional[models.FileReference]:
    """Retrieves a FileReference record by its ID."""
    return db.query(models.FileReference).filter(models.FileReference.id == file_id).first()

def update_file_reference_links(
    db: Session, 
    user_id: int, 
    file_id: int, 
    update_data: schemas.FileReferenceUpdate
):
    """Updates the project_id or task_id for a FileReference, checking ownership."""
    db_file_ref = get_file_reference(db, file_id)
    if not db_file_ref:
        return None # File record not found

    # Verify user owns the file
    if db_file_ref.owner_id != user_id:
        return "unauthorized_file"

    update_values = update_data.model_dump(exclude_unset=True)
    updated = False

    # Validate and set project_id if provided
    if "project_id" in update_values:
        project_id = update_values["project_id"]
        if project_id is not None:
            project = get_project(db, project_id)
            if not project or project.owner_id != user_id:
                return "invalid_project"
        db_file_ref.project_id = project_id
        updated = True

    # Validate and set task_id if provided
    if "task_id" in update_values:
        task_id = update_values["task_id"]
        if task_id is not None:
            task = get_task(db, task_id)
            if not task or task.owner_id != user_id:
                return "invalid_task"
        db_file_ref.task_id = task_id
        updated = True

    if updated:
        db.add(db_file_ref)
        db.commit()
        db.refresh(db_file_ref)
    
    return db_file_ref # Return the updated (or unchanged) object

# Add get/update/delete file reference later if needed

# --- Reminder Utilities ---

def validate_recurrence_rule(rule_string: str) -> bool:
    """Validates an RRULE string using python-dateutil."""
    if not rule_string:
        return False
    try:
        # Ensure DTSTART is ignored if present, as we use current_trigger
        rrule_obj = rrulestr(rule_string, ignoretz=True)
        return True
    except ValueError as e:
        print(f"RRULE validation failed: {e}")
        return False

def calculate_next_trigger(rule_string: str, current_trigger: datetime) -> Optional[datetime]:
    """Calculates the next trigger time based on an RRULE string and the current trigger time."""
    if not rule_string:
        return None

    try:
        # Ensure current_trigger is timezone-aware UTC
        if current_trigger.tzinfo is None:
             current_trigger_aware = current_trigger.replace(tzinfo=UTC)
        else:
             current_trigger_aware = current_trigger.astimezone(UTC)
        
        # Convert to naive UTC for rrule processing with ignoretz=True
        current_trigger_naive_utc = current_trigger_aware.replace(tzinfo=None)

        # Parse the rule string using naive dtstart when ignoretz=True
        rule = rrulestr(rule_string, dtstart=current_trigger_naive_utc, ignoretz=True)

        # Get the next occurrence *after* the current trigger time (also using naive)
        next_occurrence_naive = rule.after(current_trigger_naive_utc)

        if next_occurrence_naive:
            # Convert the naive datetime result back to UTC-aware
            return next_occurrence_naive.replace(tzinfo=UTC)
        else:
            return None # No more occurrences found

    except ValueError as e:
        print(f"Error calculating next trigger for rule '{rule_string}': {e}")
        return None # Invalid rule or other calculation error

def get_due_reminders(db: Session) -> list[models.Reminder]:
    """Queries the database for active reminders whose trigger time has passed and are not currently snoozed."""
    now_utc = datetime.now(timezone.utc)
    return db.query(models.Reminder).filter(
        models.Reminder.is_active == True,
        models.Reminder.trigger_datetime <= now_utc,
        (models.Reminder.snoozed_until == None) | (models.Reminder.snoozed_until <= now_utc)
    ).all()

# --- Reminder CRUD Functions ---

def get_reminder(db: Session, reminder_id: int):
    return db.query(models.Reminder).filter(models.Reminder.id == reminder_id).first()

def get_user_reminders(db: Session, user_id: int, skip: int = 0, limit: int = 100):
    # Add filtering later (e.g., active, type, due before/after)
    return db.query(models.Reminder).filter(models.Reminder.owner_id == user_id).offset(skip).limit(limit).all()

def create_user_reminder(db: Session, reminder: schemas.ReminderCreate, owner_id: int):
    # Validate task if provided
    if reminder.task_id is not None:
        task = get_task(db, reminder.task_id)
        # Ensure task belongs to the *same user*
        if not task or task.owner_id != owner_id: # Check against owner_id
             return "invalid_task" # Or raise HTTPException? For now, return string code

    # Validate file reference if provided
    if reminder.file_reference_id is not None:
        file_ref = get_file_reference(db, reminder.file_reference_id)
        # Ensure file belongs to the *same user*
        if not file_ref or file_ref.owner_id != owner_id: # Check against owner_id
            return "invalid_file"

    # Validate contact if provided
    if reminder.contact_id is not None:
        contact = get_contact(db, reminder.contact_id, owner_id) # Pass owner_id
        if not contact: # get_contact checks ownership
            return "invalid_contact"

    # Validate relative task if provided
    if reminder.relative_to_task_completion_id is not None:
        relative_task = get_task(db, reminder.relative_to_task_completion_id)
        if not relative_task or relative_task.owner_id != owner_id: # Check against owner_id
             return "invalid_relative_task"

    # Basic validation of recurrence rule format if provided
    if reminder.recurrence_rule and not validate_recurrence_rule(reminder.recurrence_rule):
         return "invalid_recurrence_rule"

    # Clean the reminder data - Ensure trigger_datetime is None for relative types
    # The schema validation (@model_validator) should handle this, but double-check here
    reminder_data = reminder.model_dump()
    if reminder.reminder_type == schemas.ReminderType.RECURRING_RELATIVE:
        reminder_data['trigger_datetime'] = None # Ensure it's None for relative
        # Ensure relative_delay_minutes is set if it's relative (schema should enforce?)
        if reminder.relative_delay_minutes is None:
            # Decide on default or return error
            logger.warning("Relative reminder created without relative_delay_minutes, defaulting may occur if schema allows.")
            # return "missing_relative_delay"

    # Create the database model instance
    # owner_id is already available as a parameter
    db_reminder = models.Reminder(**reminder_data, owner_id=owner_id)

    # Add initial last_notified_at for persistent reminders?
    # Or let the scheduler handle the first notification? Let scheduler handle.

    db.add(db_reminder)
    db.commit()
    db.refresh(db_reminder)
    return db_reminder

def update_reminder(db: Session, reminder_id: int, reminder_update: schemas.ReminderUpdate, user_id: int):
    db_reminder = db.query(models.Reminder).filter(models.Reminder.id == reminder_id, models.Reminder.owner_id == user_id).first()
    if not db_reminder:
        return None # Reminder not found or not owned

    update_data = reminder_update.model_dump(exclude_unset=True)

    # --- Recurrence Validation Logic ---
    new_type = update_data.get('reminder_type', db_reminder.reminder_type) # Get proposed type or keep existing
    new_rule = update_data.get('recurrence_rule', db_reminder.recurrence_rule) # Get proposed rule or keep existing

    if new_type != models.ReminderType.ONE_TIME:
        # If changing TO recurring, or updating rule for existing recurring
        if not new_rule:
            return "invalid_rule" # Rule required for recurring type
        if not validate_recurrence_rule(new_rule):
            return "invalid_rule" # Provided/existing rule is invalid
        # If only type is changing TO recurring, ensure rule is present (handled above)
    elif new_type == models.ReminderType.ONE_TIME and 'reminder_type' in update_data:
        # If explicitly changing FROM recurring TO one-time
        update_data['recurrence_rule'] = None # Nullify the rule
    elif 'recurrence_rule' in update_data and update_data['recurrence_rule'] is not None and new_type == models.ReminderType.ONE_TIME:
         # If trying to set a rule on an existing ONE_TIME without changing type
         return "invalid_rule" # Cannot set rule for ONE_TIME type
    # --- End Recurrence Validation ---

    # Validate task if being changed
    if "task_id" in update_data:
        task_id = update_data["task_id"]
        if task_id is not None:
            task = get_task(db, task_id)
            if not task or task.owner_id != user_id:
                return "invalid_task"

    # Validate file if being changed
    if "file_reference_id" in update_data:
        file_ref_id = update_data["file_reference_id"]
        if file_ref_id is not None:
            file_ref = get_file_reference(db, file_ref_id)
            if not file_ref or file_ref.owner_id != user_id:
                return "invalid_file"

    # Validate contact if being changed
    if "contact_id" in update_data:
        contact_id = update_data["contact_id"]
        if contact_id is not None:
            contact = get_contact(db, contact_id, user_id)
            if not contact:
                return "invalid_contact"

    # Apply the updates
    for key, value in update_data.items():
        setattr(db_reminder, key, value)

    db.add(db_reminder)
    db.commit()
    db.refresh(db_reminder)
    return db_reminder

def delete_reminder(db: Session, reminder_id: int, user_id: int):
    db_reminder = db.query(models.Reminder).filter(models.Reminder.id == reminder_id, models.Reminder.owner_id == user_id).first()
    if db_reminder:
        db.delete(db_reminder)
        db.commit()
        return True
    return False

# --- Reminder Action Functions (Complete/Skip) ---

def complete_reminder_instance(db: Session, reminder_id: int, user_id: int, action_time: Optional[datetime] = None) -> Optional[Union[models.Reminder, str]]:
    """Marks a reminder instance as completed. For recurring scheduled, calculates next trigger."""
    db_reminder = db.query(models.Reminder).filter(models.Reminder.id == reminder_id, models.Reminder.owner_id == user_id).first()
    if not db_reminder:
        return "not_found"
    if not db_reminder.is_active:
        return "inactive"

    now = action_time or datetime.now(timezone.utc)

    # Log the completion event
    event = models.ReminderEvent(
        reminder_id=reminder_id,
        expected_trigger_time=db_reminder.trigger_datetime, # Log based on current trigger
        action_time=now,
        action_type=models.ReminderActionType.COMPLETED
    )
    db.add(event)

    if db_reminder.reminder_type == models.ReminderType.RECURRING_SCHEDULED:
        next_trigger = calculate_next_trigger(db_reminder.recurrence_rule, db_reminder.trigger_datetime)
        if next_trigger:
            db_reminder.trigger_datetime = next_trigger
            # Keep is_active = True
        else:
            db_reminder.is_active = False # No more occurrences
    else: # ONE_TIME or RECURRING_RELATIVE (completing the reminder itself)
        db_reminder.is_active = False

    db.commit()
    db.refresh(db_reminder)
    return db_reminder

def skip_reminder_instance(db: Session, reminder_id: int, user_id: int, action_time: Optional[datetime] = None) -> Optional[Union[models.Reminder, str]]:
    """Marks a reminder instance as skipped. For recurring scheduled, calculates next trigger."""
    db_reminder = db.query(models.Reminder).filter(models.Reminder.id == reminder_id, models.Reminder.owner_id == user_id).first()
    if not db_reminder:
        return "not_found"
    if not db_reminder.is_active:
        return "inactive"

    now = action_time or datetime.now(timezone.utc)

    # Log the skip event
    event = models.ReminderEvent(
        reminder_id=reminder_id,
        expected_trigger_time=db_reminder.trigger_datetime, # Log based on current trigger
        action_time=now,
        action_type=models.ReminderActionType.SKIPPED
    )
    db.add(event)

    if db_reminder.reminder_type == models.ReminderType.RECURRING_SCHEDULED:
        next_trigger = calculate_next_trigger(db_reminder.recurrence_rule, db_reminder.trigger_datetime)
        if next_trigger:
            db_reminder.trigger_datetime = next_trigger
            # Keep is_active = True
        else:
            db_reminder.is_active = False # No more occurrences
    else: # ONE_TIME or RECURRING_RELATIVE (skipping essentially cancels)
        db_reminder.is_active = False

    db.commit()
    db.refresh(db_reminder)
    return db_reminder

def get_pending_persistent_reminders(db: Session) -> list[models.Reminder]:
    """Queries for active reminders that have been notified but not completed/skipped/snoozed,
       and whose persistent reminder frequency has elapsed.
    """
    now_utc = datetime.now(timezone.utc)
    # Note: This requires last_notified_at and remind_frequency_minutes to be set.
    # We need a timedelta operation, which might require specific SQL function depending on DB
    # Using SQLAlchemy's func for now, assuming compatibility or later adjustment.
    # We filter out reminders that *have* a completion/skip event for the current trigger time.
    # This subquery approach might be inefficient and needs testing/optimization.

    # Subquery to find reminder instances that have been completed or skipped
    # for the trigger time matching the reminder's last_notified_at (approx)
    # This is complex because event expected_trigger != reminder last_notified necessarily
    # A simpler, slightly less precise approach: Check if notified and frequency has passed.
    # Let the job logic double-check against recent events.

    from sqlalchemy import func, text

    return db.query(models.Reminder).filter(
        models.Reminder.is_active == True,
        models.Reminder.last_notified_at != None,
        models.Reminder.remind_frequency_minutes != None,
        # Check if snooze has expired or is not set
        (models.Reminder.snoozed_until == None) | (models.Reminder.snoozed_until <= now_utc),
        # Check if frequency minutes have passed since last notification
        # This syntax assumes a function like `now() - interval 'X minutes'`
        # Adapting for SQLite/PostgreSQL might be needed.
        # Using func.now() and basic comparison assuming DateTime storage handles it.
        # TODO: Verify/adjust timedelta logic per database.
        models.Reminder.last_notified_at <= (now_utc - func.cast(text("'' || reminders.remind_frequency_minutes || ' minutes'"), sa.Interval))
        # ^^ This interval subtraction is complex and likely DB-specific. Placeholder.
        # Alternative (less efficient): Fetch candidates and filter in Python?
        # Fetch reminders where last_notified + frequency < now
    ).all()

# --- Reminder History Function ---

def get_reminder_history(db: Session, reminder_id: int, user_id: int, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Optional[Union[List[models.ReminderEvent], str]]:
    """Retrieves the event history for a specific reminder owned by the user."""
    # Verify reminder exists and belongs to user
    db_reminder = db.query(models.Reminder).filter(models.Reminder.id == reminder_id, models.Reminder.owner_id == user_id).first()
    if not db_reminder:
        return "not_found"

    query = db.query(models.ReminderEvent).filter(models.ReminderEvent.reminder_id == reminder_id)

    # Apply date filters if provided (ensure they are timezone-aware, e.g., UTC)
    if start_date:
        query = query.filter(models.ReminderEvent.action_time >= start_date)
    if end_date:
        # Add a day if only date provided, to include the whole end day?
        # Or expect precise timestamp. Assuming precise timestamp for now.
        query = query.filter(models.ReminderEvent.action_time <= end_date)

    history = query.order_by(models.ReminderEvent.action_time.desc()).all()
    return history

# --- Task Dependency Functions ---

def add_task_dependency(db: Session, task_id: int, depends_on_task_id: int, user_id: int) -> Optional[str]:
    """Adds a dependency link between two tasks owned by the user."""
    if task_id == depends_on_task_id:
        return "self_dependency"

    # Verify both tasks exist and belong to the user
    task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.owner_id == user_id).first()
    depends_on_task = db.query(models.Task).filter(models.Task.id == depends_on_task_id, models.Task.owner_id == user_id).first()

    if not task or not depends_on_task:
        return "not_found"
    
    # Check if dependency already exists (optional but good practice)
    # Accessing the relationship directly is easier than querying association table
    if depends_on_task in task.dependency_tasks:
         return "already_exists"

    # Add the dependency
    task.dependency_tasks.append(depends_on_task)
    db.add(task)
    
    # Check and update status after adding dependency
    check_and_update_task_status(db, task)
    
    db.commit() # Commit changes to task and potentially its status
    return "ok"

def remove_task_dependency(db: Session, task_id: int, depends_on_task_id: int, user_id: int) -> Optional[str]:
    """Removes a dependency link between two tasks owned by the user."""
    # Verify both tasks exist and belong to the user
    task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.owner_id == user_id).first()
    depends_on_task = db.query(models.Task).filter(models.Task.id == depends_on_task_id, models.Task.owner_id == user_id).first()

    if not task or not depends_on_task:
        return "not_found"

    # Check if the dependency exists before trying to remove
    if depends_on_task not in task.dependency_tasks:
        return "not_found" # Or maybe "dependency_not_found"?

    # Remove the dependency
    task.dependency_tasks.remove(depends_on_task)
    db.add(task)
    
    # Check and update status after removing dependency
    check_and_update_task_status(db, task)

    db.commit() # Commit changes to task and potentially its status
    return "ok"

# --- Project Dependency Functions ---

def add_project_dependency(db: Session, project_id: int, depends_on_project_id: int, user_id: int) -> Optional[str]:
    """Adds a dependency link between two projects owned by the user."""
    if project_id == depends_on_project_id:
        return "self_dependency"

    # Verify both projects exist and belong to the user
    project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.owner_id == user_id).first()
    depends_on_project = db.query(models.Project).filter(models.Project.id == depends_on_project_id, models.Project.owner_id == user_id).first()

    if not project or not depends_on_project:
        return "not_found"

    # Check if dependency already exists
    if depends_on_project in project.dependency_projects:
         return "already_exists"

    # Add the dependency
    project.dependency_projects.append(depends_on_project)
    db.add(project)
    
    # Check and update status after adding dependency
    check_and_update_project_status(db, project)

    db.commit() # Commit changes to project and potentially its status
    return "ok"

def remove_project_dependency(db: Session, project_id: int, depends_on_project_id: int, user_id: int) -> Optional[str]:
    """Removes a dependency link between two projects owned by the user."""
    # Verify both projects exist and belong to the user
    project = db.query(models.Project).filter(models.Project.id == project_id, models.Project.owner_id == user_id).first()
    depends_on_project = db.query(models.Project).filter(models.Project.id == depends_on_project_id, models.Project.owner_id == user_id).first()

    if not project or not depends_on_project:
        return "not_found"

    # Check if the dependency exists before trying to remove
    if depends_on_project not in project.dependency_projects:
        return "not_found"

    # Remove the dependency
    project.dependency_projects.remove(depends_on_project)
    db.add(project)
    
    # Check and update status after removing dependency
    check_and_update_project_status(db, project)

    db.commit() # Commit changes to project and potentially its status
    return "ok"

# --- Dependency Status Update Helpers ---

def check_and_update_task_status(db: Session, task: models.Task) -> bool:
    """Checks a task's dependencies and updates its status to BLOCKED or PENDING if necessary.
    
    Returns:
        bool: True if the task was unblocked (status changed from BLOCKED to PENDING), False otherwise.
    """
    if not task:
        return False # Task object is None

    print(f"[Helper Task {task.id}] Checking dependencies. Current status: {task.status}") # Debug
    uncompleted_dependencies = False
    dependency_ids = [d.id for d in task.dependency_tasks]
    print(f"[Helper Task {task.id}] Dependency IDs: {dependency_ids}") # Debug
    for dep_id in dependency_ids:
        # Fetch the dependency task fresh from the DB within the same session
        # This ensures we see any status changes committed *before* this check runs
        dep_task = db.query(models.Task).filter(models.Task.id == dep_id).first()
        if not dep_task:
             print(f"[Helper Task {task.id}] Warning: Dependency task {dep_id} not found!") # Debug
             uncompleted_dependencies = True 
             break 
        print(f"[Helper Task {task.id}] Checking Dep ID {dep_id} Status: {dep_task.status}") # Debug
        if dep_task.status != models.TaskStatus.COMPLETED:
            print(f"[Helper Task {task.id}] Dependency {dep_id} is NOT completed.") # Debug
            uncompleted_dependencies = True
            break 
        else:
            print(f"[Helper Task {task.id}] Dependency {dep_id} IS completed.") # Debug

    status_changed = False
    was_unblocked = False # Flag specifically for the BLOCKED -> PENDING transition
    if uncompleted_dependencies:
        if task.status != models.TaskStatus.BLOCKED:
            print(f"[Helper Task {task.id}] Setting status to BLOCKED.") # Debug
            task.status = models.TaskStatus.BLOCKED
            status_changed = True
        else:
            print(f"[Helper Task {task.id}] Already BLOCKED, no change needed.") # Debug
    else: 
        if task.status == models.TaskStatus.BLOCKED:
            print(f"[Helper Task {task.id}] Setting status to PENDING (unblocked).") # Debug
            task.status = models.TaskStatus.PENDING 
            status_changed = True
            was_unblocked = True # Set the flag
        else:
            print(f"[Helper Task {task.id}] Not blocked, no change needed.") # Debug
    
    if status_changed:
        print(f"[Helper Task {task.id}] Adding task with new status {task.status} to session.") # Debug
        db.add(task)
        # db.commit() # No commit here
    else:
        print(f"[Helper Task {task.id}] No status change detected.") # Debug

    return was_unblocked # Return the specific flag

def check_and_update_project_status(db: Session, project: models.Project) -> bool:
    """Checks a project's dependencies and updates its status to ON_HOLD or ACTIVE if necessary.
    
    Returns:
        bool: True if the project was unblocked (status changed from ON_HOLD to ACTIVE), False otherwise.
    """
    if not project:
        return False # Project object is None

    print(f"[Helper Project {project.id}] Checking dependencies. Current status: {project.status}") # Debug
    uncompleted_dependencies = False
    # Instead of iterating the relationship directly, iterate IDs and fetch
    dependency_ids = [d.id for d in project.dependency_projects]
    print(f"[Helper Project {project.id}] Dependency IDs: {dependency_ids}") # Debug
    for dep_id in dependency_ids:
        # Fetch the dependency project fresh from the DB
        dep_project = db.query(models.Project).filter(models.Project.id == dep_id).first()
        if not dep_project:
            print(f"[Helper Project {project.id}] Warning: Dependency project {dep_id} not found!") # Debug
            uncompleted_dependencies = True
            break
        print(f"[Helper Project {project.id}] Checking Dep ID {dep_id} Status: {dep_project.status}") # Debug
        if dep_project.status != models.ProjectStatus.COMPLETED:
            print(f"[Helper Project {project.id}] Dependency {dep_id} is NOT completed.") # Debug
            uncompleted_dependencies = True
            break
        else:
             print(f"[Helper Project {project.id}] Dependency {dep_id} IS completed.") # Debug

    status_changed = False
    was_unblocked = False # Flag specifically for the ON_HOLD -> ACTIVE transition
    if uncompleted_dependencies:
        # Use ON_HOLD as the "blocked" state for projects
        if project.status != models.ProjectStatus.ON_HOLD:
            print(f"[Helper Project {project.id}] Setting status to ON_HOLD.") # Debug
            project.status = models.ProjectStatus.ON_HOLD
            status_changed = True
        else:
            print(f"[Helper Project {project.id}] Already ON_HOLD, no change needed.") # Debug
    else: # No uncompleted dependencies
        if project.status == models.ProjectStatus.ON_HOLD:
            print(f"[Helper Project {project.id}] Setting status to ACTIVE (unblocked).") # Debug
            # Reset to ACTIVE. Could also consider restoring previous state if needed.
            project.status = models.ProjectStatus.ACTIVE
            status_changed = True
            was_unblocked = True # Set the flag
        else:
            print(f"[Helper Project {project.id}] Not ON_HOLD, no change needed.") # Debug
    
    if status_changed:
        print(f"[Helper Project {project.id}] Adding project with new status {project.status} to session.") # Debug
        db.add(project)
        # db.commit() # Remove commit
        # db.refresh(project) # Refresh is not needed here, happens later if required
    else:
        print(f"[Helper Project {project.id}] No status change detected.") # Debug

    return was_unblocked # Return the specific flag

# --- Projects by Category Function ---

def get_user_projects_by_category(db: Session, user_id: int) -> schemas.ProjectsByCategoryResponse:
    """Fetches user's projects and groups them by category."""
    # Fetch all user's projects and categories in potentially fewer queries
    # Eager load projects relationship for categories if performance is critical, but usually not needed
    user_categories = db.query(models.Category).filter(models.Category.owner_id == user_id).all()
    user_projects = db.query(models.Project).filter(models.Project.owner_id == user_id).all()

    categorized_projects_map = {cat.id: [] for cat in user_categories}
    uncategorized_projects = []

    for project in user_projects:
        if project.category_id and project.category_id in categorized_projects_map:
            categorized_projects_map[project.category_id].append(project)
        else:
            uncategorized_projects.append(project)

    # Build the response structure
    categorized_response_list = []
    for category in user_categories:
        # Pass the list of projects associated with this category_id
        category_with_projects = schemas.CategoryWithProjects(
            id=category.id,
            name=category.name,
            description=category.description,
            projects=categorized_projects_map.get(category.id, []) # Use .get for safety
        )
        categorized_response_list.append(category_with_projects)

    return schemas.ProjectsByCategoryResponse(
        categorized=categorized_response_list,
        uncategorized=uncategorized_projects
    )

# --- Add other CRUD functions later --- 
# e.g., get_projects, create_task, etc. 

def get_user_available_tasks(db: Session, user_id: int) -> List[models.Task]:
    """Retrieves tasks for a user that are in PENDING or IN_PROGRESS status."""
    return db.query(models.Task).filter(
        models.Task.owner_id == user_id,
        models.Task.status.in_([
            models.TaskStatus.PENDING,
            models.TaskStatus.IN_PROGRESS
        ])
    ).all()

# --- Contact CRUD Functions ---

def get_contact(db: Session, contact_id: int, user_id: int) -> Optional[models.Contact]:
    """Gets a single contact by ID, ensuring it belongs to the user."""
    return db.query(models.Contact).filter(models.Contact.id == contact_id, models.Contact.owner_id == user_id).first()

def get_user_contacts(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> List[models.Contact]:
    """Gets a list of contacts belonging to the user."""
    return db.query(models.Contact).filter(models.Contact.owner_id == user_id).offset(skip).limit(limit).all()

def create_user_contact(db: Session, contact: schemas.ContactCreate, user_id: int) -> models.Contact:
    """Creates a new contact for the user."""
    db_contact = models.Contact(**contact.model_dump(), owner_id=user_id)
    db.add(db_contact)
    db.commit()
    db.refresh(db_contact)
    return db_contact

def update_contact(db: Session, contact_id: int, contact_update: schemas.ContactUpdate, user_id: int) -> Optional[models.Contact]:
    """Updates an existing contact belonging to the user."""
    db_contact = get_contact(db, contact_id, user_id)
    if not db_contact:
        return None

    update_data = contact_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_contact, key, value)

    db.add(db_contact)
    db.commit()
    db.refresh(db_contact)
    return db_contact

def delete_contact(db: Session, contact_id: int, user_id: int) -> bool:
    """Deletes a contact belonging to the user."""
    db_contact = get_contact(db, contact_id, user_id)
    if db_contact:
        # TODO: Consider implications of deleting a contact linked to tasks/reminders.
        # Options: Set FKs to NULL, prevent deletion if linked, cascade delete (unlikely desired).
        # For now, allow deletion without handling links.
        db.delete(db_contact)
        db.commit()
        return True
    return False 

# --- Outstanding Items Function ---

def get_outstanding_items_for_contact(db: Session, contact_id: int, user_id: int) -> Optional[schemas.OutstandingItemsResponse]:
    """Retrieves outstanding tasks and reminders linked to a specific contact for the user."""
    # First, verify the contact exists and belongs to the user
    contact = get_contact(db, contact_id, user_id)
    if not contact:
        return None # Indicate contact not found or not owned

    now_utc = datetime.now(timezone.utc)

    # Query outstanding tasks linked to this contact
    outstanding_tasks = db.query(models.Task).filter(
        models.Task.owner_id == user_id,
        models.Task.contact_id == contact_id,
        models.Task.status.in_([
            models.TaskStatus.PENDING,
            models.TaskStatus.IN_PROGRESS
        ])
    ).all()

    # Query outstanding reminders linked to this contact
    outstanding_reminders = db.query(models.Reminder).filter(
        models.Reminder.owner_id == user_id,
        models.Reminder.contact_id == contact_id,
        models.Reminder.is_active == True,
        models.Reminder.trigger_datetime != None, # Exclude relative reminders not yet triggered
        (models.Reminder.snoozed_until == None) | (models.Reminder.snoozed_until <= now_utc)
    ).all()
    
    # Query outstanding Notes linked to this contact
    # Use the existing get_user_notes function which handles filtering and ownership
    outstanding_notes = get_user_notes(db=db, user_id=user_id, contact_id=contact_id, limit=1000) # Use a high limit or handle pagination if needed

    return schemas.OutstandingItemsResponse(
        tasks=outstanding_tasks,
        reminders=outstanding_reminders,
        notes=outstanding_notes # Add notes to the response
    ) 

# --- Project Summary Function ---

def get_project_summary(db: Session, project_id: int, user_id: int) -> Optional[dict]:
    """Retrieves structured summary data for a specific project owned by the user."""
    # Fetch project and verify ownership, eager load category name if possible
    project = db.query(models.Project).options(
        # Eager load category to get name without separate query
        sqlalchemy.orm.joinedload(models.Project.category) 
    ).filter(
        models.Project.id == project_id, 
        models.Project.owner_id == user_id
    ).first()

    if not project:
        return None # Project not found or not owned

    # Get task counts by status for this project
    task_counts_query = db.query(
        models.Task.status,
        func.count(models.Task.id).label('count')
    ).filter(
        models.Task.project_id == project_id,
        models.Task.owner_id == user_id # Technically redundant if project ownership is checked, but safer
    ).group_by(
        models.Task.status
    ).all()

    # Convert query result to the TaskStatusCounts structure
    task_counts = schemas.TaskStatusCounts()
    for status_enum, count in task_counts_query:
        if hasattr(task_counts, status_enum.name.lower()):
            setattr(task_counts, status_enum.name.lower(), count)

    # Get file count for this project
    file_count = db.query(func.count(models.FileReference.id)).filter(
        models.FileReference.project_id == project_id,
        models.FileReference.owner_id == user_id # Also safer
    ).scalar() or 0 # Use scalar() and default to 0 if None

    # Get category name (already loaded if category exists)
    category_name = project.category.name if project.category else None

    # Assemble the response data (will be validated by response_model)
    summary_data = {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "category_name": category_name,
        "task_counts": task_counts.model_dump(), # Convert Pydantic model to dict for return
        "file_count": file_count
    }

    return summary_data 

# --- Note CRUD Functions ---

def get_note(db: Session, note_id: int, user_id: int) -> Optional[models.Note]:
    """Gets a single note by ID, ensuring it belongs to the user."""
    return db.query(models.Note).filter(models.Note.id == note_id, models.Note.owner_id == user_id).first()

def get_user_notes(
    db: Session, 
    user_id: int, 
    contact_id: Optional[int] = None, # Optional filter by contact
    skip: int = 0, 
    limit: int = 100
) -> List[models.Note]:
    """Gets a list of notes for a user, optionally filtered by contact_id."""
    query = db.query(models.Note).filter(models.Note.owner_id == user_id)
    if contact_id is not None:
        # Ensure the contact also belongs to the user before filtering
        contact = get_contact(db, contact_id, user_id)
        if not contact:
            # Or raise an error? Returning empty list seems safer.
            return [] 
        query = query.filter(models.Note.contact_id == contact_id)
    
    return query.order_by(models.Note.updated_at.desc(), models.Note.created_at.desc()).offset(skip).limit(limit).all()

def create_user_note(db: Session, note: schemas.NoteCreate, user_id: int) -> Union[models.Note, str]:
    """Creates a note for a user. Returns the note object or an error string."""
    # Validate contact if provided
    if note.contact_id is not None:
        contact = get_contact(db, note.contact_id, user_id)
        if not contact: # get_contact already checks ownership
            return "invalid_contact" # Return error code
            
    note_data = note.model_dump()
    db_note = models.Note(**note_data, owner_id=user_id)
    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    return db_note

def update_note(db: Session, note_id: int, note_update: schemas.NoteUpdate, user_id: int) -> Optional[Union[models.Note, str]]:
    """Updates a note. Returns the updated note object, an error string, or None if not found."""
    db_note = get_note(db, note_id, user_id) # Use get_note to ensure ownership
    if not db_note:
        return None # Note not found or not owned by user

    update_data = note_update.model_dump(exclude_unset=True)

    # Validate contact if it's being changed
    if 'contact_id' in update_data and update_data['contact_id'] is not None:
        contact = get_contact(db, update_data['contact_id'], user_id)
        if not contact:
            return "invalid_contact"
        
    # Apply updates
    for key, value in update_data.items():
        setattr(db_note, key, value)
        
    # Mark updated_at (SQLAlchemy might do this automatically if onupdate is set, but explicit is fine)
    db_note.updated_at = datetime.now(timezone.utc)
    
    db.add(db_note) # Add to session (might already be there)
    db.commit()
    db.refresh(db_note)
    return db_note

def delete_note(db: Session, note_id: int, user_id: int) -> bool:
    """Deletes a note, ensuring it belongs to the user."""
    db_note = get_note(db, note_id, user_id) # Use get_note for ownership check
    if db_note:
        db.delete(db_note)
        db.commit()
        return True
    return False 

def get_notes_content_by_filter(db: Session, user_id: int, filters: schemas.NoteSummaryRequest) -> Tuple[List[int], str]:
    """Retrieves note content based on filters for a user and combines it.

    Args:
        db: The database session.
        user_id: The ID of the user whose notes to filter.
        filters: A NoteSummaryRequest object containing filter criteria.

    Returns:
        A tuple containing: (list of included note IDs, combined content string).
        Returns ([], "") if no notes match the criteria.
    """
    query = db.query(models.Note).filter(models.Note.owner_id == user_id)

    # Apply filters
    filter_conditions = []
    if filters.note_ids:
        filter_conditions.append(models.Note.id.in_(filters.note_ids))
    
    if filters.source:
        filter_conditions.append(models.Note.source == filters.source)
        
    if filters.tags:
        # Simple tag filtering: requires all provided tags to be present (case-insensitive LIKE)
        # Assumes tags are stored as a comma-separated string in the DB.
        # For more robust tag searching, consider a separate Tags table or array column type.
        individual_tags = [tag.strip() for tag in filters.tags.split(',') if tag.strip()]
        if individual_tags:
            # Using AND to require all tags match
            tag_conditions = [models.Note.tags.ilike(f'%{tag}%') for tag in individual_tags]
            filter_conditions.append(and_(*tag_conditions))
            
    # Combine filters if any were added
    if filter_conditions:
        query = query.filter(and_(*filter_conditions))
        
    # Order by creation date to have a consistent order for summarization
    query = query.order_by(models.Note.created_at)

    matching_notes = query.all()

    if not matching_notes:
        return ([], "")

    # Combine content and collect IDs
    combined_content = []
    included_ids = []
    for note in matching_notes:
        included_ids.append(note.id)
        header = f"--- Note ID: {note.id} | Source: {note.source or 'N/A'} | Tags: {note.tags or 'N/A'} ---"
        combined_content.append(header)
        combined_content.append(note.content or "") # Add content, handle if None
        combined_content.append("\n---\n") # Separator

    return (included_ids, "\n".join(combined_content))

# === List CRUD ===

def create_list(db: Session, list_data: schemas.ListCreate, user_id: int) -> models.List:
    """Creates a new list for a user."""
    db_list = models.List(**list_data.model_dump(), user_id=user_id)
    db.add(db_list)
    db.commit()
    db.refresh(db_list)
    logger.info(f"Created list {db_list.id} for user {user_id}")
    return db_list

def get_list(db: Session, list_id: int, user_id: int) -> Optional[models.List]:
    """Retrieves a specific list by ID, ensuring it belongs to the user."""
    return db.query(models.List).options(joinedload(models.List.items)).filter(
        models.List.id == list_id,
        models.List.user_id == user_id
    ).first()

def get_lists_by_user(db: Session, user_id: int) -> List[models.List]:
    """Retrieves all lists belonging to a specific user."""
    return db.query(models.List).options(joinedload(models.List.items)).filter(
        models.List.user_id == user_id
    ).order_by(models.List.name).all()

def update_list(db: Session, list_id: int, list_data: schemas.ListUpdate, user_id: int) -> Optional[models.List]:
    """Updates a list, ensuring it belongs to the user."""
    db_list = get_list(db=db, list_id=list_id, user_id=user_id)
    if not db_list:
        logger.warning(f"Attempt to update non-existent or unauthorized list {list_id} by user {user_id}")
        return None

    update_data = list_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_list, key, value)

    db_list.updated_at = datetime.now(timezone.utc) # Manually update timestamp
    db.commit()
    db.refresh(db_list)
    logger.info(f"Updated list {list_id} for user {user_id}")
    return db_list

def delete_list(db: Session, list_id: int, user_id: int) -> bool:
    """Deletes a list, ensuring it belongs to the user. Returns True if deleted, False otherwise."""
    db_list = get_list(db=db, list_id=list_id, user_id=user_id)
    if not db_list:
        logger.warning(f"Attempt to delete non-existent or unauthorized list {list_id} by user {user_id}")
        return False

    db.delete(db_list)
    db.commit()
    logger.info(f"Deleted list {list_id} for user {user_id}")
    return True

# === ListItem CRUD ===

def create_list_item(db: Session, item_data: schemas.ListItemCreate, list_id: int, user_id: int) -> Optional[Union[models.ListItem, str]]:
    """Creates a new item within a specific list, ensuring user owns the list."""
    # Verify user owns the parent list
    parent_list = get_list(db=db, list_id=list_id, user_id=user_id)
    if not parent_list:
        logger.warning(f"Attempt to create item in non-existent or unauthorized list {list_id} by user {user_id}")
        return "list_not_found"

    db_item = models.ListItem(**item_data.model_dump(), list_id=list_id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    logger.info(f"Created item {db_item.id} in list {list_id} for user {user_id}")
    return db_item

def update_list_item(db: Session, item_id: int, item_data: schemas.ListItemUpdate, user_id: int) -> Optional[Union[models.ListItem, str]]:
    """Updates a list item, ensuring the user owns the parent list."""
    # Query the item and join with the list to check ownership in one go
    db_item = db.query(models.ListItem).join(models.List).filter(
        models.ListItem.id == item_id,
        models.List.user_id == user_id
    ).first()

    if not db_item:
        logger.warning(f"Attempt to update non-existent or unauthorized list item {item_id} by user {user_id}")
        return "item_not_found"

    update_data = item_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_item, key, value)

    db_item.updated_at = datetime.now(timezone.utc)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    logger.info(f"Updated item {item_id} in list {db_item.list_id} for user {user_id}")
    return db_item

def delete_list_item(db: Session, item_id: int, user_id: int) -> bool:
    """Deletes a list item, ensuring the user owns the parent list."""
    # Query the item and join with the list to check ownership
    db_item = db.query(models.ListItem).join(models.List).filter(
        models.ListItem.id == item_id,
        models.List.user_id == user_id
    ).first()

    if not db_item:
        logger.warning(f"Attempt to delete non-existent or unauthorized list item {item_id} by user {user_id}")
        return False

    list_id = db_item.list_id # Store list_id for logging before deletion
    db.delete(db_item)
    db.commit()
    logger.info(f"Deleted item {item_id} from list {list_id} for user {user_id}")
    return True

# === Placeholder Removal ===
# Remove the old placeholder comment below if it exists

# === List CRUD (Placeholder/Not Implemented) === 

def update_user_ms_oid(db: Session, user_id: int, ms_oid: str):
    """Update the Microsoft OID for a given user."""
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user:
        db_user.ms_oid = ms_oid
        db.commit()
        db.refresh(db_user)
        return db_user
    return None

# --- Add function to update device token ---
def update_user_device_token(db: Session, user_id: int, device_token: str) -> Optional[models.User]:
    """Update the device token for a given user."""
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user:
        db_user.device_token = device_token
        db.commit()
        db.refresh(db_user)
        return db_user
    return None
# --- End add --- 