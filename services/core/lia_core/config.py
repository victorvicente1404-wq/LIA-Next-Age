from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    llm_base_url: str
    llm_model: str
    data_dir: Path
    dev_workspaces: tuple[Path, ...] = ()
    runtime_backend: str = "auto"
    request_timeout_seconds: float = 120.0
    voice_stt_url: str = "http://127.0.0.1:8178/inference"
    voice_tts_binary: str = ""
    voice_tts_model: Path | None = None
    voice_timeout_seconds: float = 90.0
    voice_max_audio_bytes: int = 20 * 1024 * 1024

    @classmethod
    def from_env(cls) -> Settings:
        workspace_values = os.getenv("LIA_DEV_WORKSPACES", "")
        workspaces = tuple(
            Path(item).expanduser()
            for item in workspace_values.split(os.pathsep)
            if item.strip()
        )
        return cls(
            llm_base_url=os.getenv("LIA_LLM_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/"),
            llm_model=os.getenv("LIA_LLM_MODEL", "local-model"),
            data_dir=Path(os.getenv("LIA_DATA_DIR", str(Path.home() / ".lia"))).expanduser(),
            dev_workspaces=workspaces,
            runtime_backend=os.getenv("LIA_RUNTIME_BACKEND", "auto").strip().lower(),
            request_timeout_seconds=float(os.getenv("LIA_LLM_TIMEOUT", "120")),
            voice_stt_url=os.getenv(
                "LIA_VOICE_STT_URL", "http://127.0.0.1:8178/inference"
            ).strip(),
            voice_tts_binary=os.getenv("LIA_PIPER_BIN", "").strip(),
            voice_tts_model=(
                Path(os.environ["LIA_PIPER_MODEL"]).expanduser()
                if os.getenv("LIA_PIPER_MODEL", "").strip()
                else None
            ),
            voice_timeout_seconds=float(os.getenv("LIA_VOICE_TIMEOUT", "90")),
            voice_max_audio_bytes=int(
                os.getenv("LIA_VOICE_MAX_AUDIO_BYTES", str(20 * 1024 * 1024))
            ),
        )
