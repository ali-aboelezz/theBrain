import pytest
from unittest.mock import patch, MagicMock
from src.DocumentOrganizationAgent import DocumentIntelligencePipeline

@pytest.fixture
def pipeline():
    return DocumentIntelligencePipeline()

@patch("smtplib.SMTP")
def test_send_email_success(mock_smtp, pipeline):
    mock_instance = MagicMock()
    mock_smtp.return_value = mock_instance

    result = pipeline.send_email("receiver_email", "Subject", "Body")

    mock_instance.starttls.assert_called_once()
    mock_instance.login.assert_called_once_with(pipeline.EMAIL_ADDRESS, pipeline.APP_PASSWORD)
    mock_instance.sendmail.assert_called_once()
    mock_instance.quit.assert_called_once()
    assert result == 'Email sent successfully!'

@patch("smtplib.SMTP", side_effect=Exception("Connection error"))
def test_send_email_connection_failure(mock_smtp, pipeline):
    result = pipeline.send_email("receiver_email", "Subject", "Body")
    assert "Error: Connection error" in result

@patch("smtplib.SMTP")
def test_send_email_login_failure(mock_smtp, pipeline):
    mock_instance = MagicMock()
    mock_instance.login.side_effect = Exception("Login failed")
    mock_smtp.return_value = mock_instance

    result = pipeline.send_email("receiver_email", "Subject", "Body")
    assert "Error: Login failed" in result

@patch("smtplib.SMTP")
def test_send_email_sendmail_failure(mock_smtp, pipeline):
    mock_instance = MagicMock()
    mock_instance.sendmail.side_effect = Exception("Send failed")
    mock_smtp.return_value = mock_instance

    result = pipeline.send_email("receiver_email", "Subject", "Body")
    assert "Error: Send failed" in result

@patch("smtplib.SMTP")
def test_send_email_quit_failure(mock_smtp, pipeline):
    mock_instance = MagicMock()
    mock_instance.quit.side_effect = Exception("Quit failed")
    mock_smtp.return_value = mock_instance

    # Since the exception is raised at quit, the function still returns success
    result = pipeline.send_email("receiver_email", "Subject", "Body")
    assert result == "Email sent successfully!"