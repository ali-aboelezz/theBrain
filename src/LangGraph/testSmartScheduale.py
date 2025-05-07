import re
import pytz
import dateparser
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from dateparser.search import search_dates
from timezonefinder import TimezoneFinder
from geopy.geocoders import Nominatim
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow


class MeetingSchedulingAgent:
    SCOPES = ['https://www.googleapis.com/auth/calendar']

    def __init__(self) -> None:
        print("Initializing Google Calendar API...")
        self.service = self.initialize_google_calendar()

    def initialize_google_calendar(self) -> Any:
        try:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', self.SCOPES)
            creds = flow.run_local_server(port=3000)
            service = build('calendar', 'v3', credentials=creds)
            print("Google Calendar API initialized.")
            return service
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Google Calendar API: {e}")

    @staticmethod
    def parse_meeting_request(user_input: str) -> Optional[Dict[str, Any]]:
        tf = TimezoneFinder()
        geolocator = Nominatim(user_agent="timezone_locator")

        # Step 1: Detect date/time
        results = search_dates(user_input, settings={'PREFER_DATES_FROM': 'future'})
        if results:
            meeting_start = results[0][1]
        else:
            date_input = input("📅 Please provide the meeting date and time (e.g., 'April 30, 2025 at 3 PM'): ")
            results = search_dates(date_input, settings={'PREFER_DATES_FROM': 'future'})
            if results:
                meeting_start = results[0][1]
            else:
                print("❌ Could not detect meeting time. Exiting.")
                return None

        # Step 2: Detect duration
        duration_match = re.search(
            r'for\s+(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)',
            user_input,
            re.IGNORECASE
        )
        if duration_match:
            duration_value = float(duration_match.group(1))
            unit = duration_match.group(2).lower()
            duration_minutes = int(duration_value * 60) if ('hour' in unit or 'hr' in unit) else int(duration_value)
        else:
            duration_input = input("⏱️ Meeting duration missing. How long is the meeting? (e.g., '30 minutes' or '1 hour'): ")
            duration_match = re.search(r'(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)', duration_input, re.IGNORECASE)
            if duration_match:
                duration_value = float(duration_match.group(1))
                unit = duration_match.group(2).lower()
                duration_minutes = int(duration_value * 60) if ('hour' in unit or 'hr' in unit) else int(duration_value)
            else:
                print("⏱️ Defaulting meeting duration to 60 minutes.")
                duration_minutes = 60

        # Step 3: Detect timezone smartly
        timezone_match = re.search(r'\b([A-Za-z]+/[A-Za-z_]+)\b', user_input)
        if timezone_match:
            user_timezone = timezone_match.group(1)
        else:
            # Try to guess from city
            city_match = re.search(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', user_input)
            if city_match:
                city_name = city_match.group(1)
                try:
                    location = geolocator.geocode(city_name)
                    if location:
                        lat, lng = location.latitude, location.longitude
                        guessed_timezone = tf.timezone_at(lng=lng, lat=lat)
                        user_timezone = guessed_timezone or "UTC"
                    else:
                        user_timezone = input("🌍 Cannot detect timezone from city. Please enter timezone (e.g., 'Africa/Cairo'): ").strip()
                except Exception as e:
                    print(f"⚠️ Error detecting city timezone: {e}")
                    user_timezone = input("🌍 Please enter your timezone (e.g., 'Africa/Cairo'): ").strip()
            else:
                user_timezone = input("🌍 Please enter your timezone (e.g., 'Africa/Cairo'): ").strip()

        try:
            tz = pytz.timezone(user_timezone)
        except pytz.UnknownTimeZoneError:
            print("⚠️ Invalid timezone. Defaulting to UTC.")
            tz = pytz.UTC
            user_timezone = "UTC"

        # Step 4: Localize time
        if meeting_start.tzinfo is None or meeting_start.tzinfo.utcoffset(meeting_start) is None:
            meeting_start = tz.localize(meeting_start)
        else:
            meeting_start = meeting_start.astimezone(tz)

        # Step 5: Detect participant emails smartly
        participant_emails = re.findall(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            user_input,
            re.IGNORECASE
        )

        if not participant_emails:
            emails_raw = input("📧 I couldn't find any participant emails. Please enter them (comma-separated; or leave empty): ").strip()
            if emails_raw:
                participant_emails = [email.strip() for email in emails_raw.split(',') if email.strip()]

        # Step 6: Final event object
        meeting_start_utc = meeting_start.astimezone(pytz.UTC)
        meeting_end_utc = meeting_start_utc + timedelta(minutes=duration_minutes)

        return {
            "summary": "Scheduled Meeting",
            "start": meeting_start_utc.isoformat(),
            "end": meeting_end_utc.isoformat(),
            "timezone": user_timezone,
            "add_meet": True,  # Always create Meet link
            "participants": participant_emails
        }

    def add_event_to_calendar(self, event_details: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
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
            print(f"❌ Error adding event: {e}")
            return None, "No Meet Link"

    def configure_reminders(self, event_id: str, reminder_minutes: int = 30) -> None:
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
            print("Reminders configured successfully!")
        except Exception as e:
            print(f"❌ Error configuring reminders: {e}")

    def invite_participants(self, event_id: str, participant_emails: List[str]) -> None:
        try:
            event = self.service.events().get(calendarId="primary", eventId=event_id).execute()
            event["attendees"] = [{"email": email} for email in participant_emails if email]
            self.service.events().update(
                calendarId="primary", eventId=event_id, body=event
            ).execute()
            print("Participants invited successfully!")
        except Exception as e:
            print(f"❌ Error inviting participants: {e}")

    def run(self) -> None:
        print("\n👋 Hello! I am your smart Meeting Scheduling Agent.")
        user_input = input(
            "📝 Tell me about your meeting (e.g., 'Schedule a meeting with ali@example.com tomorrow at 3PM in Paris for 1 hour'): "
        )

        meeting_details = self.parse_meeting_request(user_input)
        if not meeting_details:
            print("❌ Could not complete meeting setup.")
            return

        print("\n✅ Finalized Meeting Details:")
        for key, value in meeting_details.items():
            print(f"👉 {key}: {value}")

        print("\n📅 Adding event to your Google Calendar...")
        event, meet_link = self.add_event_to_calendar(meeting_details)
        if event:
            print(f"✅ Event created: {event.get('htmlLink')}")
            if meeting_details.get("add_meet"):
                print(f"🎥 Google Meet Link: {meet_link}")
        else:
            print("❌ Failed to create event.")
            return

        print("\n⏰ Setting reminders...")
        self.configure_reminders(event.get("id"))

        if meeting_details.get("participants"):
            print("📧 Inviting participants...")
            self.invite_participants(event.get("id"), meeting_details["participants"])

        print("\n🎉 Meeting successfully scheduled!")


if __name__ == "__main__":
    agent = MeetingSchedulingAgent()
    agent.run()
