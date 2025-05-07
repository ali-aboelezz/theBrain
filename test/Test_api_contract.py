from fastapi.testclient import TestClient
from main import app
import pytest

client = TestClient(app)

@pytest.fixture
def sample_input():
    """Provide sample input data for testing."""
    return {"chat_messages": ["Please include placeholders like [DATE] and [NAME]."]}

def test_extract_placeholders_from_chat(sample_input):
    """Test the /extract_placeholders_from_chat endpoint."""
    response = client.post("/extract_placeholders_from_chat", json=sample_input)
    assert response.status_code == 200
    assert response.json() == {"placeholders": ["DATE", "NAME"]}

def test_generate_questions():
    """Test the /generate_questions endpoint."""
    data = {"placeholders": ["DATE", "NAME"]}
    response = client.post("/generate_questions", json=data)
    assert response.status_code == 200
    assert "DATE" in response.json()["questions"]
    assert "NAME" in response.json()["questions"]