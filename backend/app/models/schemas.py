from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UploadRequest(BaseModel):
    filename: str
    content_type: str = "audio/webm"


class UploadResponse(BaseModel):
    upload_url: str
    object_key: str


class AnalysisCreateRequest(BaseModel):
    object_key: str


class AnalysisCreateResponse(BaseModel):
    analysis_id: str
    status: str = "processing"


class VoiceToneResult(BaseModel):
    score: int = Field(ge=0, le=100)
    confidence_level: str
    warmth: str
    monotone_detected: bool
    summary: str


class VocabularyResult(BaseModel):
    score: int = Field(ge=0, le=100)
    filler_word_count: int
    unique_word_ratio: float
    readability_level: str
    summary: str


class PacingResult(BaseModel):
    score: int = Field(ge=0, le=100)
    words_per_minute: int
    variation: str
    pause_usage: str
    summary: str


class ExecutivePresenceResult(BaseModel):
    tips: list[str]


class AnalysisResults(BaseModel):
    voice_tone: VoiceToneResult
    vocabulary: VocabularyResult
    pacing: PacingResult
    executive_presence: Optional[ExecutivePresenceResult] = None
    overall_score: int = Field(ge=0, le=100)
    overall_summary: str
    recommendations: list[str]


class AnalysisResponse(BaseModel):
    analysis_id: str
    status: str
    created_at: datetime
    results: Optional[AnalysisResults] = None


class AnalysisListResponse(BaseModel):
    items: list[AnalysisResponse]
    total: int
    page: int
    page_size: int
