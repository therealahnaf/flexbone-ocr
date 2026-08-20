import logging
import threading
from typing import Any

import anyio
from google.cloud import vision

from app.core.errors import OcrProviderError
from app.domain.models import OcrProviderResult

logger = logging.getLogger(__name__)


class GoogleVisionOcrProvider:
    """Google Vision adapter with lazy client construction."""

    def __init__(self, timeout_seconds: float, client: Any | None = None):
        self._timeout = timeout_seconds
        self._client = client
        self._client_lock = threading.Lock()

    def _get_client(self) -> Any:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = vision.ImageAnnotatorClient()
        return self._client

    async def extract_text(self, content: bytes) -> OcrProviderResult:
        def call_vision() -> Any:
            image = vision.Image(content=content)
            return self._get_client().document_text_detection(
                image=image,
                timeout=self._timeout,
            )

        try:
            response = await anyio.to_thread.run_sync(call_vision)
        except Exception as exc:
            raise OcrProviderError() from exc

        if response.error.message:
            logger.warning("Google Vision returned an OCR error: %s", response.error.message)
            raise OcrProviderError()

        full_text = getattr(response.full_text_annotation, "text", "") or ""
        if not full_text and response.text_annotations:
            full_text = response.text_annotations[0].description or ""

        confidences: list[float] = []
        for page in getattr(response.full_text_annotation, "pages", ()):
            for block in page.blocks:
                for paragraph in block.paragraphs:
                    for word in paragraph.words:
                        confidence = float(getattr(word, "confidence", 0.0))
                        if 0.0 < confidence <= 1.0:
                            confidences.append(confidence)

        return OcrProviderResult(full_text, tuple(confidences))
