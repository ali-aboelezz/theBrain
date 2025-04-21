from fastapi import APIRouter, UploadFile, HTTPException
from app.core import ContractGenerator
from models.schemas import ExtractPlaceholders, FillDocument, ExportToPDF

router = APIRouter()
generator = ContractGenerator()

@router.post("/extract_placeholders_from_chat")
def extract_placeholders_from_chat(chat_input: ExtractPlaceholders):
    """Extract placeholders directly from chat messages."""
    try:
        placeholders = generator.extract_placeholders_from_text(chat_input.chat_messages)
        return {"placeholders": placeholders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/process_file")
async def process_file(file: UploadFile):
    """Extract placeholders from an uploaded document."""
    try:
        file_path = f"temp/{file.filename}"
        with open(file_path, "wb") as f:
            f.write(await file.read())
        placeholders = generator.extract_placeholders(file_path)
        return {"placeholders": placeholders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate_questions")
def generate_questions(data: dict):
    """Generate contextual questions for placeholders."""
    try:
        placeholders = data.get("placeholders", [])
        questions = generator.generate_questions(placeholders)
        return {"questions": questions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/fill_document")
def fill_document(request: FillDocument):
    """Fill placeholders in a document with responses."""
    try:
        generator.fill_document(request.template_path, request.output_path, request.responses)
        return {"message": f"Document filled and saved at {request.output_path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/export_to_pdf")
def export_to_pdf(request: ExportToPDF):
    """Export user responses to a PDF file."""
    try:
        generator.export_to_pdf(request.pdf_path, request.responses)
        return {"message": f"PDF exported successfully to {request.pdf_path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))