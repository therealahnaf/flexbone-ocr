import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_use_defaults_without_env_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("OCR_ENV_FILE", raising=False)
    monkeypatch.chdir(tmp_path)

    settings = get_settings()

    assert settings.max_file_size_bytes == 10 * 1024 * 1024
    assert settings.batch_concurrency == 3


def test_settings_load_explicit_env_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "ocr.env"
    env_file.write_text(
        "OCR_CACHE_TTL_SECONDS=42\nOCR_BATCH_CONCURRENCY=2\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OCR_ENV_FILE", str(env_file))

    settings = get_settings()

    assert settings.cache_ttl_seconds == 42
    assert settings.batch_concurrency == 2


def test_explicit_missing_env_file_fails_safely(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret_value = "must-not-appear"
    missing_file = tmp_path / secret_value
    monkeypatch.setenv("OCR_ENV_FILE", str(missing_file))

    with pytest.raises(RuntimeError) as error:
        get_settings()

    assert str(error.value) == "Configured OCR settings file is unavailable."
    assert secret_value not in str(error.value)


def test_invalid_mounted_settings_fail_without_leaking_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_value = "sensitive-invalid-value"
    env_file = tmp_path / "ocr.env"
    env_file.write_text(
        f"OCR_BATCH_CONCURRENCY={secret_value}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OCR_ENV_FILE", str(env_file))

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError) as error:
        get_settings()

    assert str(error.value) == "Configured OCR settings are invalid."
    assert secret_value not in str(error.value)
    assert secret_value not in caplog.text
