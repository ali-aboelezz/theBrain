import re
import pytz
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dateparser.search import search_dates
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

# FastAPI application
app = FastAPI()

class MeetingRequest(BaseModel):
    request: str
    timezone: Optional[str] = "UTC"
    add_meet: Optional[bool] = False
    participants: Optional[List[str]] = []

class ReminderRequest(BaseModel):
    event_id: str
    reminder_minutes: Optional[int] = 30

class ParticipantRequest(BaseModel):
    event_id: str
    participant_emails: List[str]

class MeetingSchedulingAgent:
    SCOPES = ['https://www.googleapis.com/auth/calendar']

    def __init__(self) -> None:
        self.service = self.initialize_google_calendar()

    def initialize_google_calendar(self) -> Any:
        """Sets up and returns the Google Calendar API service."""
        try:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', self.SCOPES)
            creds = flow.run_local_server(port=3000)
            return build('calendar', 'v3', credentials=creds)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Google Calendar API: {e}")

    @staticmethod
    def parse_meeting_request(meeting_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a meeting request from API input."""
        user_input = meeting_data.get("request", "")
        results = search_dates(user_input, settings={'PREFER_DATES_FROM': 'future'})
        if not results:
            return None

        meeting_start = results[0][1]

        duration_match = re.search(
            r'for\s+(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)',
            user_input,
            re.IGNORECASE
        )
        duration_minutes = 60 if not duration_match else int(
            float(duration_match.group(1)) * 60 if 'hour' in duration_match.group(2).lower() else float(duration_match.group(1))
        )

        user_timezone = meeting_data.get("timezone", "UTC")
        try:
            tz = pytz.timezone(user_timezone)
        except pytz.UnknownTimeZoneError:
            tz = pytz.UTC
            user_timezone = "UTC"

        if meeting_start.tzinfo is None or meeting_start.tzinfo.utcoffset(meeting_start) is None:
            meeting_start = tz.localize(meeting_start)
        else:
            meeting_start = meeting_start.astimezone(tz)

        meeting_start_utc = meeting_start.astimezone(pytz.UTC)
        meeting_end_utc = meeting_start_utc + timedelta(minutes=duration_minutes)

        return {
            "summary": "Scheduled Meeting",
            "start": meeting_start_utc.isoformat(),
            "end": meeting_end_utc.isoformat(),
            "timezone": user_timezone,
            "add_meet": meeting_data.get("add_meet", False),
            "participants": meeting_data.get("participants", [])
        }

    def add_event_to_calendar(self, event_details: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
        """Adds the event to Google Calendar."""
        event = {
            "summary": event_details["summary"],
            "start": {"dateTime": event_details["start"], "timeZone": event_details["timezone"]},
            "end": {"dateTime": event_details["end"], "timeZone": event_details["timezone"]}
        }
        if event_details.get("add_meet"):
            event["conferenceData"] = {
                "createRequest": {
                    "requestId": f"meeting-{datetime.now().timestamp()}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"}
                }
            }
        try:
            created_event = self.service.events().insert(
                calendarId="primary",
                body=event,
                conferenceDataVersion=1
            ).execute()
            meet_link = created_event.get("conferenceData", {}).get("entryPoints", [{}])[0].get("uri", "No Meet Link")
            return created_event, meet_link
        except Exception as e:
            return None, "No Meet Link"

    def check_conflicts(self, event_start: str, event_end: str) -> bool:
        """Checks for scheduling conflicts."""
        try:
            start_iso = datetime.fromisoformat(event_start).astimezone(timezone.utc).isoformat()
            end_iso = datetime.fromisoformat(event_end).astimezone(timezone.utc).isoformat()

            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=start_iso,
                timeMax=end_iso,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])
            return bool(events)
        except Exception as e:
            return False

    def suggest_alternative_slots(self, event_date: str, duration_minutes: int = 60) -> List[Tuple[datetime, datetime]]:
        """Suggests alternative time slots."""
        try:
            day_start = datetime.fromisoformat(f"{event_date}T00:00:00").astimezone(timezone.utc)
            day_end = datetime.fromisoformat(f"{event_date}T23:59:59").astimezone(timezone.utc)

            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=day_start.isoformat(),
                timeMax=day_end.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])
        except Exception:
            return []

        suggestions: List[Tuple[datetime, datetime]] = []
        previous_end = day_start

        for event in events:
            event_start = datetime.fromisoformat(event['start']['dateTime'])
            event_end = datetime.fromisoformat(event['end']['dateTime'])

            gap_minutes = (event_start - previous_end).total_seconds() / 60
            if gap_minutes >= duration_minutes:
                suggestions.append((previous_end, event_start))

            previous_end = max(previous_end, event_end)

        final_gap_minutes = (day_end - previous_end).total_seconds() / 60
        if final_gap_minutes >= duration_minutes:
            suggestions.append((previous_end, day_end))

        return suggestions

    def configure_reminders(self, event_id: str, reminder_minutes: int = 30) -> None:
        """Configures reminders for the event."""
        try:
            event = self.service.events().get(calendarId="primary", eventId=event_id).execute()
            event["reminders"] = {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": reminder_minutes},
                    {"method": "popup", "minutes": 10}
                ]
            }
            self.service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
        except Exception as e:
            pass

    def invite_participants(self, event_id: str, participant_emails: List[str]) -> None:
        """Invites participants to the event."""
        try:
            event = self.service.events().get(calendarId="primary", eventId=event_id).execute()
            event["attendees"] = [{"email": email} for email in participant_emails if email]
            self.service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
        except Exception as e:
            pass

# Instantiate the scheduling agent
agent = MeetingSchedulingAgent()

@app.post("/schedule_meeting")
def schedule_meeting(request: MeetingRequest):
    meeting_details = agent.parse_meeting_request(request.dict())
    if not meeting_details:
        raise HTTPException(status_code=400, detail="Failed to parse meeting details")

    event, meet_link = agent.add_event_to_calendar(meeting_details)
    if not event:
        raise HTTPException(status_code=500, detail="Failed to create event")

    return {
        "message": "Event created successfully",
        "event_link": event.get("htmlLink"),
        "meet_link": meet_link
    }

@app.post("/configure_reminders")
def configure_reminders(request: ReminderRequest):
    try:
        agent.configure_reminders(request.event_id, request.reminder_minutes)
        return {"message": "Reminders configured successfully"}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to configure reminders")

@app.post("/invite_participants")
def invite_participants(request: ParticipantRequest):
    try:
        agent.invite_participants(request.event_id, request.participant_emails)
        return {"message": "Participants invited successfully"}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to invite participants")