import subprocess
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]


def test_project_click_opens_chats_and_gear_opens_settings():
    node = subprocess.run(
        ["node", str(_ROOT / "tests" / "projects_views.test.mjs")],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert node.stdout.strip() == "ok"
