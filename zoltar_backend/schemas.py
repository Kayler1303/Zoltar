from pydantic import BaseModel, EmailStr, field_validator, model_validator, Field
from datetime import datetime
from typing import Optional, Any, List, Dict

# Import Enum from models using direct import
from models import ProjectStatus, TaskStatus, ReminderType, ReminderActionType

# Base model for User - common attributes
class UserBase(BaseModel):
    email: EmailStr

# Schema for creating a new user (includes password)
class UserCreate(UserBase):
    password: str

# Schema for reading user data (omits password)
class User(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True # Replaces orm_mode = True in Pydantic v2

# --- Category Schemas ---

class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None

class CategoryCreate(CategoryBase):
    pass

class Category(CategoryBase):
    id: int
    owner_id: int

    class Config:
        from_attributes = True # Replaces orm_mode = True in Pydantic v2

# --- Project Schemas ---

class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    category_id: Optional[int] = None

class ProjectCreate(ProjectBase):
    # Status might be set implicitly on creation, or allowed optionally
    status: Optional[ProjectStatus] = ProjectStatus.ACTIVE # Default to ACTIVE
    pass # Inherits name, description, category_id

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None # Allow unsetting category
    status: Optional[ProjectStatus] = None

class Project(ProjectBase):
    id: int
    owner_id: int
    status: ProjectStatus # Status is not optional when reading
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Task Schemas ---

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    project_id: Optional[int] = None
    contact_id: Optional[int] = None # Add contact_id

class TaskCreate(TaskBase):
    status: Optional[TaskStatus] = TaskStatus.PENDING # Default to PENDING
    pass # Inherits title, description, due_date, project_id, contact_id

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    project_id: Optional[int] = None # Allow changing/unsetting project
    status: Optional[TaskStatus] = None
    contact_id: Optional[int] = None # Allow changing/unsetting contact

class Task(TaskBase):
    id: int
    owner_id: int
    status: TaskStatus # Status is required when reading
    # contact_id is inherited from TaskBase
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- FileReference Schema (for reading) ---

class FileReference(BaseModel):
    id: int
    original_filename: str
    storage_path: str # Store the path where the file is saved
    file_type: Optional[str] = None # e.g., application/pdf, image/jpeg
    file_size: Optional[int] = None # In bytes
    owner_id: int
    project_id: Optional[int] = None # Link to project
    task_id: Optional[int] = None # Link to task
    uploaded_at: datetime

    class Config:
        from_attributes = True

# --- FileReference Update Schema ---

class FileReferenceUpdate(BaseModel):
    # Allow explicitly setting project/task to null to unlink
    project_id: Optional[int] = None
    task_id: Optional[int] = None

    # Ensure at least one field is provided for an update
    # Note: In Pydantic v2, validation logic like root_validator is handled differently.
    # For simplicity here, we assume the API endpoint logic ensures valid updates.
    # If stricter validation is needed, consider adding custom validators or using
    # a library like `pydantic-partial` if partial updates are complex.

# --- Reminder Schemas ---

class ReminderBase(BaseModel):
    # Make title optional, description required
    title: Optional[str] = None 
    description: str 
    trigger_datetime: Optional[datetime] = None # Make optional for relative creation
    task_id: Optional[int] = None
    file_reference_id: Optional[int] = None
    contact_id: Optional[int] = None # Add contact_id
    recurrence_rule: Optional[str] = Field(None, examples=["FREQ=WEEKLY;BYDAY=MO;INTERVAL=2"]) # Optional RRULE string

class ReminderCreate(ReminderBase):
    reminder_type: ReminderType = ReminderType.ONE_TIME
    is_active: Optional[bool] = True # Add is_active, default to True
    # contact_id inherited from Base
    # recurrence_rule is optional by default from Base
    # Fields specific to RECURRING_RELATIVE type
    relative_to_task_completion_id: Optional[int] = None
    relative_delay_minutes: Optional[int] = None

    @model_validator(mode='before')
    def check_reminder_logic(cls, data: Any) -> Any:
        reminder_type = data.get('reminder_type') or ReminderType.ONE_TIME
        recurrence_rule = data.get('recurrence_rule')
        trigger_datetime = data.get('trigger_datetime')
        relative_task_id = data.get('relative_to_task_completion_id')
        
        # Handle recurrence rule validation
        if reminder_type in [ReminderType.RECURRING_SCHEDULED]: # Only scheduled needs rule/trigger time now
            if not recurrence_rule:
                raise ValueError("recurrence_rule is required for recurring scheduled reminders")
            if not trigger_datetime:
                 raise ValueError("trigger_datetime is required for recurring scheduled reminders")
        elif reminder_type == ReminderType.RECURRING_RELATIVE:
            if not relative_task_id:
                raise ValueError("relative_to_task_completion_id is required for recurring relative reminders")
            if trigger_datetime:
                data['trigger_datetime'] = None # Ensure trigger time is NOT set initially for relative
            if recurrence_rule:
                data['recurrence_rule'] = None # Ensure rule is NOT set for relative (uses task completion)
        elif reminder_type == ReminderType.ONE_TIME:
             if not trigger_datetime:
                 raise ValueError("trigger_datetime is required for one-time reminders")
             if recurrence_rule:
                data['recurrence_rule'] = None # Clear rule for one-time reminders
             if relative_task_id:
                 data['relative_to_task_completion_id'] = None # Clear relative fields
                 data['relative_delay_minutes'] = None

        return data

    # Ensure ReminderType is set correctly if not explicitly passed
    # This might be redundant if the default works as expected, but belts and suspenders
    @field_validator('reminder_type', mode='before')
    @classmethod
    def normalize_reminder_type(cls, v):
        """
        Accept string inputs for reminder_type (case-insensitive for enum name or value), and default to ONE_TIME.
        """
        if v is None:
            return ReminderType.ONE_TIME
        if isinstance(v, str):
            # Try matching enum by name (case-insensitive)
            try:
                return ReminderType[v.upper()]
            except KeyError:
                # Try matching enum by value (case-insensitive)
                try:
                    return ReminderType(v.lower())
                except ValueError:
                    raise ValueError(f"Invalid reminder_type: {v}")
        return v

class ReminderUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    trigger_datetime: Optional[datetime] = None
    task_id: Optional[int] = None
    file_reference_id: Optional[int] = None
    contact_id: Optional[int] = None # Allow changing/unsetting contact
    is_active: Optional[bool] = None
    snoozed_until: Optional[datetime] = None # Add field for snoozing
    reminder_type: Optional[ReminderType] = None # Allow changing type
    recurrence_rule: Optional[str] = None # Allow updating/setting/unsetting rule

    # Normalize reminder_type inputs (case-insensitive) on update
    @field_validator('reminder_type', mode='before')
    @classmethod
    def normalize_reminder_type_update(cls, v):
        """
        Accept string inputs for reminder_type (case-insensitive for enum name or value) in updates.
        """
        if v is None or isinstance(v, ReminderType):
            return v
        if isinstance(v, str):
            # Try matching enum by name (case-insensitive)
            try:
                return ReminderType[v.upper()]
            except KeyError:
                # Try matching enum by value (case-insensitive)
                try:
                    return ReminderType(v.lower())
                except ValueError:
                    raise ValueError(f"Invalid reminder_type: {v}")
        return v

class Reminder(ReminderBase):
    id: int
    owner_id: int
    reminder_type: ReminderType
    # contact_id inherited from Base
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_triggered_at: Optional[datetime] = None # Added from model
    snoozed_until: Optional[datetime] = None # Added from model
    relative_delay_minutes: Optional[int] = None # Added from model
    relative_to_task_completion_id: Optional[int] = None # Added from model

    class Config:
        from_attributes = True

# --- Reminder Event Schema ---

class ReminderEvent(BaseModel):
    id: int
    reminder_id: int
    expected_trigger_time: datetime
    action_time: Optional[datetime] = None # Can be null if only triggered?
    action_type: ReminderActionType # Use the Enum from models

    class Config:
        from_attributes = True
        use_enum_values = True # Serialize enum values

# --- Schemas moved from auth.py ---
class TokenData(BaseModel):
    email: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str

# --- Add other schemas later as needed --- 
# e.g., ProjectCreate, TaskCreate, etc. 

# --- Basic Info Schemas (for concise representation) ---

class ProjectBasicInfo(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True

class TaskBasicInfo(BaseModel):
    id: int
    title: str

    class Config:
        from_attributes = True

# --- Update Response Schemas (including unblocked items) ---

class ProjectUpdateResponse(BaseModel):
    updated_project: Project
    unblocked_projects: List[ProjectBasicInfo] = []

class TaskUpdateResponse(BaseModel):
    updated_task: Task
    unblocked_tasks: List[TaskBasicInfo] = [] 

# --- Projects By Category Schemas ---

class CategoryWithProjects(CategoryBase): # Inherit name, description
    id: int
    projects: List[Project] = []

    class Config:
        from_attributes = True

class ProjectsByCategoryResponse(BaseModel):
    categorized: List[CategoryWithProjects] = []
    uncategorized: List[Project] = [] 

# --- Contact Schemas ---

class ContactBase(BaseModel):
    name: str
    email: Optional[EmailStr] = None # Validate email format if provided

class ContactCreate(ContactBase):
    pass

class ContactUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None # Allow updating email

class Contact(ContactBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True 

# --- Note Schemas ---

class NoteBase(BaseModel):
    title: Optional[str] = None
    content: str
    source: Optional[str] = None
    tags: Optional[str] = None # Simple comma-separated tags for now
    contact_id: Optional[int] = None

class NoteCreate(NoteBase):
    pass # Inherits all fields from NoteBase

class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[str] = None 
    contact_id: Optional[int] = None # Allow updating/unsetting contact link

class Note(NoteBase):
    id: int
    owner_id: int
    # contact_id is inherited from NoteBase
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Note Summarization Schemas ---

class NoteSummaryRequest(BaseModel):
    """Request body for summarizing notes.
    At least one filter (note_ids, source, or tags) must be provided.
    """
    note_ids: Optional[List[int]] = Field(None, description="List of specific note IDs to summarize.")
    source: Optional[str] = Field(None, description="Summarize notes from a specific source.")
    tags: Optional[str] = Field(None, description="Summarize notes matching specific tags (comma-separated).")
    max_summary_length: Optional[int] = Field(None, description="Optional hint for maximum summary length (e.g., number of words or tokens). LLM support varies.")

    @model_validator(mode='before')
    @classmethod
    def check_at_least_one_filter(cls, values):
        if not values.get('note_ids') and not values.get('source') and not values.get('tags'):
            raise ValueError("At least one filter (note_ids, source, or tags) must be provided")
        return values

class NoteSummaryResponse(BaseModel):
    """Response body containing the note summary."""
    summary: str
    included_note_ids: List[int]

# --- Outstanding Items Schema ---

class OutstandingItemsResponse(BaseModel):
    tasks: List[Task] = []
    reminders: List[Reminder] = []
    notes: List[Note] = [] # Add notes list

# --- Project Summary Schemas ---

class TaskStatusCounts(BaseModel):
    pending: int = 0
    in_progress: int = 0
    completed: int = 0
    blocked: int = 0
    cancelled: int = 0

class ProjectSummaryResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    status: ProjectStatus
    category_name: Optional[str] = None # Include category name instead of ID
    task_counts: TaskStatusCounts
    file_count: int

    class Config:
        from_attributes = True # Allow mapping from ORM model/dict

# --- File Summary Schema ---

class FileSummaryResponse(BaseModel):
    file_id: int
    summary: Optional[str] = None
    error: Optional[str] = None # Include error message if summarization fails

# ============================================
# Calendar Integration Schemas
# ============================================

class CalendarEventBase(BaseModel):
    """Base schema for calendar event data from Outlook/MS Graph."""
    subject: Optional[str] = Field(None, description="The subject or title of the event.")
    body_preview: Optional[str] = Field(None, description="A short preview of the event body.")
    start_datetime: Optional[datetime] = Field(None, description="The start date and time of the event (timezone aware). Note: Requires parsing from string.")
    end_datetime: Optional[datetime] = Field(None, description="The end date and time of the event (timezone aware). Note: Requires parsing from string.")

class CalendarEventCreate(BaseModel):
    """Schema for creating a new calendar event directly via the API."""
    subject: str = Field(..., description="The subject or title for the new event.")
    start_datetime: datetime = Field(..., description="The start date and time for the event (must be timezone-aware).")
    end_datetime: datetime = Field(..., description="The end date and time for the event (must be timezone-aware).")
    body_content: Optional[str] = Field(None, description="Optional body content for the event.")
    body_content_type: Optional[str] = Field("Text", description="Content type for the body ('Text' or 'HTML'). Defaults to 'Text'.")

    @field_validator('start_datetime', 'end_datetime')
    def check_datetime_timezone_aware(cls, v: datetime):
        if v.tzinfo is None:
            raise ValueError("datetime must be timezone-aware")
        return v

    @model_validator(mode='after')
    def check_end_after_start(self):
        if self.start_datetime and self.end_datetime and self.end_datetime <= self.start_datetime:
            raise ValueError("end_datetime must be after start_datetime")
        return self

class CalendarEventUpdate(BaseModel):
    """Schema for updating an existing calendar event via the API.
    All fields are optional.
    """
    subject: Optional[str] = Field(None, description="The updated subject or title for the event.")
    start_datetime: Optional[datetime] = Field(None, description="The updated start date and time (must be timezone-aware).")
    end_datetime: Optional[datetime] = Field(None, description="The updated end date and time (must be timezone-aware).")
    body_content: Optional[str] = Field(None, description="Updated body content for the event.")
    body_content_type: Optional[str] = Field(None, description="Updated content type ('Text' or 'HTML').") # Note: Graph typically expects contentType with content

    # Validate datetimes are timezone-aware if provided
    @field_validator('start_datetime', 'end_datetime')
    def check_datetime_timezone_aware_optional(cls, v: Optional[datetime]):
        if v is not None and v.tzinfo is None:
            raise ValueError("datetime must be timezone-aware")
        return v

    # Validate end > start only if both are provided in the update
    @model_validator(mode='after')
    def check_end_after_start_optional(self):
        if self.start_datetime and self.end_datetime and self.end_datetime <= self.start_datetime:
            raise ValueError("end_datetime must be after start_datetime")
        return self

class CalendarEvent(CalendarEventBase):
    """Schema for representing a calendar event retrieved via the API."""
    id: str = Field(..., description="The unique identifier for the event from Microsoft Graph.")

    class Config:
        orm_mode = True
        from_attributes=True # Added for Pydantic v2 compatibility
        # Example data for documentation generation
        schema_extra = {
            "example": {
                "id": "AAMkEXAMPLE=",
                "subject": "API Demo Meeting",
                "body_preview": "Discuss integration points.",
                "start_datetime": "2024-08-15T14:00:00Z",
                "end_datetime": "2024-08-15T15:00:00Z"
            }
        }

# --- List Schemas ---

class ListItemBase(BaseModel):
    text: str
    is_checked: bool = False

class ListItemCreate(ListItemBase):
    pass

class ListItemUpdate(ListItemBase):
    text: Optional[str] = None
    is_checked: Optional[bool] = None

class ListItem(ListItemBase):
    id: int
    list_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True # Replaces orm_mode

class ListBase(BaseModel):
    name: str

class ListCreate(ListBase):
    pass

class ListUpdate(ListBase):
    name: Optional[str] = None

class List(ListBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    items: List[ListItem] = [] # Include list items

    class Config:
        from_attributes = True # Replaces orm_mode

# =========================
# Chat Schemas
# =========================

class ChatMessageCreate(BaseModel):
    text: str

class ChatResponse(BaseModel):
    intent: str
    entities: Dict[str, Any]
    response_text: str # Added field for natural language response
    # Optional: Add original text or a response message field later
    # original_text: Optional[str] = None 
    # response_text: Optional[str] = None

# =========================
# End Chat Schemas
# =========================

# --- Schema for updating device token ---
class UserDeviceTokenUpdate(BaseModel):
    device_token: str