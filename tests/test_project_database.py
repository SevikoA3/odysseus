import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from core import database
from core import session_manager as session_manager_module
from core.session_manager import SessionManager


ROOT = Path(__file__).resolve().parents[1]


def _run_database_startup(db_file):
    return subprocess.run(
        [sys.executable, "-c", "import core.database"],
        cwd=ROOT,
        env={**os.environ, "DATABASE_URL": f"sqlite:///{db_file}"},
        capture_output=True,
        text=True,
    )


def test_legacy_session_project_migration_is_idempotent(tmp_path):
    db_file = tmp_path / "legacy.db"
    with sqlite3.connect(db_file) as connection:
        connection.execute(
            """
            CREATE TABLE sessions (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                endpoint_url VARCHAR NOT NULL,
                model VARCHAR NOT NULL,
                owner VARCHAR,
                rag BOOLEAN,
                archived BOOLEAN,
                folder VARCHAR,
                headers JSON,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                last_accessed DATETIME,
                last_message_at DATETIME,
                is_important BOOLEAN,
                message_count INTEGER,
                total_input_tokens INTEGER,
                total_output_tokens INTEGER,
                mode VARCHAR,
                crew_member_id VARCHAR
            )
            """
        )
        connection.execute(
            """
            INSERT INTO sessions (id, name, endpoint_url, model, created_at, updated_at)
            VALUES ('legacy', 'Legacy', 'http://example.test', 'model', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )

    first = _run_database_startup(db_file)
    assert first.returncode == 0, first.stderr

    with sqlite3.connect(db_file) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(sessions)")}
        first_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'sessions'"
        ).fetchone()[0]
        first_rows = connection.execute("SELECT id, project_id FROM sessions").fetchall()

    assert "project_id" in columns
    assert "ix_sessions_project_id" in indexes
    assert first_rows == [("legacy", None)]

    second = _run_database_startup(db_file)
    assert second.returncode == 0, second.stderr

    with sqlite3.connect(db_file) as connection:
        second_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'sessions'"
        ).fetchone()[0]
        second_rows = connection.execute("SELECT id, project_id FROM sessions").fetchall()

    assert second_schema == first_schema
    assert second_rows == first_rows


def test_fresh_schema_creates_project_tables_and_unique_file_links():
    engine = create_engine("sqlite:///:memory:")
    database.Base.metadata.create_all(engine)
    assert {"projects", "project_files"} <= set(inspect(engine).get_table_names())

    factory = sessionmaker(bind=engine)
    db = factory()
    try:
        db.add(database.Project(id="project", owner="owner", name="Project"))
        db.commit()
        db.add_all([
            database.ProjectFile(
                id="file-1",
                project_id="project",
                upload_id="upload",
                filename="one.txt",
                mime_type="text/plain",
                size=1,
            ),
            database.ProjectFile(
                id="file-2",
                project_id="project",
                upload_id="upload",
                filename="two.txt",
                mime_type="text/plain",
                size=2,
            ),
        ])
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(database.Session(
            id="session",
            name="Chat",
            endpoint_url="http://example.test",
            model="model",
            project_id="project",
        ))
        db.commit()
        db.delete(db.get(database.Project, "project"))
        db.commit()
        assert db.get(database.Session, "session").project_id is None
    finally:
        db.close()


def test_project_schema_enforces_name_and_instruction_limits():
    engine = create_engine("sqlite:///:memory:")
    database.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    try:
        db.add(database.Project(id="long-name", owner="owner", name="x" * 101))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.add(database.Project(
            id="long-instructions",
            owner="owner",
            name="Project",
            instructions="x" * 20001,
        ))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.close()


def test_session_manager_persists_and_reloads_nullable_project_id(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    database.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(session_manager_module, "SessionLocal", factory)
    monkeypatch.setattr(SessionManager, "load_sessions", lambda self: None)

    db = factory()
    try:
        db.add(database.Project(id="project", owner="owner", name="Project"))
        db.commit()
    finally:
        db.close()

    manager = SessionManager()
    manager.create_session(
        "project-session",
        "Project chat",
        "http://example.test",
        "model",
        owner="owner",
        project_id="project",
    )
    manager.create_session(
        "personal-session",
        "Personal chat",
        "http://example.test",
        "model",
        owner="owner",
    )

    db = factory()
    try:
        assert db.get(database.Session, "project-session").to_dict()["project_id"] == "project"
    finally:
        db.close()

    reloaded = SessionManager()
    reloaded._load_session_from_db("project-session")
    reloaded._load_session_from_db("personal-session")

    assert reloaded.sessions["project-session"].project_id == "project"
    assert reloaded.sessions["personal-session"].project_id is None
