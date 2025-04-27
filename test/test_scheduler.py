import pytest
from app.core import MeetingScheduler
from datetime import datetime, timedelta

@pytest.fixture
def scheduler():
    return MeetingScheduler()

def test_parse_meeting_request(scheduler):
    user_input = "Schedule a meeting on April 20th, 2025 at 3 PM for 2 hours."
    timezone = "UTC"
    details = scheduler.parse_meeting_request(user_input, timezone)
    assert details is not None
    assert details["start"].startswith("2025-04-20T15:00:00")
    assert details["end"].startswith("2025-04-20T17:00:00")

def test_detect_intent(scheduler):
    assert scheduler.smart_detect_intent("schedule a meeting") == "create_meeting"
    assert scheduler.smart_detect_intent("check if busy") == "check_conflicts"
