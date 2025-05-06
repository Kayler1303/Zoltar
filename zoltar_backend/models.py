import enum
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, ForeignKey, Boolean, Enum, Text, Table, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

# Association table for task dependencies (many-to-many)
task_dependency = Table('task_dependency',
    Base.metadata,
    Column('task_id', Integer, ForeignKey('tasks.id'), primary_key=True),
    Column('depends_on_task_id', Integer, ForeignKey('tasks.id'), primary_key=True)
)

# Association table for project dependencies (many-to-many)
project_dependency = Table('project_dependency',
    Base.metadata,
    Column('project_id', Integer, ForeignKey('projects.id'), primary_key=True),
    Column('depends_on_project_id', Integer, ForeignKey('projects.id'), primary_key=True)
)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # --- Microsoft Graph OAuth Fields ---
    ms_oid = Column(String, unique=True, index=True, nullable=True) # Microsoft User Object ID
    ms_token_cache = Column(Text, nullable=True) # Store serialized MSAL token cache
    # --- End Microsoft Graph OAuth Fields ---

    # --- Add device_token field ---
    device_token = Column(String, nullable=True, index=True) # Indexed for faster lookup
    # --- End Add ---

    projects = relationship("Project", back_populates="owner")
    categories = relationship("Category", back_populates="owner")
    tasks = relationship("Task", back_populates="owner")
    reminders = relationship("Reminder", back_populates="owner")
    notes = relationship("Note", back_populates="owner")
    file_references = relationship("FileReference", back_populates="owner")
    contacts = relationship("Contact", back_populates="owner")
    lists = relationship("List", back_populates="owner")

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="categories")
    projects = relationship("Project", back_populates="category")

class ProjectStatus(enum.Enum):
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(ProjectStatus), default=ProjectStatus.ACTIVE, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", back_populates="projects")
    category = relationship("Category", back_populates="projects")
    tasks = relationship("Task", back_populates="project")
    file_references = relationship("FileReference", back_populates="project")
    # Project dependencies
    dependent_projects = relationship(
        "Project",
        secondary=project_dependency,
        primaryjoin=id == project_dependency.c.project_id,
        secondaryjoin=id == project_dependency.c.depends_on_project_id,
        backref="dependency_projects"
    )

class TaskStatus(enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    due_date = Column(DateTime(timezone=True), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    owner = relationship("User", back_populates="tasks")
    project = relationship("Project", back_populates="tasks")
    contact = relationship("Contact", back_populates="tasks")
    reminders = relationship("Reminder", back_populates="task", foreign_keys='Reminder.task_id')
    file_references = relationship("FileReference", back_populates="task", foreign_keys='FileReference.task_id')
    # Task dependencies
    dependent_tasks = relationship(
        "Task",
        secondary=task_dependency,
        primaryjoin=id == task_dependency.c.task_id,
        secondaryjoin=id == task_dependency.c.depends_on_task_id,
        backref="dependency_tasks"
    )

class ReminderType(enum.Enum):
    ONE_TIME = "one_time"
    RECURRING_SCHEDULED = "recurring_scheduled" # e.g., every Monday 9am
    RECURRING_RELATIVE = "recurring_relative"   # e.g., every 2 weeks from completion

# Enum for Reminder Event Actions
class ReminderActionType(enum.Enum):
    TRIGGERED = "triggered" # System triggered a notification
    COMPLETED = "completed" # User marked as completed
    SKIPPED = "skipped"     # User skipped this instance
    # SNOOZED is handled by snoozed_until on Reminder model

class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=True, index=True)
    description = Column(Text, nullable=True)
    reminder_type = Column(Enum(ReminderType), default=ReminderType.ONE_TIME, nullable=False)
    trigger_datetime = Column(DateTime(timezone=True), nullable=True, index=True) # Allow NULL for relative reminders
    recurrence_rule = Column(String, nullable=True) # e.g., RRULE string, or custom format
    remind_frequency_minutes = Column(Integer, nullable=True) # For persistent re-reminders
    relative_delay_minutes = Column(Integer, nullable=True) # For relative dependencies
    relative_to_task_completion_id = Column(Integer, ForeignKey('tasks.id'), nullable=True)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True) # Renaming might be complex for Alembic, keep for now?
    last_notified_at = Column(DateTime(timezone=True), nullable=True) # Track last notification time for persistent reminders
    is_active = Column(Boolean, default=True, index=True) # Add index
    snoozed_until = Column(DateTime(timezone=True), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True) # Optional link to a task
    file_reference_id = Column(Integer, ForeignKey('file_references.id'), nullable=True) # Optional link to a file
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", back_populates="reminders")
    task = relationship("Task", back_populates="reminders", foreign_keys=[task_id])
    file_reference = relationship("FileReference", back_populates="reminders")
    relative_to_task_completion = relationship("Task", foreign_keys=[relative_to_task_completion_id])
    contact = relationship("Contact", back_populates="reminders")
    events = relationship("ReminderEvent", back_populates="reminder", cascade="all, delete-orphan") # Add relationship to events

# New table to track reminder instance events
class ReminderEvent(Base):
    __tablename__ = "reminder_events"
    id = Column(Integer, primary_key=True, index=True)
    reminder_id = Column(Integer, ForeignKey("reminders.id"), nullable=False, index=True)
    expected_trigger_time = Column(DateTime(timezone=True), nullable=False, index=True) # When this instance was *supposed* to trigger
    action_time = Column(DateTime(timezone=True), nullable=True) # When the action (trigger, complete, skip) occurred
    action_type = Column(Enum(ReminderActionType), nullable=False)

    reminder = relationship("Reminder", back_populates="events")

class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=True)
    content = Column(Text, nullable=False)
    source = Column(String, nullable=True) # e.g., Book title, meeting name
    tags = Column(String, nullable=True) # Simple comma-separated tags for now
    owner_id = Column(Integer, ForeignKey("users.id"))
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", back_populates="notes")
    contact = relationship("Contact", back_populates="notes")

class FileReference(Base):
    __tablename__ = "file_references"
    id = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=False, unique=True) # Path in S3, GCS, etc.
    file_type = Column(String, nullable=True) # e.g., 'pdf', 'email', 'xlsx'
    file_size = Column(Integer, nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="file_references")
    project = relationship("Project", back_populates="file_references", foreign_keys=[project_id])
    task = relationship("Task", back_populates="file_references", foreign_keys=[task_id])
    reminders = relationship("Reminder", back_populates="file_reference")

# +++ Contact Model +++
class Contact(Base):
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    email = Column(String, index=True, nullable=True) # Optional email
    owner_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", back_populates="contacts")
    # Add relationships to tasks, reminders, notes that refer to this contact
    tasks = relationship("Task", back_populates="contact")
    reminders = relationship("Reminder", back_populates="contact")
    notes = relationship("Note", back_populates="contact")

# --- New List Models ---

class List(Base):
    __tablename__ = "lists"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User") # Relationship to User (optional, can be added if needed later)
    items = relationship("ListItem", back_populates="list", cascade="all, delete-orphan")


class ListItem(Base):
    __tablename__ = "list_items"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(String, nullable=False)
    list_id = Column(Integer, ForeignKey("lists.id"), nullable=False, index=True)
    is_checked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    list = relationship("List", back_populates="items") 