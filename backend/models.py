from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class SummarizeRequest(BaseModel):
    url: str
    include_screenshots: bool = True

class Metadata(BaseModel):
    title: str
    channel: str
    duration_seconds: int
    duration_formatted: str
    thumbnail_url: str

class VideoOverview(BaseModel):
    title: str
    channel: str
    duration: str
    main_topic: str

class KeySection(BaseModel):
    title: str
    timestamp: str
    timestamp_seconds: int
    description: str

class ImportantConcept(BaseModel):
    concept: str
    explanation: str

class ScreenshotTimestamp(BaseModel):
    seconds: int
    caption: str
    section_title: str

class SummaryData(BaseModel):
    video_overview: VideoOverview
    key_sections: List[KeySection]
    main_points: List[str]
    important_concepts: List[ImportantConcept]
    action_items: List[str]
    screenshot_timestamps: List[ScreenshotTimestamp]

class MindmapNode(BaseModel):
    id: str
    label: str
    category: Literal["root", "intro", "concept", "example", "process", "conclusion", "recommendation", "data", "tool"]
    children: List['MindmapNode'] = Field(default_factory=list)

class Screenshot(BaseModel):
    seconds: int
    timestamp_formatted: str
    caption: str
    url: str
    section_title: str

class ResultData(BaseModel):
    video_id: str
    metadata: Metadata
    summary: SummaryData
    mindmap: MindmapNode
    screenshots: List[Screenshot] = Field(default_factory=list)

class SSEEventResult(BaseModel):
    type: Literal["result"] = "result"
    data: ResultData

class SSEEventError(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str
    detail: Optional[str] = None
