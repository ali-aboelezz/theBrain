from fastapi import APIRouter, HTTPException
from app.core import MeetingScheduler
from models.schemas import (
    MeetingRequest,
    ConflictCheck,
    SuggestSlotRequest,
    MeetingDetails,
    ReminderRequest,
    InviteParticipants,
    SmartAgentResponse
)

from transformers import pipeline
import pytz
from dateparser.search import search_dates
import re
from datetime import timedelta

# Load the pre-trained NLP model for zero-shot classification
intent_classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")

# Define possible intents
intents = ["create_meeting", "check_conflicts", "suggest_alternatives", "configure_reminders", "invite_participants"]

router = APIRouter()
scheduler = MeetingScheduler()


def smart_detect_intent(text: str) -> str:
    """
    Detects the intent of the user's message using a pre-trained NLP model.

    :param text: User input message as a string
    :return: Intent string that corresponds to an action (e.g., 'create_meeting')
    """
    # Use the model to classify the input text
    result = intent_classifier(text, candidate_labels=intents)

    # Get the highest score label
    intent = result['labels'][0]
    return intent


def parse_meeting_request(user_input: str, timezone: str):
    results = search_dates(user_input, settings={'PREFER_DATES_FROM': 'future'})
    if not results:
        return None
    meeting_start = results[0][1]

    duration_match = re.search(r'for\s+(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)', user_input, re.IGNORECASE)
    duration_minutes = 60
    if duration_match:
        duration_value = float(duration_match.group(1))
        unit = duration_match.group(2).lower()
        duration_minutes = int(duration_value * 60) if 'hour' in unit else int(duration_value)

    try:
        tz = pytz.timezone(timezone)
    except pytz.UnknownTimeZoneError:
        tz = pytz.UTC

    if meeting_start.tzinfo is None:
        meeting_start = tz.localize(meeting_start)

    meeting_start_utc = meeting_start.astimezone(pytz.UTC)
    meeting_end_utc = meeting_start_utc + timedelta(minutes=duration_minutes)

    return {
        "start": meeting_start_utc.isoformat(),
        "end": meeting_end_utc.isoformat(),
        "timezone": timezone,
        "duration": duration_minutes,
        "summary": "Scheduled Meeting"
    }


@router.post("/smart_agent", response_model=SmartAgentResponse)
def smart_agent(request: MeetingRequest):
    try:
        # Detect the intent of the user's message
        intent = smart_detect_intent(request.user_input)

        # Handle different intents based on the result
        if intent == "create_meeting":
            parsed = parse_meeting_request(request.user_input, request.timezone)
            if not parsed:
                return SmartAgentResponse(action=intent, message="Could not parse meeting details.")
            conflict = scheduler.check_conflicts(parsed["start"], parsed["end"])
            if conflict:
                return SmartAgentResponse(action=intent, message="Conflict detected.", data=parsed)
            event, link = scheduler.add_event_to_calendar(parsed)
            if event:
                scheduler.configure_reminders(event.get("id"))
                if parsed.get("participants"):
                    scheduler.invite_participants(event.get("id"), parsed["participants"])
            return SmartAgentResponse(action=intent, message="Meeting scheduled successfully.",
                                      data={"event_link": event.get("htmlLink"), "meet_link": link})

        elif intent == "check_conflicts":
            parsed = parse_meeting_request(request.user_input, request.timezone)
            if not parsed:
                return SmartAgentResponse(action=intent, message="Could not extract times.")
            conflict = scheduler.check_conflicts(parsed["start"], parsed["end"])
            return SmartAgentResponse(action=intent, message="Conflict found." if conflict else "No conflicts found.")

        elif intent == "suggest_alternatives":
            parsed = parse_meeting_request(request.user_input, request.timezone)
            if not parsed:
                return SmartAgentResponse(action=intent, message="Could not extract meeting date/time.")
            date = parsed["start"][:10]
            slots = scheduler.suggest_alternative_slots(date, parsed["duration"])
            formatted = [{"start": s.isoformat(), "end": e.isoformat()} for s, e in slots]
            return SmartAgentResponse(action=intent, message="Suggestions generated.", data={"slots": formatted})

        else:
            return SmartAgentResponse(action="unknown", message="Could not understand the request.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create_meeting")
def create_meeting(request: MeetingRequest):
    parsed = parse_meeting_request(request.user_input, request.timezone)
    if not parsed:
        raise HTTPException(status_code=400, detail="Parsing failed.")
    return parsed


@router.post("/check_conflicts")
def check_conflicts(request: ConflictCheck):
    conflicts = scheduler.check_conflicts(request.event_start, request.event_end)
    return {"conflicts": conflicts}


@router.post("/suggest_alternative_slots")
def suggest_alternative_slots(request: SuggestSlotRequest):
    slots = scheduler.suggest_alternative_slots(request.event_date, request.duration_minutes)
    return {"slots": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in slots]}


@router.post("/add_event")
def add_event(request: MeetingDetails):
    event, link = scheduler.add_event_to_calendar(request.model_dump())
    if not event:
        raise HTTPException(status_code=500, detail="Add event failed.")
    return {"event_link": event.get("htmlLink"), "meet_link": link}


@router.post("/configure_reminders")
def configure_reminders(request: ReminderRequest):
    scheduler.configure_reminders(request.event_id, request.reminder_minutes)
    return {"message": "Reminders configured successfully."}


@router.post("/invite_participants")
def invite_participants(request: InviteParticipants):
    scheduler.invite_participants(request.event_id, request.participant_emails)
    return {"message": "Participants invited successfully."}
