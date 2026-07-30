import subprocess
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2]


def run_tool(path: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SERVER_ROOT / ".venv/bin/python"), path, *arguments],
        cwd=SERVER_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_deepseek_smoke_help_loads_application_package() -> None:
    result = run_tool("tools/smoke_deepseek.py", "--help")

    assert result.returncode == 0
    assert "--difficulty" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr


def test_admin_credentials_help_loads_application_package() -> None:
    result = run_tool("tools/admin_credentials.py", "--help")

    assert result.returncode == 0
    assert "respond" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr
