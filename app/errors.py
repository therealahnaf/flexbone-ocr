from dataclasses import dataclass, field


@dataclass(slots=True)
class AppError(Exception):
    status_code: int
    code: str
    message: str
    headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)


class FileTooLargeError(AppError):
    def __init__(self, message: str = "The uploaded image exceeds the allowed limit."):
        super().__init__(413, "file_too_large", message)


class UnsupportedImageError(AppError):
    def __init__(self, message: str = "Only JPG, JPEG, PNG, and GIF images are supported."):
        super().__init__(415, "unsupported_image", message)


class InvalidImageError(AppError):
    def __init__(self, message: str = "The uploaded file is not a valid image."):
        super().__init__(422, "invalid_image", message)


class OcrProviderError(AppError):
    def __init__(self, message: str = "The OCR service could not process the image."):
        super().__init__(502, "ocr_provider_error", message)


class RateLimitError(AppError):
    def __init__(self, retry_after: int):
        super().__init__(
            429,
            "rate_limit_exceeded",
            "Too many OCR requests. Please retry later.",
            {"Retry-After": str(retry_after)},
        )
