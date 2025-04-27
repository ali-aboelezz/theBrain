from fastapi.testclient import TestClient
from main import app
import pytest

client = TestClient(app)

@pytest.fixture
def sample_meeting_request():
    return {
        "user_input": "Schedule a meeting on April 20th, 2025 at 3 PM for 2 hours.",
        "timezone": "UTC"
    }

def test_create_meeting(sample_meeting_request):
    response = client.post("/create_meeting", json=sample_meeting_request)
    assert response.status_code == 200
    assert "start" in response.json()

def test_smart_agent_create(sample_meeting_request):
    response = client.post("/smart_agent", json=sample_meeting_request)
    assert response.status_code == 200
    assert "action" in response.json()
