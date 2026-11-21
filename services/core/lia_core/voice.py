from __future__ import annotations

import asyncio
import ipaddress
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx


class VoiceUnavailable(RuntimeError):
    """Raised when a requested local speech component is not configured."""


class VoiceProcessingError(RuntimeError):
    """Raised when a local speech engine fails to process audio."""


_ALLOWED_AUDIO_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "audio/ogg",
    "audio/mpeg",
    "audio/mp4",
    "audio/aac",
    "audio/flac",
}


def _is_loopback_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme != "http" or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    try:
        return ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        return parsed.hostname.lower() == "localhost"


class LocalVoice:
    """Local-only speech adapters: whisper.cpp HTTP server and Piper CLI."""

    def __init__(
        self,
        *,
        stt_url: str,
        piper_binary: str | None,
        piper_model: Path | None,
        timeout_seconds: float = 90.0,
        max_audio_bytes: int = 20 * 1024 * 1024,
    ) -> None:
        self.stt_url = stt_url.strip()
        self.piper_binary = piper_binary.strip() if piper_binary else ""
        self.piper_model = piper_model
        self.timeout_seconds = max(1.0, min(timeout_seconds, 180.0))
        self.max_audio_bytes = max(1024, min(max_audio_bytes, 40 * 1024 * 1024))

    @property
    def transcription_enabled(self) -> bool:
        return bool(self.stt_url) and _is_loopback_url(self.stt_url)

    @property
    def synthesis_enabled(self) -> bool:
        return bool(
            self.piper_binary
            and self.piper_model
            and self.piper_model.is_file()
            and self._resolve_piper()
        )

    def status(self) -> dict[str, object]:
        return {
            "transcription_configured": self.transcription_enabled,
            "synthesis_configured": self.synthesis_enabled,
            "processing": "local_only",
            "transcription_engine": "whisper.cpp",
            "synthesis_engine": "Piper",
        }

    async def transcribe(self, audio: bytes, content_type: str) -> str:
        if not self.transcription_enabled:
            raise VoiceUnavailable("Reconhecimento de voz local não está configurado.")
        normalized_type = content_type.split(";", 1)[0].strip().lower()
        if normalized_type not in _ALLOWED_AUDIO_TYPES:
            raise VoiceProcessingError("Formato de áudio não suportado.")
        if not audio or len(audio) > self.max_audio_bytes:
            raise VoiceProcessingError("Áudio vazio ou acima do limite permitido.")
        extension = {
            "audio/wav": "wav",
            "audio/x-wav": "wav",
            "audio/webm": "webm",
            "audio/ogg": "ogg",
            "audio/mpeg": "mp3",
            "audio/mp4": "m4a",
            "audio/aac": "aac",
            "audio/flac": "flac",
        }[normalized_type]
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    self.stt_url,
                    files={"file": (f"lia-recording.{extension}", audio, normalized_type)},
                    data={"response_format": "json"},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise VoiceProcessingError(
                "O mecanismo local de reconhecimento não conseguiu processar o áudio."
            ) from exc
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise VoiceProcessingError("O mecanismo local não reconheceu uma fala.")
        return text.strip()[:20000]

    async def synthesize(self, text: str) -> bytes:
        executable = self._resolve_piper()
        if not executable or not self.piper_model or not self.piper_model.is_file():
            raise VoiceUnavailable("Síntese de voz local não está configurada.")
        normalized = text.strip()
        if not normalized or len(normalized) > 4000:
            raise VoiceProcessingError("Texto vazio ou acima do limite de síntese.")
        return await asyncio.to_thread(self._synthesize_sync, executable, normalized)

    def _resolve_piper(self) -> str | None:
        if not self.piper_binary:
            return None
        candidate = Path(self.piper_binary).expanduser()
        if candidate.is_absolute():
            return str(candidate) if candidate.is_file() else None
        return shutil.which(self.piper_binary)

    def _synthesize_sync(self, executable: str, text: str) -> bytes:
        assert self.piper_model is not None
        with tempfile.TemporaryDirectory(prefix="lia-voice-") as directory:
            output = Path(directory) / "speech.wav"
            try:
                result = subprocess.run(
                    [
                        executable,
                        "--model",
                        str(self.piper_model),
                        "--output_file",
                        str(output),
                    ],
                    input=text.encode("utf-8"),
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise VoiceProcessingError(
                    "O mecanismo local de síntese não conseguiu gerar o áudio."
                ) from exc
            if result.returncode != 0 or not output.is_file():
                raise VoiceProcessingError(
                    "O mecanismo local de síntese retornou uma falha."
                )
            audio = output.read_bytes()
            if len(audio) < 44 or len(audio) > 40 * 1024 * 1024:
                raise VoiceProcessingError("O áudio sintetizado é inválido ou grande demais.")
            if audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
                raise VoiceProcessingError("O mecanismo de síntese não gerou um WAV válido.")
            return audio
