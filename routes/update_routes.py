"""Admin endpoints for the opt-in native updater."""

import asyncio
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from core.middleware import require_admin
from src.owner_identity import auth_disabled

SERVICE = "odysseus-update.service"
STATUS_FIELDS = ("state", "message", "old_commit", "target_commit", "updated_at")


def _status_path():
    from src.constants import DATA_DIR
    return os.path.join(DATA_DIR, "update-status.json")


def _status_payload():
    status = {"enabled": True, "state": "unknown", "active": False}
    try:
        with open(_status_path(), encoding="utf-8") as stream:
            saved = json.load(stream)
        if isinstance(saved, dict):
            status.update({key: saved[key] for key in STATUS_FIELDS if isinstance(saved.get(key), str)})
    except (OSError, ValueError, TypeError, KeyError):
        pass
    status["active"] = status["state"] == "running"
    if status["active"] and status.get("updated_at"):
        try:
            started = datetime.fromisoformat(status["updated_at"].replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - started).total_seconds() > 10:
                result = subprocess.run(
                    ["systemctl", "--user", "show", SERVICE, "--property=ActiveState", "--property=Job"],
                    capture_output=True, text=True, timeout=3,
                )
                properties = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
                if result.returncode == 0 and properties.get("Job") in ("", "0") and properties.get("ActiveState") in ("inactive", "failed"):
                    _write_status("failed", "Update service stopped before reporting status")
                    status = _status_payload()
        except (ValueError, TypeError, OSError, subprocess.TimeoutExpired):
            pass
    return status


def _write_status(state, message):
    path = _status_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=os.path.dirname(path), delete=False) as stream:
        tmp = stream.name
        json.dump({"state": state, "message": message, "updated_at": datetime.now(timezone.utc).isoformat()}, stream)
    try:
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _check_access(request):
    require_admin(request)
    manager = getattr(request.app.state, "auth_manager", None)
    user = getattr(request.state, "current_user", None)
    if auth_disabled() or not manager or not manager.is_configured or not user or not manager.is_admin(user):
        raise HTTPException(403, "Admin only")
    if os.environ.get("ODYSSEUS_SELF_UPDATE") != "true":
        raise HTTPException(404, "Self-update is disabled")


def _start_update():
    import fcntl
    from src.constants import DATA_DIR
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "update-trigger.lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if _status_payload()["active"]:
            raise HTTPException(409, "An update is already in progress")
        _write_status("running", "Update requested")
        try:
            result = subprocess.run(
                ["systemctl", "--user", "start", "--no-block", SERVICE],
                capture_output=True, timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            result = None
        if result is None or result.returncode:
            _write_status("failed", "Could not start update service")
            raise HTTPException(500, "Could not start update service")
    return {"ok": True, "state": "running"}


def setup_update_routes():
    router = APIRouter(tags=["update"])

    @router.get("/api/admin/update/status")
    async def update_status(request: Request):
        _check_access(request)
        return await asyncio.to_thread(_status_payload)

    @router.post("/api/admin/update")
    async def trigger_update(request: Request):
        _check_access(request)
        return await asyncio.to_thread(_start_update)

    return router
