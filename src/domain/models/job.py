from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    SEARCHING = "searching"
    SCRAPING = "scraping"
    EXTRACTING = "extracting"
    SYNTHESIZING = "synthesizing"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    ERROR = "error"


class CrawlJob(BaseModel):
    search_id: str
    query: str
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    total_steps: int = 0
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
