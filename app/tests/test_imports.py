import ast
import importlib.util
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parents[1] / "transcribe_offline"
RUNTIME = [
    "__init__.py",
    "__main__.py",
    "app.py",
    "engine.py",
    "guard.py",
    "models.py",
]  # setup.py excluded
ALLOWED = {
    "__future__",
    "av",
    "av.audio.frame",
    "av.container",
    "av.error",
    "collections.abc",
    "dataclasses",
    "logging",
    "math",
    "numpy",
    "numpy.typing",
    "os",
    "pathlib",
    "queue",
    "sys",
    "threading",
    "time",
    "tkinter",
    "typing",
    "faster_whisper",
    "transcribe_offline",
    "transcribe_offline.app",
    "transcribe_offline.guard",
    "transcribe_offline.models",
}
DYNAMIC = {"__import__", "importlib", "eval", "exec"}
TCL = {"exec", "socket", "open", "load", "expose"}  # Tcl commands our code must never .call()
EXCLUDED = ["onnxruntime", "hf_xet", "httpx", "fsspec", "click"]  # [tool.uv] exclude-dependencies


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
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "call":
            strings = {a.value for a in node.args if isinstance(a, ast.Constant)}
            assert not strings & TCL, f"{name}:{node.lineno} {ast.unparse(node)}"


@pytest.mark.parametrize("module", EXCLUDED)
def test_excluded_dependency_is_not_installed(module: str) -> None:
    assert importlib.util.find_spec(module) is None


def test_faster_whisper_imports_without_excluded_dependencies() -> None:
    importlib.import_module("faster_whisper")  # ImportError if hub/tokenizers need one eagerly
    assert not set(EXCLUDED) & set(sys.modules)
