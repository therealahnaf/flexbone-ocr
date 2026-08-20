from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.errors import BatchItemErrorResponse


class ImageMetadataResponse(BaseModel):
    filename: str
    format: Literal["JPEG", "PNG", "GIF"]
    content_type: str
    size_bytes: int
    width: int
    height: int
    mode: str
    frame_count: int = 1


class OcrResponse(BaseModel):
    success: Literal[True] = True
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    processing_time_ms: int = Field(ge=0)
    cached: bool
    metadata: ImageMetadataResponse


class BatchResponse(BaseModel):
    success: bool
    total: int
    successful: int
    failed: int
    processing_time_ms: int = Field(ge=0)
    results: list[OcrResponse | BatchItemErrorResponse]
