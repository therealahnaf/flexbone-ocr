# Flexbone OCR API

A production-ready FastAPI service that extracts text from uploaded images with
Google Cloud Vision. It is deployed publicly on Google Cloud Run.

- **API:** https://flexbone-ocr-7wgxo2mfka-el.a.run.app
- **Swagger UI:** https://flexbone-ocr-7wgxo2mfka-el.a.run.app/docs
- **Health:** https://flexbone-ocr-7wgxo2mfka-el.a.run.app/api/v1/health

## Features

- JPG/JPEG, PNG, and GIF support with a 10 MiB upload limit
- Extracted text, mean word confidence, processing time, and image metadata
- Cleaned whitespace and graceful handling when no text is found
- SHA-256 duplicate-image caching for 10 minutes
- Per-client rate limiting with `Retry-After`
- Ordered batch OCR for up to five images
- Safe validation, structured logging, request IDs, and consistent errors

## Test the deployed API

The repository includes five images in [`samples/`](samples/). Run these commands
from the repository root.

### macOS and Linux

Single image:

```bash
curl -X POST \
  -F "image=@samples/sample_ocr_1.jpg" \
  https://flexbone-ocr-7wgxo2mfka-el.a.run.app/extract-text
```

Batch of five images:

```bash
curl -X POST \
  -F "images=@samples/sample_ocr_1.jpg" \
  -F "images=@samples/sample_ocr_2.jpg" \
  -F "images=@samples/sample_ocr_3.png" \
  -F "images=@samples/sample_ocr_4.jpg" \
  -F "images=@samples/sample_ocr_5.jpg" \
  https://flexbone-ocr-7wgxo2mfka-el.a.run.app/extract-text/batch
```

### Windows PowerShell

Use `curl.exe` to avoid PowerShell's `curl` alias.

Single image:

```powershell
curl.exe -X POST `
  -F "image=@samples/sample_ocr_1.jpg" `
  "https://flexbone-ocr-7wgxo2mfka-el.a.run.app/extract-text"
```

Batch of five images:

```powershell
curl.exe -X POST `
  -F "images=@samples/sample_ocr_1.jpg" `
  -F "images=@samples/sample_ocr_2.jpg" `
  -F "images=@samples/sample_ocr_3.png" `
  -F "images=@samples/sample_ocr_4.jpg" `
  -F "images=@samples/sample_ocr_5.jpg" `
  "https://flexbone-ocr-7wgxo2mfka-el.a.run.app/extract-text/batch"
```

Example response:

```json
{
  "success": true,
  "text": "Extracted text",
  "confidence": 0.95,
  "processing_time_ms": 321,
  "cached": false,
  "metadata": {
    "filename": "sample_ocr_1.jpg",
    "format": "JPEG",
    "content_type": "image/jpeg",
    "size_bytes": 12345,
    "width": 1200,
    "height": 800,
    "mode": "RGB",
    "frame_count": 1
  }
}
```

An image with no readable text returns HTTP 200 with empty `text` and confidence
`0.0`.

## API

### `POST /extract-text`

Send `multipart/form-data` with one field named `image`.

### `POST /extract-text/batch`

Send one to five repeated fields named `images`, as shown in the platform-specific
examples above.

Batch responses preserve input order and return successful and failed item counts.
One invalid image does not discard successful results.

> **Swagger UI note:** The batch field may appear as a string input because
> Swagger UI does not yet render OpenAPI 3.1 arrays of binary files correctly.
> The endpoint still accepts repeated multipart `images` fields as shown above.

### Errors

```json
{
  "success": false,
  "error": {
    "code": "unsupported_image",
    "message": "Only JPG, JPEG, PNG, and GIF images are supported."
  },
  "request_id": "correlation-id"
}
```

| Status | Meaning |
| --- | --- |
| `413` | File size or decoded dimensions exceed a limit |
| `415` | Unsupported, mismatched, or spoofed image format |
| `422` | Missing, empty, corrupt, or invalid upload |
| `429` | Rate limit exceeded |
| `502` | Google Vision could not complete OCR |
| `500` | Unexpected server error |

## Implementation

Google Cloud Vision performs document-text detection using Cloud Run's runtime
service identity, so no service-account key is stored in the repository or image.

Uploads are read into memory with a strict byte limit and never written to disk.
The service verifies extension, MIME type, detected image format, image integrity,
and decoded pixel count before calling Vision. Google-specific code is behind an
`OcrProvider` contract; FastAPI routes delegate all behavior to application
services, which keeps the API layer thin and the tests independent of Vision.

Production configuration is a versioned Secret Manager dotenv file mounted
read-only by Cloud Run. Cloud Build runs CI for pull requests, then builds,
publishes, deploys, and health-checks immutable commit-tagged images after merges
to `main`.

See [`docs/deployment.md`](docs/deployment.md) for the concise deployment runbook.

## Run locally

Requirements: Python 3.11+, `uv`, Google Cloud CLI, and access to project
`flexbone-ocr-challenge-505909`.

```powershell
gcloud auth application-default login
gcloud config set project flexbone-ocr-challenge-505909
gcloud services enable vision.googleapis.com

uv sync --dev
Copy-Item .env.example .env
uv run fastapi dev app/main.py
```

Open http://127.0.0.1:8000/docs. The `.env` copy is optional because settings have
safe defaults.

## Test and build

Tests inject a fake OCR provider and do not consume Vision quota.

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest --cov=app --cov-fail-under=85
docker build -t flexbone-ocr .
```

The suite covers validation, errors, confidence, cleanup, caching, rate limiting,
batch ordering/concurrency, and provider failures. The production image is
multi-stage, pinned, non-root, and honors Cloud Run's injected `PORT`.

## Project structure

```text
app/api       HTTP routes and dependencies
app/core      settings, middleware, errors, and composition
app/domain    dataclass contracts and protocols
app/infra     Google Vision, image, cache, and rate-limit adapters
app/schemas   HTTP request/response models
app/services  OCR, batch, validation, and text-processing use cases
tests         isolated unit and API tests
```
