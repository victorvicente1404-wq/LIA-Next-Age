from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from lia_core.voice import (
    LocalVoice,
    VoiceProcessingError,
    VoiceUnavailable,
    _is_loopback_url,
)


def test_voice_stt_accepts_only_loopback_http_urls():
    assert _is_loopback_url("http://127.0.0.1:8178/inference")
    assert _is_loopback_url("http://localhost:8178/inference")
    assert _is_loopback_url("http://[::1]:8178/inference")
    assert not _is_loopback_url("https://127.0.0.1:8178/inference")
    assert not _is_loopback_url("http://example.com/inference")
    assert not _is_loopback_url("http://user:pass@127.0.0.1/inference")


def test_voice_status_reports_local_configuration(tmp_path: Path):
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    voice = LocalVoice(
        stt_url="http://127.0.0.1:8178/inference",
        piper_binary="/usr/bin/piper",
        piper_model=model,
    )
    status = voice.status()
    assert status["transcription_configured"] is True
    assert status["processing"] == "local_only"
    assert status["synthesis_engine"] == "Piper"


def test_voice_transcription_posts_audio_to_local_whisper(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "  Olá, Lia!  "}

    class FakeClient:
        def __init__(self, timeout, trust_env):
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def post(self, url, *, files, data):
            captured["url"] = url
            captured["files"] = files
            captured["data"] = data
            return FakeResponse()

    monkeypatch.setattr("lia_core.voice.httpx.AsyncClient", FakeClient)
    voice = LocalVoice(
        stt_url="http://127.0.0.1:8178/inference",
        piper_binary=None,
        piper_model=None,
    )
    result = asyncio.run(voice.transcribe(b"fake-webm", "audio/webm;codecs=opus"))

    assert result == "Olá, Lia!"
    assert captured["url"] == "http://127.0.0.1:8178/inference"
    assert captured["trust_env"] is False
    assert captured["files"]["file"][0] == "lia-recording.webm"
    assert captured["data"] == {"response_format": "json"}


def test_voice_transcription_rejects_remote_endpoint():
    voice = LocalVoice(
        stt_url="https://speech.example.com/inference",
        piper_binary=None,
        piper_model=None,
    )
    with pytest.raises(VoiceUnavailable):
        asyncio.run(voice.transcribe(b"audio", "audio/wav"))


def test_voice_transcription_rejects_unsupported_and_oversized_audio():
    voice = LocalVoice(
        stt_url="http://127.0.0.1:8178/inference",
        piper_binary=None,
        piper_model=None,
        max_audio_bytes=1024,
    )
    with pytest.raises(VoiceProcessingError, match="Formato"):
        asyncio.run(voice.transcribe(b"audio", "application/octet-stream"))
    with pytest.raises(VoiceProcessingError, match="limite"):
        asyncio.run(voice.transcribe(b"x" * 2048, "audio/wav"))


def test_voice_synthesis_runs_piper_without_shell_and_returns_wav(tmp_path: Path):
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    executable = tmp_path / "fake-piper"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "output = pathlib.Path(sys.argv[sys.argv.index('--output_file') + 1])\n"
        "text = sys.stdin.read()\n"
        "assert text == 'Olá, Lia!'\n"
        "output.write_bytes(b'RIFF' + (36).to_bytes(4, 'little') + b'WAVE' + b'\\x00' * 32)\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    voice = LocalVoice(
        stt_url="",
        piper_binary=str(executable),
        piper_model=model,
    )

    audio = asyncio.run(voice.synthesize("Olá, Lia!"))

    assert audio[:4] == b"RIFF"
    assert audio[8:12] == b"WAVE"


def test_voice_synthesis_requires_configured_model():
    voice = LocalVoice(
        stt_url="",
        piper_binary="",
        piper_model=None,
    )
    with pytest.raises(VoiceUnavailable):
        asyncio.run(voice.synthesize("Olá"))


def test_voice_synthesis_rejects_blank_or_long_text(tmp_path: Path):
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    voice = LocalVoice(
        stt_url="",
        piper_binary="/usr/bin/piper",
        piper_model=model,
    )
    with pytest.raises(VoiceProcessingError):
        asyncio.run(voice.synthesize(" "))


def test_voice_transcription_rejects_empty_audio():
    voice = LocalVoice(
        stt_url="http://127.0.0.1:8178/inference",
        piper_binary=None,
        piper_model=None,
    )
    with pytest.raises(VoiceProcessingError, match="vazio"):
        asyncio.run(voice.transcribe(b"", "audio/wav"))
