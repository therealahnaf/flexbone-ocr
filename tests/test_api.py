from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import OcrProviderError
from app.main import create_app
from app.services import ProviderResult
from tests.conftest import FakeOcrProvider, make_image


def file_tuple(filename: str, content: bytes, content_type: str):
    return filename, content, content_type


def test_root_health_and_openapi_are_not_rate_limited(client: TestClient) -> None:
    assert client.get("/").json() == {"message": "Flexbone API"}
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    schema = client.get("/openapi.json").json()
    assert "/extract-text" in schema["paths"]
    assert "/extract-text/batch" in schema["paths"]


def test_single_ocr_returns_cleaned_text_confidence_metadata_and_cache(
    client: TestClient,
    provider: FakeOcrProvider,
) -> None:
    image = make_image("JPEG")
    files = {"image": file_tuple("sample.jpg", image, "image/jpeg")}

    first = client.post("/extract-text", files=files)
    second = client.post("/extract-text", files=files)

    assert first.status_code == 200
    assert first.headers["X-Request-ID"]
    assert first.json() == {
        "success": True,
        "text": "  Hello\n\n\nWorld",
        "confidence": 0.9,
        "processing_time_ms": first.json()["processing_time_ms"],
        "cached": False,
        "metadata": {
            "filename": "sample.jpg",
            "format": "JPEG",
            "content_type": "image/jpeg",
            "size_bytes": len(image),
            "width": 12,
            "height": 10,
            "mode": "RGB",
            "frame_count": 1,
        },
    }
    assert second.status_code == 200
    assert second.json()["cached"] is True
    assert provider.calls == [image]


def test_no_text_is_a_success(
    client: TestClient,
    provider: FakeOcrProvider,
) -> None:
    image = make_image("PNG")
    provider.results[image] = ProviderResult("", ())

    response = client.post(
        "/extract-text",
        files={"image": file_tuple("blank.png", image, "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["text"] == ""
    assert response.json()["confidence"] == 0.0


def test_single_endpoint_returns_consistent_client_errors(client: TestClient) -> None:
    missing = client.post("/extract-text")
    unsupported = client.post(
        "/extract-text",
        files={"image": file_tuple("bad.txt", b"bad", "text/plain")},
    )
    corrupt = client.post(
        "/extract-text",
        files={"image": file_tuple("bad.jpg", b"bad", "image/jpeg")},
    )

    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "invalid_request"
    assert unsupported.status_code == 415
    assert unsupported.json()["error"]["code"] == "unsupported_image"
    assert corrupt.status_code == 422
    assert corrupt.json()["error"]["code"] == "invalid_image"
    for response in (missing, unsupported, corrupt):
        assert response.json()["success"] is False
        assert response.json()["request_id"]


def test_provider_and_unexpected_failures_are_safe(
    client: TestClient,
    provider: FakeOcrProvider,
) -> None:
    provider_failure = make_image("JPEG", color=(1, 1, 1))
    unexpected_failure = make_image("JPEG", color=(2, 2, 2))
    provider.errors[provider_failure] = OcrProviderError()
    provider.errors[unexpected_failure] = RuntimeError("secret detail")

    expected = client.post(
        "/extract-text",
        files={"image": file_tuple("provider.jpg", provider_failure, "image/jpeg")},
    )
    unexpected = client.post(
        "/extract-text",
        files={"image": file_tuple("unexpected.jpg", unexpected_failure, "image/jpeg")},
    )

    assert expected.status_code == 502
    assert expected.json()["error"]["code"] == "ocr_provider_error"
    assert unexpected.status_code == 500
    assert unexpected.json()["error"] == {
        "code": "internal_error",
        "message": "An unexpected error occurred.",
    }


def test_rate_limit_returns_retry_after(settings: Settings) -> None:
    limited_settings = settings.model_copy(update={"rate_limit_requests": 1})
    provider = FakeOcrProvider()
    image = make_image("JPEG")

    with TestClient(create_app(limited_settings, provider)) as client:
        first = client.post(
            "/extract-text",
            files={"image": file_tuple("first.jpg", image, "image/jpeg")},
        )
        second = client.post(
            "/extract-text",
            files={"image": file_tuple("second.jpg", image, "image/jpeg")},
        )
        health = client.get("/api/v1/health")

    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) >= 1
    assert second.json()["error"]["code"] == "rate_limit_exceeded"
    assert health.status_code == 200


def test_batch_returns_ordered_partial_results_and_reuses_cache(
    client: TestClient,
    provider: FakeOcrProvider,
) -> None:
    valid = make_image("PNG", color=(10, 10, 10))
    failed = make_image("GIF", color=(20, 20, 20))
    provider.errors[failed] = OcrProviderError("Vision unavailable")

    response = client.post(
        "/extract-text/batch",
        files=[
            ("images", file_tuple("valid.png", valid, "image/png")),
            ("images", file_tuple("failed.gif", failed, "image/gif")),
            ("images", file_tuple("duplicate.png", valid, "image/png")),
        ],
    )

    body = response.json()
    assert response.status_code == 200
    assert body["success"] is False
    assert (body["total"], body["successful"], body["failed"]) == (3, 2, 1)
    assert body["results"][0]["metadata"]["filename"] == "valid.png"
    assert body["results"][1]["filename"] == "failed.gif"
    assert body["results"][1]["error"]["code"] == "ocr_provider_error"
    assert body["results"][2]["metadata"]["filename"] == "duplicate.png"
    assert body["results"][2]["cached"] is True
    assert provider.calls.count(valid) == 1


def test_batch_enforces_maximum_and_provider_concurrency(settings: Settings) -> None:
    provider = FakeOcrProvider()
    provider.delay = 0.03
    batch_settings = settings.model_copy(
        update={"batch_max_files": 3, "batch_concurrency": 2}
    )
    images = [make_image("PNG", color=(value, 0, 0)) for value in (1, 2, 3)]

    with TestClient(create_app(batch_settings, provider)) as client:
        too_many = client.post(
            "/extract-text/batch",
            files=[
                ("images", file_tuple(f"{index}.png", image, "image/png"))
                for index, image in enumerate(images + [make_image("PNG")])
            ],
        )
        accepted = client.post(
            "/extract-text/batch",
            files=[
                ("images", file_tuple(f"{index}.png", image, "image/png"))
                for index, image in enumerate(images)
            ],
        )

    assert too_many.status_code == 422
    assert too_many.json()["error"]["code"] == "too_many_images"
    assert accepted.status_code == 200
    assert provider.max_active == 2
