import pytest
from datetime import datetime
from zoltar_backend.schemas import ReminderCreate, ReminderType


def test_one_time_clears_recurrence_rule():
    """Ensure that creating a ONE_TIME reminder with a recurrence_rule clears the rule."""
    payload = {
        "title": "Test OneTime With Rule",
        "trigger_datetime": datetime.utcnow().isoformat(),
        "recurrence_rule": "FREQ=DAILY;COUNT=5"
    }
    reminder = ReminderCreate(**payload)
    assert reminder.reminder_type == ReminderType.ONE_TIME
    assert reminder.recurrence_rule is None


def test_recurring_requires_rule():
    """Ensure that creating a RECURRING_SCHEDULED reminder without a rule raises ValueError."""
    payload = {
        "title": "Test Recurring Without Rule",
        "trigger_datetime": datetime.utcnow().isoformat(),
        "reminder_type": ReminderType.RECURRING_SCHEDULED
    }
    with pytest.raises(ValueError):
        ReminderCreate(**payload)


def test_reminder_type_case_insensitive_name():
    """Ensure that uppercase enum names are normalized to ReminderType."""
    payload = {
        "title": "Test Case Insensitive Name",
        "trigger_datetime": datetime.utcnow().isoformat(),
        "reminder_type": "RECURRING_SCHEDULED",
        "recurrence_rule": "FREQ=DAILY;COUNT=1"
    }
    reminder = ReminderCreate(**payload)
    assert reminder.reminder_type == ReminderType.RECURRING_SCHEDULED


def test_reminder_type_case_insensitive_value():
    """Ensure that lowercase enum values are accepted for reminder_type."""
    payload = {
        "title": "Test Case Insensitive Value",
        "trigger_datetime": datetime.utcnow().isoformat(),
        "reminder_type": "recurring_scheduled",
        "recurrence_rule": "FREQ=DAILY;COUNT=1"
    }
    reminder = ReminderCreate(**payload)
    assert reminder.reminder_type == ReminderType.RECURRING_SCHEDULED


def test_invalid_reminder_type_raises():
    """Ensure that an invalid reminder_type string raises ValueError."""
    payload = {
        "title": "Test Invalid Reminder Type",
        "trigger_datetime": datetime.utcnow().isoformat(),
        "reminder_type": "INVALID_TYPE"
    }
    with pytest.raises(ValueError):
        ReminderCreate(**payload) 