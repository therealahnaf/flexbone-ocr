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
| `OCR_ENV_FILE` | `.env` | Optional bootstrap path to a mounted dotenv file |
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

The application follows a conventional layered FastAPI structure:

- `app/api`: transport-only routes, dependency lookup, and API composition.
- `app/schemas`: Pydantic HTTP response schemas with no service logic.
- `app/domain`: frozen dataclass contracts and dependency-inversion protocols.
- `app/services`: focused OCR, batch, validation, and text-processing use cases.
- `app/infra`: Google Vision, cache, and rate-limiter adapters.
- `app/core`: settings, composition root, exceptions, logging, and middleware.

Routes delegate directly to `OcrUseCase` or `BatchOcrUseCase`. `OcrService`
depends only on the `OcrProvider`, `OcrCache`, `ImageValidator`, and
`TextProcessor` protocols. `ApplicationContainer` is the single composition root
that selects concrete implementations. This keeps FastAPI and Google SDK types
out of the business contracts and makes every external dependency replaceable.

Uploads remain in memory and are never written to disk. Duplicate concurrent
requests share one in-flight Vision call. The Vision client is created lazily, so
importing the application and running unit tests do not require Google credentials.

## Testing

The default suite generates images in memory and injects a fake OCR provider. It
does not call Google Vision or consume quota.

```powershell
uv run ruff check app tests
uv run ruff format --check app tests
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

## Production deployment

Production uses Cloud Build, Artifact Registry, Cloud Run, and Secret Manager in
project `flexbone-ocr-challenge-505909`. The deployed URL is recorded here after
the initial release:

Public API: [https://flexbone-ocr-7wgxo2mfka-el.a.run.app](https://flexbone-ocr-7wgxo2mfka-el.a.run.app)

- Interactive docs: [https://flexbone-ocr-7wgxo2mfka-el.a.run.app/docs](https://flexbone-ocr-7wgxo2mfka-el.a.run.app/docs)
- Health check: [https://flexbone-ocr-7wgxo2mfka-el.a.run.app/api/v1/health](https://flexbone-ocr-7wgxo2mfka-el.a.run.app/api/v1/health)

Cloud Run runs with the dedicated identity
`ocr-runtime@flexbone-ocr-challenge-505909.iam.gserviceaccount.com`, zero to one
instances, one CPU, 512 MiB memory, request-based billing, and a 20-request
concurrency limit. The one-instance maximum preserves the process-local cache and
rate-limit behavior.

### Production configuration and secrets

Secret Manager secret `flexbone-ocr-env` contains the complete production dotenv
document. Cloud Run mounts a numeric secret version read-only at
`/secrets/ocr.env` and sets `OCR_ENV_FILE=/secrets/ocr.env`. The application fails
startup safely if an explicitly configured file is missing, unreadable, or
invalid.

Create or rotate the payload from a temporary file outside the repository. Never
put the value directly in a command argument or print it:

```powershell
$configFile = Join-Path $env:TEMP "flexbone-ocr-production.env"
# Create $configFile with the OCR_* settings, then upload it without displaying it.
gcloud secrets versions add flexbone-ocr-env `
  --project flexbone-ocr-challenge-505909 `
  --data-file=$configFile
Remove-Item -LiteralPath $configFile
```

After rotation, update `_OCR_ENV_VERSION` on the `flexbone-main-deploy` trigger
and run it. Retain the current and two previous enabled versions for rollback;
destroy older versions after the rollback window. Do not store Google credentials
in this secret and do not set `GOOGLE_APPLICATION_CREDENTIALS` on Cloud Run.
Cloud Run supplies ADC through its service identity.

### CI/CD

- `cloudbuild-ci.yaml` runs frozen dependency installation, Ruff checks, and the
  fake-provider test suite for pull requests without Vision or secret access.
- `cloudbuild-deploy.yaml` repeats those gates, builds and pushes an image tagged
  with the immutable commit SHA, deploys it with a pinned configuration version,
  and verifies `/api/v1/health`.
- `flexbone-pr-ci` runs for pull requests targeting `main` using the least-privilege
  `flexbone-ci` identity.
- `flexbone-main-deploy` deploys pushes to `main` using `flexbone-deployer`.

Artifact Registry cleanup policy
`deploy/artifact-registry-cleanup-policy.json` deletes versions older than seven
days while retaining the three most recent versions. The policy should be checked
in dry-run mode before automatic deletion is enabled.

### Rollback

List revisions and move traffic back to the last healthy revision. Each revision
retains its immutable image and pinned Secret Manager version:

```powershell
gcloud run revisions list `
  --service flexbone-ocr `
  --project flexbone-ocr-challenge-505909 `
  --region asia-south1

gcloud run services update-traffic flexbone-ocr `
  --project flexbone-ocr-challenge-505909 `
  --region asia-south1 `
  --to-revisions PREVIOUS_REVISION=100
```
