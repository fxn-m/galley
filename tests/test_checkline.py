import subprocess
import sys
from pathlib import Path

SCRIPT = Path("scripts/checkline.py")


def test_checkline_accepts_files_at_limit(tmp_path: Path) -> None:
    source = tmp_path / "short.py"
    _ = source.write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(source), "--max-lines", "3"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "checkline: OK" in result.stdout


def test_checkline_reports_files_over_limit(tmp_path: Path) -> None:
    source = tmp_path / "long.md"
    _ = source.write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(source), "--max-lines", "2"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert str(source) in result.stderr
    assert "3 lines > 2" in result.stderr
