# Flexbone OCR API

A FastAPI service that accepts image uploads and extracts text with Google Cloud
Vision document-text detection. It is designed for local development with `uv`
and is ready to run as a non-root container on Google Cloud Run.

## Features

- Single-image OCR for JPG/JPEG, PNG, and GIF (animated GIFs use the first frame)
- Batch OCR for up to five images with ordered partial results
- Mean word-confidence score and cleaned text formatting
- Image dimensions, format, mode, frame count, and size metadata
- SHA-256 duplicate detection with a bounded 10-minute in-memory cache
- Per-client in-memory rate limiting with `Retry-After`
- Bounded file reads, content validation, pixel limits, safe errors, and request IDs
- Structured JSON request logging without logging image data or extracted text

The cache and rate limiter are intentionally process-local. They reset whenever
the server restarts and are not shared between Cloud Run instances.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Google Cloud CLI
- A Google Cloud project with the Vision API enabled
- Application Default Credentials (ADC)

This project is configured for `flexbone-ocr-challenge-505909`. Authenticate and
verify the active project:

```powershell
gcloud auth login
gcloud config set project flexbone-ocr-challenge-505909
gcloud auth application-default login
gcloud config get-value project
gcloud services enable vision.googleapis.com
```

ADC is discovered automatically by the Google client library. Do not download a
service-account key or set `GOOGLE_APPLICATION_CREDENTIALS` for normal local
development.

## Run locally

```powershell
uv sync --dev
Copy-Item .env.example .env
uv run fastapi dev app/main.py
```

The server is available at `http://127.0.0.1:8000`:

- Interactive API docs: `http://127.0.0.1:8000/docs`
- OpenAPI document: `http://127.0.0.1:8000/openapi.json`
- Health check: `GET http://127.0.0.1:8000/api/v1/health`

The `.env` copy is optional because every setting has a safe default.

## API

### Extract text from one image

`POST /extract-text` expects multipart field `image`:

```powershell
curl.exe -X POST -F "image=@test.jpg" http://127.0.0.1:8000/extract-text
```

Successful response:

```json
{
  "success": true,
  "text": "Extracted text",
  "confidence": 0.95,
  "processing_time_ms": 321,
  "cached": false,
  "metadata": {
    "filename": "test.jpg",
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

An image containing no readable text returns HTTP 200 with `text: ""` and
`confidence: 0.0`.

### Extract text from a batch

`POST /extract-text/batch` accepts one to five repeated `images` fields:

```powershell
curl.exe -X POST `
  -F "images=@test.jpg" `
  -F "images=@another.png" `
  http://127.0.0.1:8000/extract-text/batch
```

The response preserves input order and contains `total`, `successful`, `failed`,
total processing time, and one success or error object per file. A valid batch
returns HTTP 200 even when individual files fail, allowing successful results to
be retained.

### Errors

All request-level errors use this shape:

```json
{
  "success": false,
  "error": {
    "code": "unsupported_image",
    "message": "Only JPG, JPEG, PNG, and GIF images are supported."
  },
  "request_id": "59d20b4e-4407-475c-9fe7-e93dd772a5cf"
}
```

| Status | Meaning |
| --- | --- |
| `413` | File bytes or decoded image dimensions exceed a limit |
| `415` | Unsupported, mismatched, or spoofed image format |
| `422` | Missing multipart field, corrupt image, or invalid batch |
| `429` | Rate limit exceeded; inspect `Retry-After` |
| `502` | Google Vision rejected or could not complete OCR |
| `500` | Unexpected server error with implementation details hidden |

Every response includes `X-Request-ID` for correlation.

## Configuration

Settings use the `OCR_` prefix and can be placed in `.env`:

| Variable | Default | Description |
| --- | ---: | --- |
| `OCR_MAX_FILE_SIZE_BYTES` | `10485760` | Maximum bytes per image (10 MiB) |
| `OCR_MAX_IMAGE_PIXELS` | `25000000` | Maximum decoded width x height |
| `OCR_CACHE_TTL_SECONDS` | `600` | Cached OCR result lifetime |
| `OCR_CACHE_MAX_ENTRIES` | `256` | Maximum cached image hashes |
| `OCR_RATE_LIMIT_REQUESTS` | `30` | OCR requests allowed per client/window |
| `OCR_RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate-limit window |
| `OCR_VISION_TIMEOUT_SECONDS` | `15` | Deadline for a Vision request |
| `OCR_BATCH_MAX_FILES` | `5` | Maximum images in a batch |
| `OCR_BATCH_CONCURRENCY` | `3` | Maximum concurrent Vision calls |

## Design

The API routes only translate HTTP input/output. `OcrService` coordinates small,
replaceable components:

- `OcrProvider` isolates Google Vision and permits a quota-free fake in tests.
- `ImageValidator` enforces format, size, integrity, and metadata rules.
- `TextProcessor` normalizes OCR output while preserving meaningful line breaks.
- `OcrCache` hides the bounded TTL cache implementation.
- `InMemoryRateLimiter` protects only OCR endpoints; health and docs remain open.

Uploads remain in memory and are never written to disk. Duplicate concurrent
requests share one in-flight Vision call. The Vision client is created lazily, so
importing the application and running unit tests do not require Google credentials.

## Testing

The default suite generates images in memory and injects a fake OCR provider. It
does not call Google Vision or consume quota.

```powershell
uv run pytest --cov=app --cov-fail-under=85
```

To run the standalone live Vision smoke test with ADC and the included sample:

```powershell
uv run python test_vision.py
```

## Docker

Build the pinned, non-root production image:

```powershell
docker build -t flexbone-ocr .
```

For local container testing only, mount the ADC file generated by gcloud as
read-only:

```powershell
docker run --rm -p 8080:8080 `
  -e GOOGLE_APPLICATION_CREDENTIALS=/var/secrets/google/adc.json `
  --mount "type=bind,source=$env:APPDATA\gcloud\application_default_credentials.json,target=/var/secrets/google/adc.json,readonly" `
  flexbone-ocr
```

Test it at `http://127.0.0.1:8080/docs`. The container listens on `0.0.0.0` and
uses Cloud Run's injected `PORT`, defaulting to 8080 locally.

## Future Cloud Run deployment

Deployment is intentionally not performed as part of the local implementation.
When ready, the existing dedicated runtime identity can be attached with:

```powershell
gcloud run deploy flexbone-ocr `
  --source . `
  --project flexbone-ocr-challenge-505909 `
  --region asia-south1 `
  --allow-unauthenticated `
  --service-account ocr-runtime@flexbone-ocr-challenge-505909.iam.gserviceaccount.com
```

Cloud Run supplies ADC automatically through that service identity; do not copy
local credential files into the image.
