import hashlib
from pathlib import Path

from app.core.errors import FileTooLargeError, InvalidImageError, UnsupportedImageError
from app.domain.models import ImageFormat, ImageMetadata, ValidatedImage
from app.domain.ports import ImageInspector, UploadSource


class ImageValidationService:
    _extensions: dict[str, ImageFormat] = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".gif": "GIF",
    }
    _content_types: dict[str, ImageFormat] = {
        "image/jpeg": "JPEG",
        "image/jpg": "JPEG",
        "image/png": "PNG",
        "image/gif": "GIF",
    }

    def __init__(
        self,
        max_file_size_bytes: int,
        max_image_pixels: int,
        inspector: ImageInspector,
    ):
        self._max_file_size = max_file_size_bytes
        self._max_image_pixels = max_image_pixels
        self._inspector = inspector

    async def validate(self, upload: UploadSource) -> ValidatedImage:
        filename = upload.filename or ""
        extension_format = self._extensions.get(Path(filename).suffix.lower())
        content_type = (upload.content_type or "").lower()
        content_type_format = self._content_types.get(content_type)

        if not extension_format or not content_type_format:
            raise UnsupportedImageError()
        if extension_format != content_type_format:
            raise UnsupportedImageError(
                "The filename extension and Content-Type do not describe the same image format."
            )

        content = await upload.read(self._max_file_size + 1)
        if not content:
            raise InvalidImageError("The uploaded image is empty.")
        if len(content) > self._max_file_size:
            raise FileTooLargeError(f"Each image must be at most {self._max_file_size} bytes.")

        inspected = self._inspector.inspect(content)
        if inspected.width * inspected.height > self._max_image_pixels:
            raise FileTooLargeError(
                f"Image dimensions must not exceed {self._max_image_pixels} pixels."
            )
        if inspected.format != extension_format:
            raise UnsupportedImageError(
                "The image contents do not match its filename and Content-Type."
            )

        metadata = ImageMetadata(
            filename=filename,
            format=inspected.format,
            content_type=content_type,
            size_bytes=len(content),
            width=inspected.width,
            height=inspected.height,
            mode=inspected.mode,
            frame_count=inspected.frame_count,
        )
        return ValidatedImage(
            content=content,
            digest=hashlib.sha256(content).hexdigest(),
            metadata=metadata,
        )
