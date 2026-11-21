from pathlib import Path

from lia_core.agents.registry import ToolPolicy, ToolRegistry, ToolResult, ToolSpec
from lia_core.agents.tools import CalculatorTool, build_default_registry
from lia_core.memory.store import MemoryStore


def test_calculator_supports_basic_arithmetic():
    result = CalculatorTool().execute(expression="(12 + 8) * 3")
    assert result.success
    assert result.content == "60"


def test_calculator_rejects_code_execution():
    tool = CalculatorTool()
    for expression in ("__import__('os').system('whoami')", "2 ** 100", "x + 1"):
        try:
            tool.execute(expression=expression)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe expression accepted: {expression}")


def test_registry_denies_unknown_and_non_allowlisted_tools():
    class WriteTool:
        @property
        def spec(self):
            return ToolSpec("write_file", "write", {"type": "object"}, "write")

        def execute(self, **arguments):
            return ToolResult("write_file", "written")

    registry = ToolRegistry(ToolPolicy({"calculator"}))
    registry.register(WriteTool())
    assert not registry.execute("missing", {}).success
    assert not registry.execute("write_file", {}).success


def test_default_tools_are_local_and_memory_search_is_read_only(tmp_path: Path):
    memory = MemoryStore(tmp_path / "memory.sqlite3")
    memory.add("fact", "Lia usa armazenamento local.")
    registry = build_default_registry(memory)
    assert {spec.name for spec in registry.list_specs()} == {"calculator", "memory_search"}
    result = registry.execute("memory_search", {"query": "armazenamento local"})
    assert result.success
    assert "armazenamento local" in result.content


def test_registry_denial_never_dispatches_tool():
    calls = []

    class RestrictedTool:
        @property
        def spec(self):
            return ToolSpec("restricted", "restricted operation", {"type": "object"})

        def execute(self, **arguments):
            calls.append(arguments)
            return ToolResult("restricted", "executed")

    registry = ToolRegistry(ToolPolicy(set()))
    registry.register(RestrictedTool())

    result = registry.execute("restricted", {"value": "x"})

    assert not result.success
    assert calls == []
