import re
import pytz
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

# Define scopes globally
SCOPES = ['https://www.googleapis.com/auth/calendar']


def initialize_google_calendar() -> Any:
    """
    Set up and return the Google Calendar API service.
    """
    try:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=3000)
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        raise RuntimeError(f"❌ Failed to initialize Google Calendar API: {e}")


def clean_ordinal_suffix(date_str: str) -> str:
    """
    Removes ordinal suffixes (st, nd, rd, th) from dates and capitalizes the month.
    E.g., 'march 20th, 2025' → 'March 20, 2025'
    """
    date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)  # Remove ordinal suffix
    return date_str.title()


def parse_meeting_request(user_input: str) -> Dict[str, Any]:
    """
    Parse a meeting request from user input and generate meeting details.
    Expected input example:
      "Schedule a meeting on March 20th, 2025 at 3:00 PM for 1 hour."
    """
    date_match = re.search(
        r'on ([A-Za-z]+ \d{1,2}(?:st|nd|rd|th)?,? \d{4})',
        user_input,
        re.IGNORECASE
    )
    time_match = re.search(
        r'at (\d{1,2}:\d{2} ?(?:AM|PM)?)',
        user_input,
        re.IGNORECASE
    )
    duration_match = re.search(
        r'for (\d{1,2} ?(?:hours?|hour|min|minutes?))',
        user_input,
        re.IGNORECASE
    )

    if not date_match or not time_match or not duration_match:
        raise ValueError(
            "❌ Error: Could not parse meeting details. "
            "Ensure your input includes a valid date, time, and duration."
        )

    date_str = clean_ordinal_suffix(date_match.group(1))

    try:
        event_date = datetime.strptime(date_str, "%B %d, %Y")
    except ValueError:
        raise ValueError(
            f"❌ Error: Invalid date format detected - '{date_str}'. "
            "Expected format: 'March 20, 2025'."
        )

    try:
        event_time = datetime.strptime(time_match.group(1), "%I:%M %p").time()
    except ValueError:
        raise ValueError(
            f"❌ Error: Invalid time format detected - '{time_match.group(1)}'. "
            "Expected format: '3:00 PM'."
        )

    # Ask user for timezone
    user_timezone = input("Enter your timezone (e.g., 'Africa/Cairo' or 'UTC'): ").strip()
    try:
        tz = pytz.timezone(user_timezone)
    except pytz.UnknownTimeZoneError:
        print("Invalid timezone provided. Defaulting to UTC.")
        user_timezone = "UTC"
        tz = pytz.UTC

    local_datetime = tz.localize(datetime.combine(event_date, event_time))
    event_datetime_utc = local_datetime.astimezone(pytz.UTC)

    # Calculate event end time based on duration
    duration_value = int(re.search(r'\d+', duration_match.group(1)).group())
    duration_unit = "minutes" if "min" in duration_match.group(1).lower() else "hours"
    duration_delta = timedelta(minutes=duration_value) if duration_unit == "minutes" else timedelta(hours=duration_value)
    end_time = event_datetime_utc + duration_delta

    confirmation = input("Do you want to add this event to your calendar? (yes/y/no/n): ").strip().lower()
    if confirmation not in ['yes', 'y']:
        print("Event creation canceled.")
        return {}

    # Ask whether to generate a Google Meet link and capture participant emails if needed
    meet_confirmation = input("Do you want to generate a Google Meet link? (yes/y/no/n): ").strip().lower()
    participant_emails: List[str] = []
    if meet_confirmation in ['yes', 'y']:
        emails_raw = input("Enter participant emails (comma-separated; leave empty if none): ")
        if emails_raw:
            participant_emails = [email.strip() for email in emails_raw.split(',') if email.strip()]

    return {
        "summary": "Scheduled Meeting",
        "start": event_datetime_utc.isoformat(),
        "end": end_time.isoformat(),
        "timezone": user_timezone,
        "add_meet": meet_confirmation in ['yes', 'y'],
        "participants": participant_emails,
    }


