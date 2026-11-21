from __future__ import annotations

from io import BytesIO

from lia_core.dev.tasks import MAX_OUTPUT_BYTES, TaskRunner


def test_task_output_capture_is_bounded_and_pipe_is_drained():
    source = BytesIO(b"x" * (MAX_OUTPUT_BYTES + 8192))
    captured = bytearray()
    truncated = [False]

    TaskRunner._read_limited_output(source, captured, truncated)

    assert len(captured) == MAX_OUTPUT_BYTES
    assert truncated == [True]
    assert source.read() == b""
