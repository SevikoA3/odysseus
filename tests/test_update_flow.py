"""Tests for the Phase 7 native self-update backend.

Covers:
- scripts/update_odysseus behavior via bash -n syntax check and isolated
  disposable git repositories (dirty worktree, non-fast-forward, clean
  no-update, success path, backup failure, dependency failure).
- routes/update_routes.py: disabled endpoints, non-admin denial, trigger
  argument array, concurrent request rejection, status payload.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import types
from types import SimpleNamespace

import pytest

from fastapi import HTTPException

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPDATE_SCRIPT = os.path.join(REPO, "scripts", "update_odysseus")

# ---------------------------------------------------------------------------
# Shell syntax check
# ---------------------------------------------------------------------------


def test_update_script_syntax():
    proc = subprocess.run(["bash", "-n", UPDATE_SCRIPT], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_update_script_executable():
    mode = os.stat(UPDATE_SCRIPT).st_mode
    assert mode & stat.S_IXUSR


# ---------------------------------------------------------------------------
# Isolated repository harness
#
# The update script resolves its repository root from its own location, so
# each test clones the remote, drops the script into <clone>/scripts (tracked
# in the initial commit so it never counts as dirty), and runs it from there.
# ---------------------------------------------------------------------------


def _git(repo, *args):
    proc = subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _init_repo_with_remote(tmpdir):
    """origin bare remote + a clone with one commit on main containing the
    update script, requirements.txt and install-service.sh."""
    remote = os.path.join(tmpdir, "remote.git")
    clone = os.path.join(tmpdir, "clone")
    subprocess.run(["git", "init", "--bare", "-q", remote], check=True)
    subprocess.run(["git", "clone", "-q", remote, clone], check=True)
    _git(clone, "config", "user.email", "t@example.com")
    _git(clone, "config", "user.name", "T")
    with open(os.path.join(clone, "requirements.txt"), "w") as f:
        f.write("# deps\n")
    with open(os.path.join(clone, ".gitignore"), "w") as f:
        f.write("data/\nvenv/\n")
    shutil.copy(os.path.join(REPO, "install-service.sh"), clone)
    os.makedirs(os.path.join(clone, "systemd"))
    for name in ("odysseus-ui.service.in", "odysseus-update.service.in"):
        shutil.copy(os.path.join(REPO, "systemd", name), os.path.join(clone, "systemd"))
    os.makedirs(os.path.join(clone, "scripts"), exist_ok=True)
    shutil.copy(UPDATE_SCRIPT, os.path.join(clone, "scripts", "update_odysseus"))
    _git(clone, "add", "-A")
    _git(clone, "commit", "-q", "-m", "init")
    _git(clone, "push", "-q", "origin", "HEAD:refs/heads/main")
    _git(clone, "branch", "-M", "main")
    _git(clone, "pull", "-q", "--ff-only", "origin", "main")
    return remote, clone


def _fake_tools(tmpdir, clone):
    """Stub venv python and systemctl. The venv python is a fake interpreter
    (pip install succeeds); systemctl records its call in calls.log."""
    bindir = os.path.join(tmpdir, "bin")
    os.makedirs(bindir, exist_ok=True)
    venvdir = os.path.join(clone, "venv")
    os.makedirs(os.path.join(venvdir, "bin"), exist_ok=True)
    with open(os.path.join(venvdir, "bin", "python"), "w") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(os.path.join(venvdir, "bin", "python"), 0o755)

    systm = os.path.join(bindir, "systemctl")
    with open(systm, "w") as f:
        f.write(
            "#!/bin/sh\n"
            f"echo systemctl \"$@\" >> {tmpdir}/calls.log\n"
            f'if [ "$2" = restart ]; then git -C "{clone}" rev-parse HEAD > "{tmpdir}/running_commit"; fi\n'
            "exit 0\n"
        )
    os.chmod(systm, 0o755)
    return venvdir, bindir


def _fake_backup(tmpdir, exit_code=0):
    path = os.path.join(tmpdir, "bin", "odysseus-backup")
    with open(path, "w") as f:
        f.write(f"#!/bin/sh\nexit {exit_code}\n")
    os.chmod(path, 0o755)
    return path


def _run_update(clone, env_extra=None):
    env = dict(os.environ)
    env.setdefault("LC_ALL", "C")
    env["ODYSSEUS_SELF_UPDATE"] = "true"
    env["XDG_CONFIG_HOME"] = os.path.join(os.path.dirname(clone), "config")
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["/bin/sh", os.path.join(clone, "scripts", "update_odysseus")],
        cwd=clone,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _read_status(clone):
    path = os.path.join(clone, "data", "update-status.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _advance_origin(clone, n=1):
    """Commit n empty commits on the clone, push them, then reset the clone
    back so local HEAD is n commits behind origin/main."""
    for i in range(n):
        _git(clone, "commit", "-q", "--allow-empty", "-m", f"advance {i}")
    _git(clone, "push", "-q", "origin", "main")
    _git(clone, "reset", "-q", "--hard", f"HEAD~{n}")


# ---------------------------------------------------------------------------
# Update script behavior in isolated repos
# ---------------------------------------------------------------------------


def test_dirty_worktree_untracked_rejected(tmp_path):
    tmpdir = str(tmp_path)
    _remote, clone = _init_repo_with_remote(tmpdir)
    with open(os.path.join(clone, "dirty.txt"), "w") as f:
        f.write("untracked\n")
    proc = _run_update(clone)
    assert proc.returncode != 0
    status = _read_status(clone)
    assert status["state"] == "failed"
    assert "dirty" in status["message"].lower()


def test_update_script_disabled(tmp_path):
    _remote, clone = _init_repo_with_remote(str(tmp_path))
    proc = _run_update(clone, {"ODYSSEUS_SELF_UPDATE": "false"})
    assert proc.returncode != 0
    assert _read_status(clone)["message"] == "Self-update is disabled"


def test_dirty_tracked_worktree_rejected(tmp_path):
    tmpdir = str(tmp_path)
    _remote, clone = _init_repo_with_remote(tmpdir)
    with open(os.path.join(clone, "requirements.txt"), "a") as f:
        f.write("# local change\n")
    proc = _run_update(clone)
    assert proc.returncode != 0
    assert _read_status(clone)["state"] == "failed"


def test_non_fast_forward_rejected(tmp_path):
    tmpdir = str(tmp_path)
    remote, clone = _init_repo_with_remote(tmpdir)
    # Diverge: a new root commit is force-pushed to origin/main while local
    # main stays on the old line, so origin/main is not a descendant of HEAD.
    subprocess.run(["git", "-C", clone, "checkout", "--orphan", "diverged"], check=True)
    _git(clone, "add", "-A")
    _git(clone, "commit", "-q", "-m", "diverged root")
    _git(clone, "push", "-q", "--force", "origin", "diverged:refs/heads/main")
    _git(clone, "checkout", "-q", "main")
    # Provide a venv so the preflight passes and the run reaches the
    # fast-forward check rather than failing earlier on the missing venv.
    venvdir, bindir = _fake_tools(tmpdir, clone)
    proc = _run_update(
        clone,
        {"ODYSSEUS_VENV_DIR": venvdir, "PATH": f"{bindir}:{os.environ['PATH']}"},
    )
    assert proc.returncode != 0
    status = _read_status(clone)
    assert status["state"] == "failed"
    assert "fast-forward" in status["message"].lower()


def test_clean_no_update(tmp_path):
    tmpdir = str(tmp_path)
    _remote, clone = _init_repo_with_remote(tmpdir)
    venvdir, bindir = _fake_tools(tmpdir, clone)
    proc = _run_update(
        clone,
        {"ODYSSEUS_VENV_DIR": venvdir, "PATH": f"{bindir}:{os.environ['PATH']}"},
    )
    assert proc.returncode == 0, proc.stderr
    status = _read_status(clone)
    assert status["state"] == "up_to_date"
    # No restart, no pip run: fake tools never invoked.
    assert not os.path.exists(os.path.join(tmpdir, "calls.log"))


def test_wrong_branch_rejected(tmp_path):
    _remote, clone = _init_repo_with_remote(str(tmp_path))
    proc = _run_update(clone, {"ODYSSEUS_UPDATE_BRANCH": "other"})
    assert proc.returncode != 0
    assert "branch" in _read_status(clone)["message"].lower()


def test_update_lock_rejects_second_process(tmp_path):
    _remote, clone = _init_repo_with_remote(str(tmp_path))
    os.makedirs(os.path.join(clone, "data"))
    with open(os.path.join(clone, "data", "odysseus-update.lock"), "w") as lock:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX)
        proc = _run_update(clone)
    assert proc.returncode != 0
    assert _read_status(clone) is None


def test_success_flow(tmp_path):
    tmpdir = str(tmp_path)
    remote, clone = _init_repo_with_remote(tmpdir)
    old = _git(clone, "rev-parse", "HEAD")
    _advance_origin(clone)
    target = _git(clone, "rev-parse", "origin/main")

    venvdir, bindir = _fake_tools(tmpdir, clone)
    _fake_backup(tmpdir)

    proc = _run_update(
        clone,
        {
            "ODYSSEUS_VENV_DIR": venvdir,
            "ODYSSEUS_BACKUP_CMD": os.path.join(bindir, "odysseus-backup"),
            "PATH": f"{bindir}:{os.environ['PATH']}",
        },
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert _git(clone, "rev-parse", "HEAD") == target
    status = _read_status(clone)
    assert status["state"] == "success"
    assert status["old_commit"] == old
    assert status["target_commit"] == target
    # Restart happened.
    with open(os.path.join(tmpdir, "calls.log")) as f:
        calls = f.read()
    assert "restart" in calls
    assert "odysseus-ui.service" in calls
    assert "enable --now" not in calls
    with open(os.path.join(tmpdir, "running_commit")) as stream:
        assert stream.read().strip() == target


def test_status_replaced_atomically(tmp_path):
    _remote, clone = _init_repo_with_remote(str(tmp_path))
    venvdir, bindir = _fake_tools(str(tmp_path), clone)
    status_file = os.path.join(clone, "data", "update-status.json")
    os.makedirs(os.path.dirname(status_file))
    with open(status_file, "w") as stream:
        stream.write('{"state":"old"}')
    old_inode = os.stat(status_file).st_ino
    proc = _run_update(clone, {"ODYSSEUS_VENV_DIR": venvdir, "PATH": f"{bindir}:{os.environ['PATH']}"})
    assert proc.returncode == 0
    assert _read_status(clone)["state"] == "up_to_date"
    assert os.stat(status_file).st_ino != old_inode


def test_status_no_secrets(tmp_path):
    tmpdir = str(tmp_path)
    _remote, clone = _init_repo_with_remote(tmpdir)
    _git(clone, "remote", "set-url", "origin", "https://user:hunter2@127.0.0.1:1/repo.git")
    venvdir, bindir = _fake_tools(tmpdir, clone)
    proc = _run_update(clone, {"ODYSSEUS_VENV_DIR": venvdir, "PATH": f"{bindir}:{os.environ['PATH']}"})
    assert proc.returncode != 0
    assert _read_status(clone)["message"] == "Update fetch failed"
    raw = open(os.path.join(clone, "data", "update-status.json")).read()
    assert "hunter2" not in raw


def test_backup_failure_aborts_before_merge(tmp_path):
    tmpdir = str(tmp_path)
    remote, clone = _init_repo_with_remote(tmpdir)
    old = _git(clone, "rev-parse", "HEAD")
    _advance_origin(clone)

    venvdir, bindir = _fake_tools(tmpdir, clone)
    _fake_backup(tmpdir, exit_code=1)

    proc = _run_update(
        clone,
        {
            "ODYSSEUS_VENV_DIR": venvdir,
            "ODYSSEUS_BACKUP_CMD": os.path.join(bindir, "odysseus-backup"),
            "PATH": f"{bindir}:{os.environ['PATH']}",
        },
    )
    assert proc.returncode != 0
    status = _read_status(clone)
    assert status["state"] == "failed"
    assert "backup" in status["message"].lower()
    # Running process untouched: worktree still at old commit, no restart.
    assert _git(clone, "rev-parse", "HEAD") == old
    assert not os.path.exists(os.path.join(tmpdir, "calls.log"))


def test_failing_dependency_install_does_not_restart(tmp_path):
    tmpdir = str(tmp_path)
    remote, clone = _init_repo_with_remote(tmpdir)
    old = _git(clone, "rev-parse", "HEAD")
    _advance_origin(clone)

    venvdir, bindir = _fake_tools(tmpdir, clone)
    _fake_backup(tmpdir)
    # venv python that always fails (pip install fails).
    with open(os.path.join(venvdir, "bin", "python"), "w") as f:
        f.write("#!/bin/sh\nexit 1\n")
    os.chmod(os.path.join(venvdir, "bin", "python"), 0o755)

    proc = _run_update(
        clone,
        {
            "ODYSSEUS_VENV_DIR": venvdir,
            "ODYSSEUS_BACKUP_CMD": os.path.join(bindir, "odysseus-backup"),
            "PATH": f"{bindir}:{os.environ['PATH']}",
        },
    )
    assert proc.returncode != 0
    status = _read_status(clone)
    assert status["state"] == "failed"
    assert "dependency" in status["message"].lower()
    # No automatic rollback. The running app is never restarted.
    assert _git(clone, "rev-parse", "HEAD") != old
    assert not os.path.exists(os.path.join(tmpdir, "calls.log"))


def test_setup_failure_does_not_restart(tmp_path):
    tmpdir = str(tmp_path)
    _remote, clone = _init_repo_with_remote(tmpdir)
    _advance_origin(clone)
    venvdir, bindir = _fake_tools(tmpdir, clone)
    _fake_backup(tmpdir)
    with open(os.path.join(bindir, "systemctl"), "w") as stream:
        stream.write(f'#!/bin/sh\necho "$@" >> {tmpdir}/calls.log\n[ "$2" != enable ]\n')
    proc = _run_update(clone, {
        "ODYSSEUS_VENV_DIR": venvdir,
        "ODYSSEUS_BACKUP_CMD": os.path.join(bindir, "odysseus-backup"),
        "PATH": f"{bindir}:{os.environ['PATH']}",
    })
    assert proc.returncode != 0
    assert _read_status(clone)["message"] == "Service setup failed"
    assert "restart" not in open(os.path.join(tmpdir, "calls.log")).read()


def test_missing_backup_cmd_fails_clean(tmp_path):
    tmpdir = str(tmp_path)
    remote, clone = _init_repo_with_remote(tmpdir)
    old = _git(clone, "rev-parse", "HEAD")
    _advance_origin(clone)

    venvdir, bindir = _fake_tools(tmpdir, clone)
    proc = _run_update(
        clone,
        {
            "ODYSSEUS_VENV_DIR": venvdir,
            "ODYSSEUS_BACKUP_CMD": os.path.join(tmpdir, "nonexistent-backup"),
            "PATH": f"{bindir}:{os.environ['PATH']}",
        },
    )
    assert proc.returncode != 0
    assert _read_status(clone)["state"] == "failed"
    assert _git(clone, "rev-parse", "HEAD") == old


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------


@pytest.fixture
def update_routes_mod(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "python_multipart", types.ModuleType("python_multipart"))
    monkeypatch.delitem(sys.modules, "routes.update_routes", raising=False)
    import src.constants as constants
    monkeypatch.setattr(constants, "DATA_DIR", str(tmp_path))
    import routes.update_routes as mod
    return mod


def _endpoints(router):
    return {
        (method, route.path): route.endpoint
        for route in router.routes
        for method in (route.methods or ())
    }


def _req(is_admin=True):
    """Fake request satisfying require_admin: auth disabled when no
    auth_manager is configured; admin check via is_admin otherwise."""
    return SimpleNamespace(
        headers={},
        state=SimpleNamespace(current_user="alice"),
        app=SimpleNamespace(
            state=SimpleNamespace(
                auth_manager=SimpleNamespace(
                    is_configured=True, is_admin=lambda u: is_admin
                )
            )
        ),
    )


def test_disabled_endpoints(update_routes_mod, monkeypatch):
    import asyncio
    monkeypatch.setenv("ODYSSEUS_SELF_UPDATE", "false")
    endpoints = _endpoints(update_routes_mod.setup_update_routes())
    with pytest.raises(HTTPException) as ei:
        asyncio.run(endpoints[("GET", "/api/admin/update/status")](_req()))
    assert ei.value.status_code == 404
    with pytest.raises(HTTPException) as ei:
        asyncio.run(endpoints[("POST", "/api/admin/update")](_req()))
    assert ei.value.status_code == 404


def test_non_admin_denied(update_routes_mod, monkeypatch):
    import asyncio
    monkeypatch.setenv("ODYSSEUS_SELF_UPDATE", "true")
    monkeypatch.setattr(
        update_routes_mod, "require_admin",
        lambda request: (_ for _ in ()).throw(HTTPException(403, "Admin only")),
    )
    endpoints = _endpoints(update_routes_mod.setup_update_routes())
    with pytest.raises(HTTPException) as ei:
        asyncio.run(endpoints[("POST", "/api/admin/update")](_req()))
    assert ei.value.status_code == 403


def test_auth_disabled_denied(update_routes_mod, monkeypatch):
    import asyncio
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("ODYSSEUS_SELF_UPDATE", "true")
    endpoint = _endpoints(update_routes_mod.setup_update_routes())[("POST", "/api/admin/update")]
    with pytest.raises(HTTPException) as error:
        asyncio.run(endpoint(_req()))
    assert error.value.status_code == 403


def test_trigger_concurrent_rejected(update_routes_mod, monkeypatch):
    import asyncio
    monkeypatch.setenv("ODYSSEUS_SELF_UPDATE", "true")
    monkeypatch.setattr(
        update_routes_mod, "_status_payload",
        lambda: {"enabled": True, "state": "running", "active": True},
    )
    called = []
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: called.append(a) or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    endpoints = _endpoints(update_routes_mod.setup_update_routes())
    with pytest.raises(HTTPException) as ei:
        asyncio.run(endpoints[("POST", "/api/admin/update")](_req()))
    assert ei.value.status_code == 409
    assert not called


def test_trigger_argument_array_no_shell(update_routes_mod, monkeypatch):
    import asyncio
    monkeypatch.setenv("ODYSSEUS_SELF_UPDATE", "true")
    monkeypatch.setattr(
        update_routes_mod, "_status_payload",
        lambda: {"enabled": True, "state": "idle", "active": False},
    )
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["shell"] = kwargs.get("shell", False)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    endpoints = _endpoints(update_routes_mod.setup_update_routes())
    result = asyncio.run(endpoints[("POST", "/api/admin/update")](_req()))
    assert result == {"ok": True, "state": "running"}
    assert captured["argv"] == [
        "systemctl", "--user", "start", "--no-block", "odysseus-update.service",
    ]
    assert captured["shell"] is False


def test_second_trigger_rejected_after_first(update_routes_mod, monkeypatch):
    import asyncio
    monkeypatch.setenv("ODYSSEUS_SELF_UPDATE", "true")
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append(args) or SimpleNamespace(returncode=0))
    endpoint = _endpoints(update_routes_mod.setup_update_routes())[("POST", "/api/admin/update")]
    asyncio.run(endpoint(_req()))
    with pytest.raises(HTTPException) as error:
        asyncio.run(endpoint(_req()))
    assert error.value.status_code == 409
    assert len(calls) == 1


def test_trigger_start_failure_500(update_routes_mod, monkeypatch):
    import asyncio
    monkeypatch.setenv("ODYSSEUS_SELF_UPDATE", "true")
    monkeypatch.setattr(
        update_routes_mod, "_status_payload",
        lambda: {"enabled": True, "state": "idle", "active": False},
    )
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="no unit"),
    )
    endpoints = _endpoints(update_routes_mod.setup_update_routes())
    with pytest.raises(HTTPException) as ei:
        asyncio.run(endpoints[("POST", "/api/admin/update")](_req()))
    assert ei.value.status_code == 500
    with open(update_routes_mod._status_path()) as stream:
        assert json.load(stream)["state"] == "failed"


def test_status_payload_reads_data_dir(tmp_path, update_routes_mod, monkeypatch):
    monkeypatch.setenv("ODYSSEUS_SELF_UPDATE", "true")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "update-status.json").write_text(
        json.dumps({"state": "success", "message": "updated to abc", "secret": "hunter2"})
    )
    import src.constants as constants
    monkeypatch.setattr(constants, "DATA_DIR", str(data_dir))
    payload = update_routes_mod._status_payload()
    assert payload["state"] == "success"
    assert payload["enabled"] is True
    assert "secret" not in payload


def test_status_payload_missing_file(tmp_path, update_routes_mod, monkeypatch):
    monkeypatch.setenv("ODYSSEUS_SELF_UPDATE", "true")
    import src.constants as constants
    monkeypatch.setattr(constants, "DATA_DIR", str(tmp_path))
    payload = update_routes_mod._status_payload()
    assert payload["state"] == "unknown"
    assert payload["active"] is False


def test_status_payload_running_is_active(tmp_path, update_routes_mod, monkeypatch):
    monkeypatch.setenv("ODYSSEUS_SELF_UPDATE", "true")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "update-status.json").write_text(json.dumps({"state": "running"}))
    import src.constants as constants
    monkeypatch.setattr(constants, "DATA_DIR", str(data_dir))
    assert update_routes_mod._status_payload()["active"] is True


def test_stale_running_status_reports_failed_service(tmp_path, update_routes_mod, monkeypatch):
    monkeypatch.setenv("ODYSSEUS_SELF_UPDATE", "true")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "update-status.json").write_text(json.dumps({
        "state": "running", "updated_at": "2000-01-01T00:00:00Z",
    }))
    import src.constants as constants
    monkeypatch.setattr(constants, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout="ActiveState=failed\nJob=0\n",
    ))
    assert update_routes_mod._status_payload()["state"] == "failed"
