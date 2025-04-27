from fastapi import FastAPI
from app.api import router

app = FastAPI(
    title="Smart Meeting Scheduler Agent",
    description="An AI-powered assistant for smart scheduling and managing Google Calendar events.",
    version="2.0.0"
)

app.include_router(router)
