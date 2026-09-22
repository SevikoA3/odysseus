from types import SimpleNamespace

import pytest
from fastapi import APIRouter, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core import database
from core.models import ChatMessage, Session
from routes import project_routes


class _Uploads:
    def __init__(self):
        self.rows = {
            "a" * 32 + ".txt": {
                "id": "a" * 32 + ".txt",
                "owner": "alice",
                "name": "alice.txt",
                "mime": "text/plain",
                "size": 5,
            },
            "b" * 32 + ".txt": {
                "id": "b" * 32 + ".txt",
                "owner": "bob",
                "name": "bob.txt",
                "mime": "text/plain",
                "size": 3,
            },
        }

    def resolve_upload(self, upload_id, owner=None, allow_admin=False):
        upload = self.rows.get(upload_id)
        return dict(upload) if upload and upload["owner"] == owner else None

    def reserve_upload(self, upload_id, owner=None, allow_admin=False):
        return self.resolve_upload(upload_id, owner=owner, allow_admin=allow_admin)


def _endpoints(router):
    return {
        (method, route.path): route.endpoint
        for route in router.routes
        for method in route.methods or ()
        if method != "HEAD"
    }


def _project_routes(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    database.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    user = {"name": "alice"}
    manager = SimpleNamespace(sessions={})
    uploads = _Uploads()

    monkeypatch.setattr(project_routes, "SessionLocal", factory)
    monkeypatch.setattr(project_routes, "effective_user", lambda request: user["name"])
    monkeypatch.setattr(project_routes, "storage_owner_for_request", lambda request: user["name"])
    return _endpoints(project_routes.setup_project_routes(manager, uploads)), user, factory, manager, uploads


def _create_project(endpoints):
    return endpoints[("POST", "/api/projects")](
        SimpleNamespace(),
        project_routes.ProjectCreate(name="Project", instructions="Keep answers short."),
    )


def test_project_crud_is_owner_scoped(monkeypatch):
    endpoints, user, factory, _manager, _uploads = _project_routes(monkeypatch)
    create = endpoints[("POST", "/api/projects")]
    for payload in (
        project_routes.ProjectCreate(name=" "),
        project_routes.ProjectCreate(name="Project", instructions="x" * 20001),
    ):
        with pytest.raises(HTTPException) as exc:
            create(SimpleNamespace(), payload)
        assert exc.value.status_code == 422

    created = _create_project(endpoints)

    assert endpoints[("GET", "/api/projects")](SimpleNamespace()) == [created]
    updated = endpoints[("PATCH", "/api/projects/{project_id}")](
        SimpleNamespace(),
        created["id"],
        project_routes.ProjectUpdate(name="Renamed", instructions=None),
    )
    assert updated["name"] == "Renamed"
    assert updated["instructions"] is None

    db = factory()
    try:
        db.add(database.Session(
            id="bob-session",
            owner="bob",
            name="Bob chat",
            endpoint_url="http://example.test",
            model="model",
            project_id=created["id"],
        ))
        db.commit()
    finally:
        db.close()
    detail = endpoints[("GET", "/api/projects/{project_id}")](SimpleNamespace(), created["id"])
    assert detail["sessions"] == []

    user["name"] = "bob"
    assert endpoints[("GET", "/api/projects")](SimpleNamespace()) == []
    for endpoint, args in (
        (endpoints[("GET", "/api/projects/{project_id}")], (created["id"],)),
        (endpoints[("PATCH", "/api/projects/{project_id}")], (created["id"], project_routes.ProjectUpdate(name="No"))),
        (endpoints[("DELETE", "/api/projects/{project_id}")], (created["id"],)),
    ):
        with pytest.raises(HTTPException) as exc:
            endpoint(SimpleNamespace(), *args)
        assert exc.value.status_code == 404


def test_project_session_membership_detaches_without_deleting_messages(monkeypatch):
    endpoints, user, factory, manager, _uploads = _project_routes(monkeypatch)
    project = _create_project(endpoints)
    db = factory()
    try:
        db.add_all([
            database.Session(
                id="alice-session",
                owner="alice",
                name="Alice chat",
                endpoint_url="http://example.test",
                model="model",
            ),
            database.Session(
                id="bob-session",
                owner="bob",
                name="Bob chat",
                endpoint_url="http://example.test",
                model="model",
            ),
        ])
        db.add(database.ChatMessage(
            id="message",
            session_id="alice-session",
            role="user",
            content="Keep this message",
        ))
        db.commit()
    finally:
        db.close()
    manager.sessions["alice-session"] = Session(
        id="alice-session",
        name="Alice chat",
        endpoint_url="http://example.test",
        model="model",
        owner="alice",
    )

    attached = endpoints[("POST", "/api/projects/{project_id}/sessions/{session_id}")](
        SimpleNamespace(), project["id"], "alice-session"
    )
    assert attached["project_id"] == project["id"]
    assert manager.sessions["alice-session"].project_id == project["id"]

    with pytest.raises(HTTPException) as exc:
        endpoints[("POST", "/api/projects/{project_id}/sessions/{session_id}")](
            SimpleNamespace(), project["id"], "bob-session"
        )
    assert exc.value.status_code == 404

    deleted = endpoints[("DELETE", "/api/projects/{project_id}")](
        SimpleNamespace(), project["id"]
    )
    assert deleted == {"id": project["id"], "deleted": True}
    assert manager.sessions["alice-session"].project_id is None
    db = factory()
    try:
        assert db.get(database.Session, "alice-session").project_id is None
        assert db.get(database.ChatMessage, "message") is not None
    finally:
        db.close()


def test_project_file_attachment_is_owner_scoped_and_idempotent(monkeypatch):
    endpoints, _user, factory, _manager, uploads = _project_routes(monkeypatch)
    project = _create_project(endpoints)
    attach = endpoints[("POST", "/api/projects/{project_id}/files")]
    alice_upload_id = "a" * 32 + ".txt"

    first = attach(
        SimpleNamespace(), project["id"], project_routes.ProjectFileAttach(upload_id=alice_upload_id)
    )
    second = attach(
        SimpleNamespace(), project["id"], project_routes.ProjectFileAttach(upload_id=alice_upload_id)
    )
    assert first["id"] == second["id"]
    assert first["filename"] == "alice.txt"

    with pytest.raises(HTTPException) as exc:
        attach(
            SimpleNamespace(),
            project["id"],
            project_routes.ProjectFileAttach(upload_id="b" * 32 + ".txt"),
        )
    assert exc.value.status_code == 404

    db = factory()
    try:
        assert db.query(database.ProjectFile).count() == 1
    finally:
        db.close()

    detached = endpoints[("DELETE", "/api/projects/{project_id}/files/{upload_id}")](
        SimpleNamespace(), project["id"], alice_upload_id
    )
    assert detached == {"upload_id": alice_upload_id, "detached": True}
    assert alice_upload_id in uploads.rows


def test_project_file_references_survive_upload_cleanup(monkeypatch):
    from routes import upload_routes

    endpoints, _user, factory, _manager, _uploads = _project_routes(monkeypatch)
    project = _create_project(endpoints)
    upload_id = "a" * 32 + ".txt"
    endpoints[("POST", "/api/projects/{project_id}/files")](
        SimpleNamespace(), project["id"], project_routes.ProjectFileAttach(upload_id=upload_id)
    )
    monkeypatch.setattr(upload_routes, "SessionLocal", factory)

    referenced_ids, _referenced_hashes = upload_routes._collect_persisted_upload_references()

    assert upload_id in referenced_ids


def test_session_api_validates_and_returns_project_membership(monkeypatch):
    from routes import session_routes
    from src import event_bus

    engine = create_engine("sqlite:///:memory:")
    database.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    project_id = "project"
    db = factory()
    try:
        db.add_all([
            database.Project(id=project_id, owner="alice", name="Project"),
            database.Project(id="bob-project", owner="bob", name="Bob project"),
        ])
        db.commit()
    finally:
        db.close()

    class SessionManager:
        def __init__(self):
            self.sessions = {}

        def create_session(self, **kwargs):
            session = Session(
                id=kwargs["session_id"],
                name=kwargs["name"],
                endpoint_url=kwargs["endpoint_url"],
                model=kwargs["model"],
                rag=kwargs["rag"],
                owner=kwargs["owner"],
                project_id=kwargs.get("project_id"),
            )
            self.sessions[session.id] = session
            return session

        def get_sessions_for_user(self, _user):
            return self.sessions

    manager = SessionManager()
    monkeypatch.setattr(session_routes, "SessionLocal", factory)
    monkeypatch.setattr(session_routes, "effective_user", lambda request: "alice")
    monkeypatch.setattr(session_routes, "storage_owner_for_request", lambda request: "alice")
    monkeypatch.setattr(event_bus, "fire_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        session_routes,
        "router",
        APIRouter(prefix="/api", tags=["sessions"]),
    )
    router = session_routes.setup_session_routes(manager, {})
    endpoints = _endpoints(router)
    request = SimpleNamespace(state=SimpleNamespace(), query_params={})
    create = endpoints[("POST", "/api/session")]

    project_session = create(
        request,
        name="Project chat",
        endpoint_url="",
        model="",
        rag=None,
        skip_validation="true",
        api_key="",
        endpoint_id="",
        project_id=project_id,
    )
    personal_session = create(
        request,
        name="Personal chat",
        endpoint_url="",
        model="",
        rag=None,
        skip_validation="true",
        api_key="",
        endpoint_id="",
        project_id=None,
    )
    assert project_session.project_id == project_id
    assert personal_session.project_id is None

    db = factory()
    try:
        db.add_all([
            database.Session(
                id=project_session.id,
                owner="alice",
                name="Project chat",
                endpoint_url="",
                model="",
                project_id=project_id,
            ),
            database.Session(
                id=personal_session.id,
                owner="alice",
                name="Personal chat",
                endpoint_url="",
                model="",
            ),
            database.Session(
                id="archived",
                owner="alice",
                name="Archived chat",
                endpoint_url="",
                model="",
                project_id=project_id,
                archived=True,
            ),
        ])
        db.commit()
    finally:
        db.close()

    active = endpoints[("GET", "/api/sessions")](request)
    active_projects = {session["id"]: session["project_id"] for session in active}
    assert active_projects == {
        project_session.id: project_id,
        personal_session.id: None,
    }
    archived = endpoints[("GET", "/api/sessions/archived")](request)
    assert archived["sessions"] == [
        {
            "id": "archived",
            "name": "Archived chat",
            "model": "",
            "message_count": 0,
            "created_at": archived["sessions"][0]["created_at"],
            "updated_at": archived["sessions"][0]["updated_at"],
            "is_important": False,
            "project_id": project_id,
        }
    ]

    with pytest.raises(HTTPException) as exc:
        create(
            request,
            name="No project",
            endpoint_url="",
            model="",
            rag=None,
            skip_validation="true",
            api_key="",
            endpoint_id="",
            project_id="missing",
        )
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        create(
            request,
            name="Other user project",
            endpoint_url="",
            model="",
            rag=None,
            skip_validation="true",
            api_key="",
            endpoint_id="",
            project_id="bob-project",
        )
    assert exc.value.status_code == 404
