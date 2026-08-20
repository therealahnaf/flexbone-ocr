from types import SimpleNamespace

import pytest

from app.core.errors import OcrProviderError
from app.infra.google_vision import GoogleVisionOcrProvider


class FakeVisionClient:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.timeout = None
        self.image = None

    def document_text_detection(self, *, image, timeout):
        self.image = image
        self.timeout = timeout
        if self.error:
            raise self.error
        return self.response


def vision_response(*, text="Detected", confidences=(0.75, 0.95), error=""):
    words = [SimpleNamespace(confidence=value) for value in confidences]
    paragraph = SimpleNamespace(words=words)
    block = SimpleNamespace(paragraphs=[paragraph])
    page = SimpleNamespace(blocks=[block])
    return SimpleNamespace(
        error=SimpleNamespace(message=error),
        full_text_annotation=SimpleNamespace(text=text, pages=[page]),
        text_annotations=[SimpleNamespace(description="Fallback")],
    )


@pytest.mark.anyio
async def test_google_provider_extracts_text_confidences_and_timeout() -> None:
    client = FakeVisionClient(vision_response(confidences=(0.0, 0.75, 0.95, 2.0)))
    provider = GoogleVisionOcrProvider(7.5, client=client)

    result = await provider.extract_text(b"image")

    assert result.text == "Detected"
    assert result.confidences == (0.75, 0.95)
    assert client.timeout == 7.5


@pytest.mark.anyio
async def test_google_provider_falls_back_to_text_annotation() -> None:
    response = vision_response(text="", confidences=())
    client = FakeVisionClient(response)

    result = await GoogleVisionOcrProvider(1, client).extract_text(b"image")

    assert result.text == "Fallback"
    assert result.confidences == ()


@pytest.mark.anyio
async def test_google_provider_maps_client_and_response_errors() -> None:
    failing_client = FakeVisionClient(error=RuntimeError("private"))
    response_error_client = FakeVisionClient(vision_response(error="quota unavailable"))

    with pytest.raises(OcrProviderError, match="OCR service"):
        await GoogleVisionOcrProvider(1, failing_client).extract_text(b"image")
    with pytest.raises(OcrProviderError, match="OCR service"):
        await GoogleVisionOcrProvider(1, response_error_client).extract_text(b"image")


@pytest.mark.anyio
async def test_google_provider_lazily_creates_client(monkeypatch) -> None:
    client = FakeVisionClient(vision_response())
    monkeypatch.setattr(
        "app.infra.google_vision.vision.ImageAnnotatorClient",
        lambda: client,
    )
    provider = GoogleVisionOcrProvider(1)

    await provider.extract_text(b"one")
    await provider.extract_text(b"two")

    assert provider._get_client() is client
