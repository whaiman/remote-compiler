from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rgcc.server.compiler.fallback import run_fallback_compilation


def test_c_compilation_command(tmp_path: Path):
    src = tmp_path / "main.c"
    out = tmp_path / "a.out"
    proc = Mock(returncode=0, stdout="ok", stderr="")
    with patch("rgcc.server.compiler.fallback.subprocess.run", return_value=proc) as run:
        result = run_fallback_compilation(src, out)
    run.assert_called_once_with(
        ["gcc", str(src), "-o", str(out)], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0
    assert result.output_path == out
    assert result.stdout == "ok"


def test_cpp_compilation_command(tmp_path: Path):
    src = tmp_path / "main.cpp"
    out = tmp_path / "a.out"
    with patch(
        "rgcc.server.compiler.fallback.subprocess.run",
        return_value=Mock(returncode=1, stdout="", stderr="bad"),
    ):
        result = run_fallback_compilation(src, out)
    assert result.returncode == 1
    assert result.output_path is None


def test_unsupported_extension(tmp_path: Path):
    with pytest.raises(ValueError, match="Unsupported file extension"):
        run_fallback_compilation(tmp_path / "main.rs", tmp_path / "a.out")


def test_subprocess_exception_returns_error_result(tmp_path: Path):
    src = tmp_path / "main.cpp"
    with patch("rgcc.server.compiler.fallback.subprocess.run", side_effect=RuntimeError("boom")):
        result = run_fallback_compilation(src, tmp_path / "a.out")
    assert result.returncode == -1
    assert "boom" in result.stderr
    assert result.output_path is None
