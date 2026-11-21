from __future__ import annotations

from lia_core.config import Settings
from lia_core.inference.llamacpp import LocalInferenceClient


def create_inference_client(settings: Settings):
    """Select a local runtime; never selects a hosted AI provider."""
    backend = settings.runtime_backend

    if backend in {"auto", "openjarvis"}:
        try:
            from lia_core.inference.openjarvis import OpenJarvisInferenceClient

            return OpenJarvisInferenceClient(settings)
        except ImportError as exc:
            if backend == "openjarvis":
                raise RuntimeError(
                    "LIA_RUNTIME_BACKEND=openjarvis, but OpenJarvis is not installed "
                    "in this Python environment."
                ) from exc

    if backend in {"auto", "llama.cpp", "llamacpp"}:
        return LocalInferenceClient(settings)

    raise ValueError(
        "LIA_RUNTIME_BACKEND must be auto, openjarvis, or llama.cpp."
    )
