from pydantic import BaseModel, Field
from typing import List


class Chapter(BaseModel):
    title: str
    start_time: float
    end_time: float


class TranscriptSegment(BaseModel):
    text: str
    start: float
    duration: float


class TranscriptResult(BaseModel):
    text: str
    segments: List[TranscriptSegment]


class SummarizeRequest(BaseModel):
    url: str


class Metadata(BaseModel):
    title: str
    channel: str
    duration_seconds: int
    duration_formatted: str
    thumbnail_url: str
    chapters: List[Chapter] = Field(default_factory=list)
