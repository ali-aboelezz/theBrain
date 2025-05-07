from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict

class MeetingRequest(BaseModel):
    user_input: str
    timezone: str

class ConflictCheck(BaseModel):
    event_start: str
    event_end: str

class SuggestSlotRequest(BaseModel):
    event_date: str
    duration_minutes: int = 60

class MeetingDetails(BaseModel):
    summary: str
    start: str
    end: str
    timezone: str
    add_meet: Optional[bool] = False
    participants: Optional[List[EmailStr]] = []

class ReminderRequest(BaseModel):
    event_id: str
    reminder_minutes: int = 30

class InviteParticipants(BaseModel):
    event_id: str
    participant_emails: List[str]

class SmartAgentResponse(BaseModel):
    action: str
    message: str
    data: Optional[Dict] = None
