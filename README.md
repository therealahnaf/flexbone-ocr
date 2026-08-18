# Flexbone API

A FastAPI application managed with [uv](https://docs.astral.sh/uv/).

## Run locally

```powershell
uv sync
uv run fastapi dev app/main.py
```

The API is available at `http://127.0.0.1:8000`. Interactive documentation is
available at `/docs`.

## Endpoints

- `GET /` — API welcome response
- `GET /api/v1/health` — health check
