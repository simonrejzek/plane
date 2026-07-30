from __future__ import annotations

from typing import ClassVar
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as pi_service


class FakeTranscriptionResponse:
    status_code = 200
    headers: ClassVar[dict[str, str]] = {"content-type": "application/json"}
    text = '{"text":"hello from audio"}'

    def json(self):
        return {"text": "hello from audio"}


class FakeAsyncClient:
    request_data = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, **kwargs):
        FakeAsyncClient.request_data = kwargs.get("data")
        return FakeTranscriptionResponse()


def test_transcription_uses_whisper_large_v3_turbo(monkeypatch):
    monkeypatch.setattr(pi_service, "LLM_API_KEY", "test-key")
    FakeAsyncClient.request_data = None

    with patch.object(pi_service.httpx, "AsyncClient", FakeAsyncClient):
        response = TestClient(pi_service.app).post(
            "/api/v1/transcription/transcribe/?workspace_id=workspace&chat_id=chat",
            files={"file": ("sample.webm", b"audio-data", "audio/webm")},
        )

    assert response.status_code == 200
    assert response.json()["detail"] == "hello from audio"
    assert response.json()["text"] == "hello from audio"
    assert FakeAsyncClient.request_data == {
        "model": "openai/whisper-large-v3-turbo"
    }
