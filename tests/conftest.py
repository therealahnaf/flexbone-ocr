import asyncio
import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.core.errors import OcrProviderError
from app.domain.models import OcrProviderResult
from app.main import create_app


class FakeOcrProvider:
    def __init__(self) -> None:
        self.calls: list[bytes] = []
        self.results: dict[bytes, OcrProviderResult] = {}
        self.errors: dict[bytes, Exception] = {}
        self.default_result = OcrProviderResult(
            "  Hello  \r\n\r\n\r\n\r\nWorld  \n",
            (0.8, 1.0),
        )
        self.delay = 0.0
        self.active = 0
        self.max_active = 0

    async def extract_text(self, content: bytes) -> OcrProviderResult:
        self.calls.append(content)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            error = self.errors.get(content)
            if error:
                raise error
            return self.results.get(content, self.default_result)
        finally:
            self.active -= 1


def make_image(
    image_format: str = "JPEG",
    *,
    size: tuple[int, int] = (12, 10),
    color: tuple[int, int, int] = (255, 255, 255),
    frames: int = 1,
) -> bytes:
    output = io.BytesIO()
    image = Image.new("RGB", size, color)
    if image_format == "GIF" and frames > 1:
        other_frames = [Image.new("RGB", size, (index * 30, 0, 0)) for index in range(1, frames)]
        image.save(
            output,
            format=image_format,
            save_all=True,
            append_images=other_frames,
            duration=100,
            loop=0,
        )
    else:
        image.save(output, format=image_format)
    return output.getvalue()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        max_file_size_bytes=1024 * 1024,
        max_image_pixels=10_000,
        cache_ttl_seconds=60,
        cache_max_entries=32,
        rate_limit_requests=100,
        rate_limit_window_seconds=60,
        vision_timeout_seconds=1,
        batch_max_files=5,
        batch_concurrency=2,
    )


@pytest.fixture
def provider() -> FakeOcrProvider:
    return FakeOcrProvider()


@pytest.fixture
def client(
    settings: Settings,
    provider: FakeOcrProvider,
) -> Iterator[TestClient]:
    with TestClient(
        create_app(settings=settings, provider=provider),
        raise_server_exceptions=False,
    ) as test_client:
        yield test_client


@pytest.fixture
def provider_error() -> OcrProviderError:
    return OcrProviderError()
