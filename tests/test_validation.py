import io

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.core.errors import FileTooLargeError, InvalidImageError, UnsupportedImageError
from app.infra.image_inspection import PillowImageInspector
from app.services.image_validation import ImageValidationService
from app.services.text_processing import TextProcessingService
from tests.conftest import make_image


def upload(filename: str, content_type: str, content: bytes) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


@pytest.mark.parametrize(
    ("image_format", "filename", "content_type", "expected_frames"),
    [
        ("JPEG", "image.jpg", "image/jpeg", 1),
        ("JPEG", "image.jpeg", "image/jpg", 1),
        ("PNG", "image.png", "image/png", 1),
        ("GIF", "image.gif", "image/gif", 2),
    ],
)
@pytest.mark.anyio
async def test_validator_accepts_supported_images(
    image_format: str,
    filename: str,
    content_type: str,
    expected_frames: int,
) -> None:
    content = make_image(image_format, frames=expected_frames)
    validator = ImageValidationService(len(content), 1_000, PillowImageInspector())

    result = await validator.validate(upload(filename, content_type, content))

    assert result.metadata.format == image_format
    assert result.metadata.frame_count == expected_frames
    assert result.metadata.size_bytes == len(content)
    assert len(result.digest) == 64


@pytest.mark.anyio
async def test_validator_rejects_unsupported_or_mismatched_formats() -> None:
    jpeg = make_image("JPEG")
    validator = ImageValidationService(1_000_000, 1_000, PillowImageInspector())

    with pytest.raises(UnsupportedImageError):
        await validator.validate(upload("image.bmp", "image/bmp", jpeg))
    with pytest.raises(UnsupportedImageError):
        await validator.validate(upload("image.jpg", "image/png", jpeg))
    with pytest.raises(UnsupportedImageError):
        await validator.validate(upload("image.png", "image/png", jpeg))


@pytest.mark.anyio
async def test_validator_rejects_empty_corrupt_oversized_and_huge_images() -> None:
    validator = ImageValidationService(100, 100, PillowImageInspector())

    with pytest.raises(InvalidImageError, match="empty"):
        await validator.validate(upload("image.jpg", "image/jpeg", b""))
    with pytest.raises(InvalidImageError):
        await validator.validate(upload("image.jpg", "image/jpeg", b"not-an-image"))
    with pytest.raises(FileTooLargeError):
        await validator.validate(upload("image.jpg", "image/jpeg", b"x" * 101))

    large_dimensions = make_image("PNG", size=(11, 10))
    dimension_validator = ImageValidationService(
        len(large_dimensions),
        100,
        PillowImageInspector(),
    )
    with pytest.raises(FileTooLargeError, match="dimensions"):
        await dimension_validator.validate(upload("image.png", "image/png", large_dimensions))


def test_text_processor_preserves_structure_and_limits_blank_lines() -> None:
    raw = "\r\n  First  \r\n\r\n\r\n\r\nSecond\t \n\n"

    assert TextProcessingService.clean(raw) == "  First\n\n\nSecond"
    assert TextProcessingService.clean("\r\n\r\n") == ""
