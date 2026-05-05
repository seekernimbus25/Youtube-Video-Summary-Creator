from pydantic import BaseModel, Field
from typing import List, Literal, Optional


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


class IndexRequest(BaseModel):
    video_id: str


class IndexStatusResponse(BaseModel):
    status: Literal["indexing", "ready", "failed", "not_found"]
    progress_pct: Optional[int] = None
    error: Optional[str] = None
    message: Optional[str] = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    video_id: str
    messages: List[ChatMessage]


class ChatSSEEvent(BaseModel):
    type: Literal["status", "token", "error", "done"]
    text: Optional[str] = None


class StudyRequest(BaseModel):
    video_id: str


class Flashcard(BaseModel):
    id: str
    front: str
    back: str
    topic: str
    timestamp: str


class FlashcardsResponse(BaseModel):
    cards: List[Flashcard]


class QuizQuestion(BaseModel):
    id: str
    prompt: str
    options: List[str]
    correct_index: int
    explanation: str
    timestamp: str


class QuizResponse(BaseModel):
    questions: List[QuizQuestion]
