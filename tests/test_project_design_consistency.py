from pathlib import Path


CSS = (Path(__file__).parents[1] / "static" / "style.css").read_text(encoding="utf-8")
INDEX = (Path(__file__).parents[1] / "static" / "index.html").read_text(encoding="utf-8")


def test_project_controls_follow_shared_muted_design():
    project_css = CSS.split("/* Projects */", 1)[1].split("/* ── Archive browser ── */", 1)[0]

    assert "text-decoration: underline" not in project_css
    assert ".current-project-name { position: relative; max-width: 180px; height: 24px;" in project_css
    assert ".current-project-name::before" in project_css
    assert ".project-modal-content { width: min(620px, 92vw); max-width: calc(100vw - 24px); padding: 16px; }" in project_css
    assert ".project-modal-body { display: grid; grid-template-columns: minmax(0, 1fr); min-width: 0; gap: 12px; padding: 4px 2px 2px; }" in project_css
    assert ".project-chat-list { display: grid; grid-template-columns: minmax(0, 1fr); gap: 4px; }" in project_css
    assert ".project-actions .confirm-btn-primary { border: 1px solid color-mix" in project_css
    assert ".project-settings-btn { width: 44px; height: 44px; flex-basis: 44px; }" in project_css


def test_primary_sidebar_rows_do_not_use_manual_offsets():
    new_chat = INDEX.split('id="sidebar-new-chat-btn"', 1)[1].split("</div>", 1)[0]
    search = INDEX.split('id="sidebar-search-btn"', 1)[1].split("</div>", 1)[0]

    assert "left:" not in new_chat
    assert "left:" not in search
