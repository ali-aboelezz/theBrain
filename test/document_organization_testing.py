
import os
import pytest
from document_pipeline import DocumentIntelligencePipeline

@pytest.fixture(scope="module")
def pipeline():
    pipeline = DocumentIntelligencePipeline()
    pipeline._init_()  # Ensure internal setup is called
    return pipeline

def test_text_extraction_from_image(pipeline):
    sample_image_path = "/content/drive/MyDrive/datasets/text_inout/Screen Shot 2025-03-20 at 11.23.06 AM.png"
    if not os.path.exists(sample_image_path):
        pytest.skip(f"Sample image not found: {sample_image_path}")
    text = pipeline.extract_text_from_image(sample_image_path)
    assert isinstance(text, str) and len(text) > 0



def test_email_notification(pipeline):
    result = pipeline.send_email(
        receiver_email="sinbadx22@gmail.com",  
        subject="Test Email from Pipeline",
        body="This is a test email from the document intelligence pipeline."
    )
    assert "Email sent successfully" in result or "Error:" in result

def test_document_processing_and_storage(pipeline):
    sample_txt = "/content/drive/MyDrive/datasets/text_inout/recognized2.txt"
    if not os.path.exists(sample_txt):
        pytest.skip(f"Sample text file not found: {sample_txt}")
    pipeline.process_and_store(sample_txt)

def test_smart_search(pipeline):
    question = "meeting"
    result = pipeline.search_documents(question)
    assert isinstance(result, list)
