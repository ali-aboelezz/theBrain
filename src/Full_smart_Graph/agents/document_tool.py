# agents/document_tool.py

from langchain_core.tools import tool
from .docOrganization import DocumentIntelligencePipeline

@tool
def document_organizer() -> str:
    """
    Runs the Document Intelligence Pipeline for classification, summary, and storage.
    """
    print("📄 [Tool] Starting document intelligence pipeline...")
    pipeline = DocumentIntelligencePipeline()
    pipeline.run()
    return "✅ Document processed and stored."
