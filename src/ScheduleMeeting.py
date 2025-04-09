import re
import pytz
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from dateparser.search import search_dates  # Open-source library for natural language date parsing
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

class MeetingSchedulingAgent:
    SCOPES = ['https://www.googleapis.com/auth/calendar']

    def __init__(self) -> None:
        print("Initializing Google Calendar API...")
        self.service = self.initialize_google_calendar()

    def initialize_google_calendar(self) -> Any:
        """
        Sets up and returns the Google Calendar API service.
        """
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
        """
        Parse a meeting request from free-form natural language using the open-source dateparser API.

        This function extracts the meeting's start date/time intelligently, handling a variety of
        formats (e.g., 'tomorrow at 3 PM', 'next Friday 14:00', 'March 20th, 2025 at 3:00 PM', etc.).
        It also extracts the duration using a flexible regex.

        If the date/time lacks timezone information, the user is prompted for their timezone.

        Parameters:
          user_input (str): The meeting request text.
        Returns:
          Optional[Dict[str, Any]]: A dictionary with keys "summary", "start", "end", "timezone",
                                    "add_meet", and "participants", or None if parsing fails or is canceled.
        """
        # Use dateparser's search functionality to extract date/time information.
        results = search_dates(user_input, settings={'PREFER_DATES_FROM': 'future'})
        if not results:
            print("❌ Error: Could not detect date and time from your meeting request.")
            return None

        # Choose the first detected date/time occurrence as the meeting start.
        meeting_start = results[0][1]

        # Enhance duration extraction: matches numbers (with or without decimals) with various units.
        duration_match = re.search(
            r'for\s+(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)',
            user_input,
            re.IGNORECASE
        )
        if not duration_match:
            print("Duration not specified. Defaulting to 60 minutes.")
            duration_minutes = 60
        else:
            duration_value = float(duration_match.group(1))
            unit = duration_match.group(2).lower()
            duration_minutes = int(duration_value * 60) if ('hour' in unit or 'hr' in unit) else int(duration_value)

        # Prompt for timezone in case the parsed date is naive (or to enforce user preference).
        user_timezone = input("Enter your timezone (e.g., 'Africa/Cairo' or 'UTC'): ").strip()
        try:
            tz = pytz.timezone(user_timezone)
        except pytz.UnknownTimeZoneError:
            print("Invalid timezone provided. Defaulting to UTC.")
            user_timezone = "UTC"
            tz = pytz.UTC

        # If parsed meeting_start is naive, assign the provided timezone.
        if meeting_start.tzinfo is None or meeting_start.tzinfo.utcoffset(meeting_start) is None:
            meeting_start = tz.localize(meeting_start)
        else:
            meeting_start = meeting_start.astimezone(tz)

        # Convert meeting start to UTC — to be used when creating the event.
        meeting_start_utc = meeting_start.astimezone(pytz.UTC)
        meeting_end_utc = meeting_start_utc + timedelta(minutes=duration_minutes)

        confirmation = input("Do you want to add this event to your calendar? (yes/y/no/n): ").strip().lower()
        if confirmation not in ['yes', 'y']:
            print("Event creation canceled.")
            return None

        meet_confirmation = input("Do you want to generate a Google Meet link? (yes/y/no/n): ").strip().lower()
        participant_emails: List[str] = []
        if meet_confirmation in ['yes', 'y']:
            emails_raw = input("Enter participant emails (comma-separated; leave empty if none): ").strip()
            if emails_raw:
                participant_emails = [email.strip() for email in emails_raw.split(',') if email.strip()]

        return {
            "summary": "Scheduled Meeting",
            "start": meeting_start_utc.isoformat(),
            "end": meeting_end_utc.isoformat(),
            "timezone": user_timezone,
            "add_meet": meet_confirmation in ['yes', 'y'],
            "participants": participant_emails
        }

    def check_conflicts(self, event_start: str, event_end: str) -> bool:
        """
        Checks for scheduling conflicts between the given start and end times.

        Returns:
            True if conflicts are found, False otherwise.
        """
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
            if events:
                print("⚠️ Conflict detected! Existing events:")
                for event in events:
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    end = event['end'].get('dateTime', event['end'].get('date'))
                    print(f"- {event.get('summary', 'No Title')} from {start} to {end}")
                return True
            return False
        except Exception as e:
            print(f"❌ Error checking conflicts: {e}")
            return False

    def suggest_alternative_slots(self, event_date: str, duration_minutes: int = 60) -> List[Tuple[datetime, datetime]]:
        """
        Suggests alternative time slots within the same day that fit the required duration.

        Args:
            event_date (str): Date of the event in 'YYYY-MM-DD' format.
            duration_minutes (int): Desired duration of the meeting in minutes.

        Returns:
            List of tuples (start_datetime, end_datetime) representing alternative slots.
        """
        try:
            # Create start and end datetime for the full day
            day_start = datetime.fromisoformat(f"{event_date}T00:00:00").astimezone(timezone.utc)
            day_end = datetime.fromisoformat(f"{event_date}T23:59:59").astimezone(timezone.utc)
            print(f"✅ Checking the entire day: {day_start} to {day_end}")
        except Exception as e:
            print(f"❌ Error parsing date: {e}")
            return []

        # Fetch all events for the entire day
        try:
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=day_start.isoformat(),
                timeMax=day_end.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
            print(f"✅ Events fetched: {len(events)}")
        except Exception as e:
            print(f"❌ Error fetching events: {e}")
            return []

        suggestions: List[Tuple[datetime, datetime]] = []
        previous_end = day_start

        for event in events:
            event_start_str = event['start'].get('dateTime') or (event['start'].get('date') + "T00:00:00+00:00")
            event_end_str = event['end'].get('dateTime') or (event['end'].get('date') + "T23:59:59+00:00")

            try:
                current_start = datetime.fromisoformat(event_start_str).astimezone(timezone.utc)
                current_end = datetime.fromisoformat(event_end_str).astimezone(timezone.utc)
            except Exception as ve:
                print(f"❌ Error parsing event times: {ve}")
                continue

            print(f"📅 Event - Start (UTC): {current_start}, End (UTC): {current_end}")

            # Calculate the gap before the current event
            gap_minutes = (current_start - previous_end).total_seconds() / 60
            if gap_minutes >= duration_minutes:
                suggestions.append((previous_end, current_start))

            # Move previous_end forward
            previous_end = max(previous_end, current_end)

        # Check for a gap after the last event till the end of the day
        final_gap_minutes = (day_end - previous_end).total_seconds() / 60
        if final_gap_minutes >= duration_minutes:
            suggestions.append((previous_end, day_end))

        # Print suggestions
        if suggestions:
            print("✅ Suggested alternative time slots:")
            for slot in suggestions:
                print(f" - From {slot[0].isoformat()} to {slot[1].isoformat()}")
        else:
            print("⚠️ No available alternative slots found for the day.")

        return suggestions

    def add_event_to_calendar(self, event_details: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Adds the event to Google Calendar, optionally generating a Google Meet link.
        """
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
        """
        Configures email and popup reminders for the given event.
        """
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
        """
        Invites participants by updating the event with their email addresses.
        """
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
        """
        Main loop for the agent. It interacts with the user, processes the meeting request,
        and executes scheduling tasks.
        """
        print("\n👋 Hello! I am your Meeting Scheduling Agent. How can I assist you today?")
        user_input = input(
            "📝 Enter your meeting request (e.g., 'Schedule a meeting on March 20th, 2025 at 3:00 PM for 1 hour.'): "
        )

        # Parse user input
        meeting_details = self.parse_meeting_request(user_input)
        if not meeting_details:
            print("❌ Failed to parse meeting details. Please try again with the correct format.")
            return

        # Display parsed details
        print("\n✅ Parsed Meeting Details:")
        for key, value in meeting_details.items():
            print(f"👉 {key}: {value}")

        # Check for scheduling conflicts
        print("\n🔎 Checking for scheduling conflicts...")
        conflict_exists = self.check_conflicts(meeting_details["start"], meeting_details["end"])

        if conflict_exists:
            print("⚠️ Conflict detected! Suggesting alternative time slots...")

            # Extract date from start time to pass properly
            event_date = meeting_details["start"].split("T")[0]
            suggestions = self.suggest_alternative_slots(event_date=event_date,
                                                         duration_minutes=meeting_details.get("duration", 60))

            if suggestions:
                print("\n✅ Available alternative slots:")
                for start, end in suggestions:
                    print(f"🕒 From {start.strftime('%Y-%m-%d %H:%M')} to {end.strftime('%Y-%m-%d %H:%M')}")
            else:
                print("❌ No available alternative slots found for the same day.")
            return

        # No conflict - Proceed to schedule the event
        print("\n📅 Adding event to your Google Calendar...")
        event, meet_link = self.add_event_to_calendar(meeting_details)
        if event:
            print(f"✅ Event created: {event.get('htmlLink')}")
            if meeting_details.get("add_meet"):
                print(f"🎥 Google Meet Link: {meet_link}")
        else:
            print("❌ Failed to create event.")
            return

        # Configure reminders if event is created
        print("\n⏰ Configuring reminders...")
        self.configure_reminders(event.get("id"))

        # Invite participants if any
        if meeting_details.get("participants"):
            print("📧 Inviting participants...")
            self.invite_participants(event.get("id"), meeting_details["participants"])

        print("\n✅ All tasks completed successfully! 🎉")


if __name__ == "__main__":
    agent = MeetingSchedulingAgent()
    agent.run()
