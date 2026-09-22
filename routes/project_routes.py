import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from core.database import Project, ProjectFile, Session as DbSession, SessionLocal
from src.auth_helpers import (
    effective_user,
    owner_filter,
    require_chat_api_token_scope,
    storage_owner_for_request,
)
from src.upload_handler import reserve_upload_ids


logger = logging.getLogger(__name__)


class ProjectCreate(BaseModel):
    name: str
    instructions: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    instructions: str | None = None


class ProjectFileAttach(BaseModel):
    upload_id: str


def _owner(request: Request) -> str:
    owner = effective_user(request) or storage_owner_for_request(request)
    if not owner:
        raise HTTPException(401, "Authentication required")
    return owner


def _project_or_404(db, project_id: str, owner: str) -> Project:
    query = db.query(Project).filter(Project.id == project_id)
    project = owner_filter(query, Project, owner, include_shared=False).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


def _session_or_404(db, session_id: str, request: Request) -> DbSession:
    query = db.query(DbSession).filter(DbSession.id == session_id)
    user = effective_user(request)
    if user:
        query = owner_filter(query, DbSession, user, include_shared=False)
    session = query.first()
    if not session:
        raise HTTPException(404, "Session not found")
    return session


def _project_sessions_query(db, project_id: str, request: Request):
    query = db.query(DbSession).filter(DbSession.project_id == project_id)
    user = effective_user(request)
    if user:
        return owner_filter(query, DbSession, user, include_shared=False)
    return query


