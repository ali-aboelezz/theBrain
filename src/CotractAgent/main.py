from fastapi import FastAPI
from app.api import router

# Initialize FastAPI app
app = FastAPI(
    title="Contract Generator Agent",
    description="An AI-powered document generation assistant",
    version="1.0.0"
)

# Include API router
app.include_router(router)

# Run using `uvicorn main:app --reload`