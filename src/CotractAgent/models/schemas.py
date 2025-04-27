from pydantic import BaseModel
from typing import List, Dict

class ExtractPlaceholders(BaseModel):
    chat_messages: List[str]

class ProcessFile(BaseModel):
    file_path: str

class FillDocument(BaseModel):
    template_path: str
    output_path: str
    responses: Dict[str, str]

class ExportToPDF(BaseModel):
    pdf_path: str
    responses: Dict[str, str]