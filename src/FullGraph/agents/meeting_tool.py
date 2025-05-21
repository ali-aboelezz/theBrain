from langchain_core.tools import tool
from agents.testSmartScheduale import MeetingSchedulingAgent

@tool
def schedule_meeting() -> str:
    """
    Interactively schedules a meeting via Google Calendar.
    Returns confirmation and Meet link if available.
    """
    print("📅 [Tool] Starting meeting scheduling...")
    agent = MeetingSchedulingAgent()
    agent.run()
    return "✅ Meeting scheduled."