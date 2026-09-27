import ast
import importlib.util
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parents[1] / "transcribe_offline"
RUNTIME = ["__init__.py", "__main__.py", "app.py", "engine.py", "models.py"]  # setup.py excluded
ALLOWED = {
    "__future__",
    "collections.abc",
    "dataclasses",
    "logging",
    "logging.handlers",
    "math",
    "os",
    "pathlib",
    "queue",
    "sys",
    "threading",
    "tkinter",
    "typing",
    "faster_whisper",
    "transcribe_offline",
    "transcribe_offline.app",
    "transcribe_offline.engine",
    "transcribe_offline.models",
}
DYNAMIC = {"__import__", "importlib", "eval", "exec"}
EXCLUDED = ["onnxruntime"]  # [tool.uv] exclude-dependencies


@pytest.mark.parametrize("name", RUNTIME)
def test_runtime_imports_are_allow_listed(name: str) -> None:
    tree = ast.parse((PACKAGE / name).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert {a.name for a in node.names} <= ALLOWED, ast.unparse(node)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module in ALLOWED, ast.unparse(node)
            if node.module == "faster_whisper":
                assert [a.name for a in node.names] == ["WhisperModel"], ast.unparse(node)
        elif isinstance(node, ast.Name):
            assert node.id not in DYNAMIC, f"{name}:{node.lineno} {node.id}"
        elif isinstance(node, ast.Attribute):
            assert node.attr not in DYNAMIC, f"{name}:{node.lineno} {node.attr}"


@pytest.mark.parametrize("module", EXCLUDED)
def test_excluded_dependency_is_not_installed(module: str) -> None:
    assert importlib.util.find_spec(module) is None
