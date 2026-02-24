from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from charts_api import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_MODE", "local")
    monkeypatch.setenv("LOCAL_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def png_file() -> tuple[io.BytesIO, str]:
    return io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * 64), "vg-chart.png"