def add_event_to_calendar(service: Any, event_details: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """
    Add an event to Google Calendar.
    If Google Meet link generation is requested, include conference data.
    """
    event = {
        'summary': event_details['summary'],
        'start': {'dateTime': event_details['start'], 'timeZone': event_details['timezone']},
        'end': {'dateTime': event_details['end'], 'timeZone': event_details['timezone']},
    }
    if event_details.get('add_meet'):
        event['conferenceData'] = {
            'createRequest': {
                'requestId': f"meeting-{datetime.now().timestamp()}",
                'conferenceSolutionKey': {'type': 'hangoutsMeet'},
            }
        }
    try:
        created_event = service.events().insert(
            calendarId='primary',
            body=event,
            conferenceDataVersion=1
        ).execute()
        meet_link = created_event.get('conferenceData', {}).get('entryPoints', [{}])[0].get('uri', "No Meet Link")
        return created_event, meet_link
    except Exception as e:
        raise RuntimeError(f"❌ Error adding event to calendar: {e}")


def check_conflicts(service: Any, event_start: str, event_end: str) -> bool:
    """
    Check for scheduling conflicts in the calendar during the proposed event time.
    Returns True if conflicts exist.
    """
    try:
        event_start_iso = datetime.fromisoformat(event_start).astimezone(timezone.utc).isoformat()
        event_end_iso = datetime.fromisoformat(event_end).astimezone(timezone.utc).isoformat()

        events_result = service.events().list(
            calendarId='primary',
            timeMin=event_start_iso,
            timeMax=event_end_iso,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        if events:
            print("⚠️ Conflict detected! Existing events:")
            for event in events:
                start_time = event['start'].get('dateTime') or event['start'].get('date')
                end_time = event['end'].get('dateTime') or event['end'].get('date')
                print(f"- {event.get('summary', 'No Title')} from {start_time} to {end_time}")
            return True

        return False
    except Exception as e:
        print(f"❌ Error checking for conflicts: {e}")
        return False





def suggest_alternative_slots(service: Any, event_start: str, event_end: str, duration_minutes: int = 60) -> None:
    """
    Suggest alternative available time slots for a meeting within the given interval that satisfy the required duration.

    The function fetches existing events between event_start and event_end, then:
      - If no events exist, it suggests the entire time window (provided it meets the required duration).
      - If there are events, it calculates gaps between events and suggests any gap that is at least `duration_minutes` long.
      - Additionally, it checks for a gap after the last event until the event_end.

    Parameters:
      service (Any): The Google Calendar API service object.
      event_start (str): The start time of the interval in RFC3339 format.
      event_end (str): The end time of the interval in RFC3339 format.
      duration_minutes (int): The minimum duration (in minutes) required for a suggested slot.

    Returns:
      None. Prints out the suggested time slots.
    """
    try:
        start_dt = datetime.fromisoformat(event_start).astimezone(timezone.utc)
        end_dt = datetime.fromisoformat(event_end).astimezone(timezone.utc)
    except Exception as e:
        print(f"❌ Error parsing input times: {e}")
        return

    # Fetch existing events in the user's calendar in the given interval
    events_result = service.events().list(
        calendarId='primary',
        timeMin=start_dt.isoformat(),
        timeMax=end_dt.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    suggestions: List[Tuple[datetime, datetime]] = []

    # Handle an empty calendar by suggesting the entire window if it meets the duration requirement.
    if not events:
        total_minutes = (end_dt - start_dt).total_seconds() / 60.0
        if total_minutes >= duration_minutes:
            suggestions.append((start_dt, end_dt))
    else:
        # Initialize the first available slot starting from event_start.
        previous_end = start_dt

        for event in events:
            # Handle both all-day events and timed events.
            event_start_str = event['start'].get('dateTime') or (event['start'].get('date') + "T00:00:00+00:00")
            event_end_str = event['end'].get('dateTime') or (event['end'].get('date') + "T23:59:59+00:00")

            try:
                current_start = datetime.fromisoformat(event_start_str)
            except ValueError:
                current_start = datetime.fromisoformat(event_start_str.replace("Z", "+00:00"))

            # Calculate gap in minutes between previous_end and the start of the current event.
            gap_minutes = (current_start - previous_end).total_seconds() / 60.0

            if gap_minutes >= duration_minutes:
                suggestions.append((previous_end, current_start))

            try:
                previous_end = datetime.fromisoformat(event_end_str)
            except ValueError:
                previous_end = datetime.fromisoformat(event_end_str.replace("Z", "+00:00"))

        # After processing all events, check the gap between the end of the last event and event_end.
        final_gap_minutes = (end_dt - previous_end).total_seconds() / 60.0
        if final_gap_minutes >= duration_minutes:
            suggestions.append((previous_end, end_dt))

    # Print out the suggestions.
    if suggestions:
        print("Suggested alternative time slots:")
        for slot in suggestions:
            print(f"- From {slot[0].isoformat()} to {slot[1].isoformat()}")
    else:
        print("No available alternative slots found.")


def configure_reminders(event_id: str, service: Any, reminder_minutes: int = 30) -> Dict[str, Any]:
    """
    Configure email and popup reminders for the created event.
    """
    try:
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
        event['reminders'] = {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': reminder_minutes},
                {'method': 'popup', 'minutes': 10},
            ]
        }
        updated_event = service.events().update(
            calendarId='primary',
            eventId=event_id,
            body=event
        ).execute()
        print("Reminders configured successfully!")
        return updated_event
    except Exception as e:
        print(f"❌ Error configuring reminders: {e}")
        return {}


def invite_participants(service: Any, event_id: str, participant_emails: List[str]) -> Dict[str, Any]:
    """
    Invite participants by adding their email addresses to the event.
    """
    try:
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
        event['attendees'] = [{'email': email} for email in participant_emails if email]
        updated_event = service.events().update(
            calendarId='primary',
            eventId=event_id,
            body=event
        ).execute()
        print("Participants invited successfully!")
        return updated_event
    except Exception as e:
        print(f"❌ Error inviting participants: {e}")
        return {}


def main() -> None:
    print("Initializing Google Calendar...")
    try:
        service = initialize_google_calendar()
    except Exception as e:
        print(e)
        return

    print("Enter your meeting request (e.g., 'Schedule a meeting on March 20th, 2025 at 3:00 PM for 1 hour.')")
    user_input = input("> ")

    print("Parsing meeting details...")
    try:
        meeting_details = parse_meeting_request(user_input)
    except ValueError as ve:
        print(ve)
        return

    # Check if the event creation was canceled by the user.
    if not meeting_details:
        return

    print("Checking for conflicts...")
    conflict = check_conflicts(service, meeting_details['start'], meeting_details['end'])
    if conflict:
        print("Suggesting alternative slots...")
        suggest_alternative_slots(service, meeting_details['start'], meeting_details['end'])
        return

    print("Adding event to Google Calendar...")
    try:
        event, meet_link = add_event_to_calendar(service, meeting_details)
        print(f"Event created: {event.get('htmlLink')}")
        if meeting_details.get('add_meet'):
            print(f"Google Meet link: {meet_link}")
    except Exception as e:
        print(e)
        return

    print("Configuring reminders...")
    configure_reminders(event['id'], service)

    if meeting_details.get('participants'):
        invite_participants(service, event['id'], meeting_details['participants'])

    print("All tasks completed successfully!")


if __name__ == "__main__":
    main()