def _project_dict(project: Project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "instructions": project.instructions,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


def _project_file_dict(project_file: ProjectFile) -> dict:
    return {
        "id": project_file.id,
        "upload_id": project_file.upload_id,
        "filename": project_file.filename,
        "mime_type": project_file.mime_type,
        "size": project_file.size,
        "created_at": project_file.created_at.isoformat() if project_file.created_at else None,
    }


def _validate_name(name: str | None) -> str:
    if name is None:
        raise HTTPException(422, "Project name is required")
    name = name.strip()
    if not name:
        raise HTTPException(422, "Project name cannot be blank")
    if len(name) > 100:
        raise HTTPException(422, "Project name must be at most 100 characters")
    return name


def _validate_instructions(instructions: str | None) -> str | None:
    if instructions is not None and len(instructions) > 20000:
        raise HTTPException(422, "Project instructions must be at most 20000 characters")
    return instructions


def _sync_session_project(session_manager, session_id: str, project_id: str | None) -> None:
    session = getattr(session_manager, "sessions", {}).get(session_id)
    if session is not None:
        session.project_id = project_id


def _index_project_file(rag_manager, project: Project, project_file: ProjectFile, upload: dict) -> None:
    if rag_manager is None or not upload.get("path"):
        return
    try:
        result = rag_manager.index_project_file(
            upload["path"],
            owner=project.owner,
            project_id=project.id,
            upload_id=project_file.upload_id,
            filename=project_file.filename,
        )
        if not result.get("success"):
            logger.warning("Project file indexing failed: %s", result.get("message", "unknown error"))
    except Exception:
        logger.warning("Project file indexing failed", exc_info=True)


def _delete_project_chunks(rag_manager, owner: str, project_id: str, upload_id: str | None = None) -> None:
    if rag_manager is None:
        return
    try:
        result = rag_manager.delete_project_chunks(owner, project_id, upload_id)
        if not result.get("success"):
            logger.warning("Project chunk deletion failed: %s", result.get("message", "unknown error"))
    except Exception:
        logger.warning("Project chunk deletion failed", exc_info=True)


def setup_project_routes(session_manager, upload_handler=None, rag_manager=None) -> APIRouter:
    router = APIRouter(
        prefix="/api",
        tags=["projects"],
        dependencies=[Depends(require_chat_api_token_scope)],
    )

    @router.get("/projects")
    def list_projects(request: Request):
        db = SessionLocal()
        try:
            owner = _owner(request)
            projects = owner_filter(
                db.query(Project), Project, owner, include_shared=False
            ).order_by(Project.updated_at.desc()).all()
            return [_project_dict(project) for project in projects]
        finally:
            db.close()

    @router.post("/projects")
    def create_project(request: Request, payload: ProjectCreate):
        db = SessionLocal()
        try:
            project = Project(
                id=str(uuid.uuid4()),
                owner=_owner(request),
                name=_validate_name(payload.name),
                instructions=_validate_instructions(payload.instructions),
            )
            db.add(project)
            db.commit()
            db.refresh(project)
            return _project_dict(project)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @router.get("/projects/{project_id}")
    def get_project(request: Request, project_id: str):
        db = SessionLocal()
        try:
            project = _project_or_404(db, project_id, _owner(request))
            files = db.query(ProjectFile).filter(
                ProjectFile.project_id == project.id
            ).order_by(ProjectFile.created_at.desc()).all()
            session_query = _project_sessions_query(db, project.id, request)
            sessions = [_project_session_dict(session) for session in session_query.order_by(
                DbSession.updated_at.desc()
            ).all()]
            return {
                "project": _project_dict(project),
                "files": [_project_file_dict(project_file) for project_file in files],
                "sessions": sessions,
            }
        finally:
            db.close()

    @router.patch("/projects/{project_id}")
    def update_project(request: Request, project_id: str, payload: ProjectUpdate):
        db = SessionLocal()
        try:
            project = _project_or_404(db, project_id, _owner(request))
            if "name" in payload.model_fields_set:
                project.name = _validate_name(payload.name)
            if "instructions" in payload.model_fields_set:
                project.instructions = _validate_instructions(payload.instructions)
            db.commit()
            db.refresh(project)
            return _project_dict(project)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @router.delete("/projects/{project_id}")
    def delete_project(request: Request, project_id: str):
        db = SessionLocal()
        try:
            project = _project_or_404(db, project_id, _owner(request))
            project_owner = project.owner
            session_query = _project_sessions_query(db, project.id, request)
            session_ids = [session.id for session in session_query.all()]
            session_query.update(
                {DbSession.project_id: None}, synchronize_session=False
            )
            db.query(ProjectFile).filter(ProjectFile.project_id == project.id).delete(
                synchronize_session=False
            )
            db.delete(project)
            db.commit()
            _delete_project_chunks(rag_manager, project_owner, project_id)
            for session_id in session_ids:
                _sync_session_project(session_manager, session_id, None)
            return {"id": project_id, "deleted": True}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @router.post("/projects/{project_id}/files")
    def attach_project_file(request: Request, project_id: str, payload: ProjectFileAttach):
        db = SessionLocal()
        try:
            project = _project_or_404(db, project_id, _owner(request))
            user = effective_user(request)
            if upload_handler is None:
                raise HTTPException(404, "Upload not found")
            upload = upload_handler.resolve_upload(
                payload.upload_id,
                owner=user,
                allow_admin=False,
            )
            if not isinstance(upload, dict):
                raise HTTPException(404, "Upload not found")
            missing_upload_id = reserve_upload_ids(upload_handler, user, [payload.upload_id])
            if missing_upload_id:
                raise HTTPException(404, "Upload not found")
            existing = db.query(ProjectFile).filter(
                ProjectFile.project_id == project.id,
                ProjectFile.upload_id == payload.upload_id,
            ).first()
            if existing:
                return _project_file_dict(existing)
            project_file = ProjectFile(
                id=str(uuid.uuid4()),
                project_id=project.id,
                upload_id=payload.upload_id,
                filename=str(upload.get("name") or ""),
                mime_type=str(upload.get("mime") or "application/octet-stream"),
                size=int(upload.get("size") or 0),
            )
            db.add(project_file)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                existing = db.query(ProjectFile).filter(
                    ProjectFile.project_id == project.id,
                    ProjectFile.upload_id == payload.upload_id,
                ).first()
                if existing:
                    return _project_file_dict(existing)
                raise
            db.refresh(project_file)
            _index_project_file(rag_manager, project, project_file, upload)
            return _project_file_dict(project_file)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @router.delete("/projects/{project_id}/files/{upload_id}")
    def detach_project_file(request: Request, project_id: str, upload_id: str):
        db = SessionLocal()
        try:
            project = _project_or_404(db, project_id, _owner(request))
            project_file = db.query(ProjectFile).filter(
                ProjectFile.project_id == project.id,
                ProjectFile.upload_id == upload_id,
            ).first()
            if not project_file:
                raise HTTPException(404, "Project file not found")
            db.delete(project_file)
            db.commit()
            _delete_project_chunks(rag_manager, project.owner, project.id, upload_id)
            return {"upload_id": upload_id, "detached": True}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @router.post("/projects/{project_id}/sessions/{session_id}")
    def attach_project_session(request: Request, project_id: str, session_id: str):
        db = SessionLocal()
        try:
            project = _project_or_404(db, project_id, _owner(request))
            session = _session_or_404(db, session_id, request)
            session.project_id = project.id
            db.commit()
            _sync_session_project(session_manager, session.id, project.id)
            return _project_session_dict(session)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @router.delete("/projects/{project_id}/sessions/{session_id}")
    def detach_project_session(request: Request, project_id: str, session_id: str):
        db = SessionLocal()
        try:
            project = _project_or_404(db, project_id, _owner(request))
            session = _session_or_404(db, session_id, request)
            if session.project_id != project.id:
                raise HTTPException(404, "Session not found")
            session.project_id = None
            db.commit()
            _sync_session_project(session_manager, session.id, None)
            return _project_session_dict(session)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    return router


def _project_session_dict(session: DbSession) -> dict:
    return {
        "id": session.id,
        "name": session.name,
        "model": session.model,
        "project_id": session.project_id,
    }
