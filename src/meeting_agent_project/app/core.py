import re
import pytz
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from dateparser.search import search_dates
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
import logging
import os
import logging

# Configure logging
# Ensure the 'logs' directory exists
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/meeting_agent.log",  # Path where the log file will be created
    level=logging.INFO,  # Set the logging level (INFO, DEBUG, etc.)
    format="%(asctime)s - %(levelname)s - %(message)s"  # Log format
)


class MeetingScheduler:
    SCOPES = ['https://www.googleapis.com/auth/calendar']

    def __init__(self) -> None:
        logging.info("Initializing Google Calendar API...")
        self.service = self.initialize_google_calendar()

    def initialize_google_calendar(self) -> Any:
        """Initialize the Google Calendar API service."""
        try:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', self.SCOPES)
            creds = flow.run_local_server(port=3000)
            service = build('calendar', 'v3', credentials=creds)
            logging.info("Google Calendar API initialized.")
            return service
        except Exception as e:
            logging.error(f"Failed to initialize Google Calendar API: {e}")
            raise RuntimeError(f"Failed to initialize Google Calendar API: {e}")

    @staticmethod
    def parse_meeting_request(user_input: str, user_timezone: str) -> Optional[Dict[str, Any]]:
        """Parse natural language meeting requests to extract relevant details."""
        try:
            results = search_dates(user_input, settings={'PREFER_DATES_FROM': 'future'})
            if not results:
                logging.warning("Could not detect date and time from input.")
                return None

            meeting_start = results[0][1]

            duration_match = re.search(
                r'for\s+(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)',
                user_input,
                re.IGNORECASE
            )
            duration_minutes = 60  # Default duration
            if duration_match:
                duration_value = float(duration_match.group(1))
                unit = duration_match.group(2).lower()
                duration_minutes = int(duration_value * 60) if 'hour' in unit else int(duration_value)

            try:
                tz = pytz.timezone(user_timezone)
            except pytz.UnknownTimeZoneError:
                logging.warning("Invalid timezone provided. Defaulting to UTC.")
                tz = pytz.UTC

            if meeting_start.tzinfo is None:
                meeting_start = tz.localize(meeting_start)

            meeting_start_utc = meeting_start.astimezone(pytz.UTC)
            meeting_end_utc = meeting_start_utc + timedelta(minutes=duration_minutes)

            return {
                "start": meeting_start_utc.isoformat(),
                "end": meeting_end_utc.isoformat(),
                "timezone": user_timezone,
                "duration": duration_minutes
            }
        except Exception as e:
            logging.error(f"Error parsing meeting request: {e}")
            return None

    def check_conflicts(self, event_start: str, event_end: str) -> bool:
        """Check for scheduling conflicts."""
        try:
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=event_start,
                timeMax=event_end,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])
            if events:
                logging.info("Conflict detected with the following events:")
                for event in events:
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    end = event['end'].get('dateTime', event['end'].get('date'))
                    logging.info(f"- {event.get('summary', 'No Title')} from {start} to {end}")
                return True
            return False
        except Exception as e:
            logging.error(f"Error checking conflicts: {e}")
            return False

    def suggest_alternative_slots(self, event_date: str, duration_minutes: int = 60) -> List[Tuple[datetime, datetime]]:
        """Suggest alternative time slots for a meeting."""
        try:
            day_start = datetime.fromisoformat(f"{event_date}T00:00:00").astimezone(timezone.utc)
            day_end = datetime.fromisoformat(f"{event_date}T23:59:59").astimezone(timezone.utc)
            logging.info(f"Checking entire day: {day_start} to {day_end}")
        except Exception as e:
            logging.error(f"Error parsing date: {e}")
            return []

        try:
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=day_start.isoformat(),
                timeMax=day_end.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
        except Exception as e:
            logging.error(f"Error fetching events: {e}")
            return []

        suggestions = []
        previous_end = day_start

        for event in events:
            try:
                event_start = datetime.fromisoformat(event['start'].get('dateTime')).astimezone(timezone.utc)
                event_end = datetime.fromisoformat(event['end'].get('dateTime')).astimezone(timezone.utc)
            except Exception as ve:
                logging.warning(f"Error parsing event times: {ve}")
                continue

            gap_minutes = (event_start - previous_end).total_seconds() / 60
            if gap_minutes >= duration_minutes:
                suggestions.append((previous_end, event_start))

            previous_end = max(previous_end, event_end)

        final_gap_minutes = (day_end - previous_end).total_seconds() / 60
        if final_gap_minutes >= duration_minutes:
            suggestions.append((previous_end, day_end))

        return suggestions

    def add_event_to_calendar(self, event_details: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
        """Add an event to Google Calendar."""
        event = {
            "summary": event_details["summary"],
            "start": {"dateTime": event_details["start"], "timeZone": event_details["timezone"]},
            "end": {"dateTime": event_details["end"], "timeZone": event_details["timezone"]},
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
            logging.error(f"Error adding event to calendar: {e}")
            return None, "No Meet Link"

    def configure_reminders(self, event_id: str, reminder_minutes: int = 30) -> None:
        """Configure reminders for an event."""
        try:
            event = self.service.events().get(calendarId="primary", eventId=event_id).execute()
            event["reminders"] = {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": reminder_minutes},
                    {"method": "popup", "minutes": 10}
                ]
            }
            self.service.events().update(
                calendarId="primary", eventId=event_id, body=event
            ).execute()
            logging.info("Reminders configured successfully!")
        except Exception as e:
            logging.error(f"Error configuring reminders: {e}")

    def invite_participants(self, event_id: str, participant_emails: List[str]) -> None:
        """Invite participants to an event."""
        try:
            event = self.service.events().get(calendarId="primary", eventId=event_id).execute()
            event["attendees"] = [{"email": email} for email in participant_emails if email]
            self.service.events().update(
                calendarId="primary", eventId=event_id, body=event
            ).execute()
            logging.info("Participants invited successfully!")
        except Exception as e:
            logging.error(f"Error inviting participants: {e}")