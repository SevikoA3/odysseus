# Odysseus Projects and Native Updater Implementation Plan

Status: planned

Target deployment: native Python, project venv, systemd user services

Target branch for VM updates: `main`

## Executor Rules

- [ ] Read `AGENTS.md` and `/home/seviko/.codex/RTK.md` before changing code.
- [ ] Prefix shell commands with `rtk`.
- [x] Activate the project virtual environment with `source venv/bin/activate` before Python or package commands. Use `venv/bin/python` for non-interactive commands.
- [ ] Run one phase at a time.
- [ ] Do not start the next phase until the current phase gate passes.
- [ ] Mark a checkbox complete only after its implementation and verification pass.
- [ ] Before ending a phase, mark every passed checklist item complete.
- [ ] Keep unrelated user changes untouched.
- [ ] Do not edit files under `specs/` unless the user expands scope.
- [ ] Reuse existing upload, extraction, RAG, session, auth, and settings paths.
- [ ] Add no dependency unless existing code and Python standard library cannot cover the requirement.
- [ ] Record blockers and failed checks in the Execution Log at the end of this file.

## Fixed Product Decisions

- [ ] Projects are private and owner-scoped.
- [ ] A project contains a name, instructions, files, and chats.
- [ ] Existing chats can move into or out of a project.
- [ ] Deleting a project detaches its chats instead of deleting them.
- [ ] Removing a project file removes its project reference and RAG chunks. Upload cleanup removes unreferenced bytes later.
- [ ] Project instructions apply to every chat in that project.
- [ ] Project files enter model context as untrusted content.
- [ ] Project file retrieval must filter by both owner and project ID.
- [ ] Chats outside a project must never retrieve project-scoped chunks.
- [ ] Cross-chat transcript memory is not part of MVP.
- [ ] Project sharing, icons, colors, connectors, and per-project default models are not part of MVP.
- [ ] Native self-update is disabled unless `ODYSSEUS_SELF_UPDATE=true`.
- [ ] Browser requests cannot supply a command, repository path, remote, or branch.

## Definition of Done

- [ ] User can create, rename, edit, and delete a project.
- [ ] User can create a chat inside a project.
- [ ] User can move an existing chat into or out of a project.
- [ ] Project instructions affect every project chat and no other chat.
- [ ] Project files are available across chats in the same project.
- [ ] Retrieval cannot cross owner or project boundaries.
- [ ] Upload cleanup preserves files referenced by a project.
- [ ] Existing non-project chats keep current behavior.
- [ ] Admin can trigger a safe native update from Settings when explicitly enabled.
- [ ] Dirty worktrees and non-fast-forward updates are rejected.
- [ ] Focused backend, security, JavaScript, shell, and systemd checks pass.

## Phase 0: Baseline and Flow Confirmation

### Repository baseline

- [x] Confirm worktree state with `rtk git status --short`.
- [x] Record existing changes before editing.
- [x] Confirm current session flow through `routes/session_routes.py`, `core/session_manager.py`, and `core/models.py`.
- [x] Confirm prompt flow through `routes/chat_helpers.py` and `src/chat_processor.py`.
- [x] Confirm upload lifecycle through `routes/upload_routes.py` and `src/upload_handler.py`.
- [x] Confirm RAG write/search/delete paths through `src/rag_vector.py` and `src/rag_manager.py`.
- [x] Confirm Settings System ownership through `static/index.html`, `static/js/admin.js`, and `static/js/settings/registry.js`.
- [x] Select and record focused baseline tests covering sessions, uploads, RAG, auth, and settings.
- [x] Run selected baseline tests before implementation.

### Phase gate

- [x] Baseline failures are documented and distinguished from new failures.
- [x] No production file has changed during this phase.

## Phase 1: Database and Session Model

### Database schema

- [x] Add `Project` to `core/database.py`.
- [x] Add owner-indexed `Project.owner`.
- [x] Add required `Project.name` with a 100-character API limit.
- [x] Add nullable `Project.instructions` with a 20,000-character API limit.
- [x] Add project timestamps using the repository timestamp pattern.
- [x] Add `ProjectFile` to `core/database.py`.
- [x] Store `project_id`, `upload_id`, filename, MIME type, size, and creation timestamp.
- [x] Add a uniqueness constraint for `(project_id, upload_id)`.
- [x] Add nullable, indexed `Session.project_id`.
- [x] Configure project deletion to leave sessions intact.

### Existing database migration

- [x] Add an idempotent migration for `sessions.project_id`.
- [x] Add the project ID index idempotently.
- [x] Ensure fresh databases create project tables through SQLAlchemy metadata.
- [x] Register the migration in the existing startup migration sequence.
- [x] Do not rewrite existing session rows.

### In-memory session model

- [x] Add `project_id` to `core.models.Session`.
- [x] Load `project_id` in `core.session_manager.SessionManager`.
- [x] Accept `project_id` in `SessionManager.create_session()`.
- [x] Persist `project_id` when creating a session.
- [x] Include `project_id` in database session serialization where applicable.

### Verification

- [x] Add a focused migration test for a legacy database without `project_id`.
- [x] Add a fresh-schema test for `projects` and `project_files`.
- [x] Add a session persistence test for nullable `project_id`.
- [x] Run focused database and session tests.

### Phase gate

- [x] Existing sessions load unchanged.
- [x] A session can persist and reload a valid project ID.
- [x] Re-running migrations changes nothing.

## Phase 2: Owner-Scoped Project API

### Routes

- [x] Add `routes/project_routes.py`.
- [x] Register project routes in `app.py`.
- [x] Implement `GET /api/projects`.
- [x] Implement `POST /api/projects`.
- [x] Implement `GET /api/projects/{project_id}`.
- [x] Implement `PATCH /api/projects/{project_id}`.
- [x] Implement `DELETE /api/projects/{project_id}`.
- [x] Implement `POST /api/projects/{project_id}/files`.
- [x] Implement `DELETE /api/projects/{project_id}/files/{upload_id}`.
- [x] Implement `POST /api/projects/{project_id}/sessions/{session_id}`.
- [x] Implement `DELETE /api/projects/{project_id}/sessions/{session_id}`.

### Validation and ownership

- [x] Use `effective_user()` and existing owner-filter helpers.
- [x] Return 404 for inaccessible project IDs to avoid ownership disclosure.
- [x] Validate project name and instructions at the API boundary.
- [x] Reject blank project names.
- [x] Validate session ownership before moving a chat.
- [x] Validate upload ownership with `UploadHandler.resolve_upload()`.
- [x] Reserve attached upload IDs with `reserve_upload_ids()` before committing `ProjectFile`.
- [x] Make duplicate file attachment idempotent or return a stable conflict response.

### Session API integration

- [x] Accept optional `project_id` in `POST /session`.
- [x] Validate project ownership before creating the session.
- [x] Return `project_id` from active and archived session responses.
- [x] Keep `project_id=None` behavior unchanged.
- [x] Update in-memory session state when moving a chat.

### Deletion semantics

- [x] Detach all project sessions in the same database transaction before deleting a project.
- [x] Delete project file associations in the same transaction.
- [x] Defer project RAG chunk deletion until the Phase 4 lifecycle function exists.
- [x] Do not delete chat transcripts.
- [x] Do not delete upload bytes directly.

### Upload cleanup integration

- [x] Include every `ProjectFile.upload_id` in `_collect_persisted_upload_references()`.
- [x] Preserve fail-closed cleanup behavior if project reference scanning fails.

### Verification

- [x] Test project CRUD for the owner.
- [x] Test project CRUD denial for another user.
- [x] Test chat move into and out of a project.
- [x] Test cross-owner chat move denial.
- [x] Test upload attachment ownership.
- [x] Test project deletion detaches chats.
- [x] Test project deletion does not delete messages.
- [x] Test project references prevent upload cleanup.

### Phase gate

- [x] Project CRUD and chat membership work without prompt or UI changes.
- [x] Owner isolation tests pass.
- [x] Upload cleanup safety tests pass.

## Phase 3: Project Instructions in Chat Context

### Context loading

- [ ] Load the project using both `session.project_id` and effective owner.
- [ ] Treat missing, deleted, or inaccessible projects as a closed failure, not shared context.
- [ ] Pass project instructions through the shared chat context path.
- [ ] Cover both synchronous and streaming chat through the shared helper.
- [ ] Cover agent mode through the same context construction path.

### Prompt ordering

- [ ] Keep the selected preset system prompt first.
- [ ] Add project instructions after the preset.
- [ ] Keep `UNTRUSTED_CONTEXT_POLICY` active.
- [ ] Keep project instructions stable across turns for prompt-cache reuse.
- [ ] Do not copy project instructions into persisted user messages.
- [ ] Do not place project file contents in a system message.

### Verification

- [ ] Test instructions appear in every chat inside the project.
- [ ] Test instructions do not appear outside the project.
- [ ] Test one user's project instructions cannot enter another user's chat.
- [ ] Test presets still work with project instructions.
- [ ] Test empty instructions add no empty system message.
- [ ] Test streaming and non-streaming context use the same project instructions.

### Phase gate

- [ ] Project instructions are owner-scoped and consistent across chat modes.
- [ ] Existing preset behavior remains intact.

## Phase 4: Project Files and Scoped Retrieval

### File extraction and indexing

- [ ] Reuse existing upload resolution and document extraction code.
- [ ] Reuse existing chunking and embedding lanes.
- [ ] Avoid a second upload directory or upload metadata store.
- [ ] Index project chunks with `owner`, `scope`, `project_id`, `upload_id`, and filename metadata.
- [ ] Set `scope` to `project` for project chunks.
- [ ] Include project ID and upload ID in generated chunk identity.
- [ ] Preserve legacy document IDs for existing non-project content.
- [ ] Run blocking extraction and indexing outside the async event loop.

### Retrieval isolation

- [ ] Extend RAG search with optional project scope.
- [ ] Project searches must filter by owner and exact project ID.
- [ ] Normal personal RAG must exclude chunks where `scope=project`.
- [ ] Treat legacy chunks without a scope as personal content.
- [ ] Apply the same filtering in vector and keyword fallback paths.
- [ ] Dedupe results without merging chunks from different projects.
- [ ] Return project file source metadata for the existing source UI.

### Context injection

- [ ] Retrieve no more than five relevant project chunks per turn.
- [ ] Apply the existing similarity threshold.
- [ ] Wrap retrieved file text with `untrusted_context_message()`.
- [ ] Cap total injected project file text using the existing context budget pattern.
- [ ] Keep normal memory behavior unchanged.
- [ ] If Chroma is unavailable, fall back to capped extraction from project files.
- [ ] A corrupt file must not fail the whole chat.

### File removal and project deletion

- [ ] Add scoped RAG deletion by owner, project ID, and optional upload ID.
- [ ] Remove only the selected project's chunks.
- [ ] Removing one project file must not remove an identical file from another project.
- [ ] Deleting a project must remove all its chunks.
- [ ] Keep uploaded bytes until reference-aware cleanup decides they are unreferenced.

### Verification

- [ ] Test same-project retrieval.
- [ ] Test cross-project retrieval denial.
- [ ] Test cross-owner retrieval denial.
- [ ] Test ordinary personal RAG excludes project chunks.
- [ ] Test vector and keyword fallback isolation.
- [ ] Test identical text in two projects remains independently indexed.
- [ ] Test file removal deletes only matching chunks.
- [ ] Test degraded behavior without Chroma.

### Phase gate

- [ ] Relevant project files work across separate chats in the same project.
- [ ] No project chunk appears in another project or ordinary chat.
- [ ] File lifecycle and upload cleanup remain coherent.

## Phase 5: Projects UI

### Module and navigation

- [ ] Add `static/js/projects.js`.
- [ ] Import and initialize it from `static/app.js`.
- [ ] Add a Projects section to the existing sidebar in `static/index.html`.
- [ ] Match existing sidebar, modal, menu, button, focus, and toast patterns.
- [ ] Do not redesign the sidebar or introduce a new component system.

### Project operations

- [ ] Add create project action.
- [ ] Add rename project action.
- [ ] Add edit instructions action.
- [ ] Add delete project confirmation explaining that chats will be detached.
- [ ] Add project detail view with instructions, files, and chats.
- [ ] Add project file upload through existing `/api/upload`.
- [ ] Add project file removal.
- [ ] Add New Chat inside project.
- [ ] Add Move to project in the existing session menu.
- [ ] Add Remove from project in the existing session menu.
- [ ] Show current project identity in the chat header without adding decorative UI.

### Required states

- [ ] Add empty project state.
- [ ] Add empty file state.
- [ ] Add loading state.
- [ ] Add upload and API error states.
- [ ] Disable repeated actions while requests are pending.
- [ ] Preserve keyboard navigation and visible focus.
- [ ] Verify mobile sidebar and modal layout.
- [ ] Escape all project names, filenames, and server-provided text before rendering.

### Verification

- [ ] Run `rtk node --check static/js/projects.js`.
- [ ] Run syntax checks for every changed JavaScript file.
- [ ] Add focused JavaScript tests where current test helpers support the touched behavior.
- [ ] Manually create, rename, edit, and delete a project.
- [ ] Manually upload and remove a project file.
- [ ] Manually move a chat into and out of a project.
- [ ] Verify desktop and mobile layouts.

### Phase gate

- [ ] Every visible control works.
- [ ] Empty, loading, success, and error states are usable.
- [ ] Existing chats and folders remain usable.

## Phase 6: Native systemd User Service Foundation

### Service installation

- [ ] Add a native user-service installer instead of modifying Docker flows.
- [ ] Install user units under `~/.config/systemd/user/`.
- [ ] Generate absolute repository and venv paths during installation.
- [ ] Keep the existing native service name stable where practical.
- [ ] Document `sudo loginctl enable-linger <user>` as a host setup step.
- [ ] Run the app as a dedicated unprivileged Linux user.
- [ ] Bind the app to `127.0.0.1` by default.
- [ ] Keep secrets in the existing environment file, not in unit files.

### Update unit

- [ ] Add `systemd/odysseus-update.service` or the repository-equivalent user unit template.
- [ ] Set the update unit to `Type=oneshot`.
- [ ] Prevent concurrent runs with both systemd state and `flock`.
- [ ] Give the update service only the privileges of the dedicated user.
- [ ] Do not add sudo or root execution to the web application.

### Verification

- [ ] Verify generated units with `rtk systemd-analyze --user verify`.
- [ ] Confirm service startup after logout when lingering is enabled.
- [ ] Confirm app restart through `systemctl --user restart`.

### Phase gate

- [ ] Odysseus runs from the project venv as a user service.
- [ ] No Docker or root dependency was introduced.

## Phase 7: Native Self-Update Backend

### Update script

- [ ] Add `scripts/update_odysseus`.
- [ ] Use POSIX-safe shell behavior compatible with the VM target.
- [ ] Resolve and validate the exact repository root before any mutation.
- [ ] Acquire a file lock before checking or updating.
- [ ] Require the configured branch, default `main`.
- [ ] Reject any dirty tracked or untracked worktree state.
- [ ] Fetch only the configured remote and branch.
- [ ] Reject non-fast-forward history.
- [ ] Record the old and target commit hashes.
- [ ] Run the existing local backup command before merging.
- [ ] Update code with fast-forward-only semantics.
- [ ] Install requirements into the existing project venv.
- [ ] Run existing idempotent setup required by native installs.
- [ ] Restart Odysseus only after all preparation succeeds.
- [ ] Write update status atomically to `data/update-status.json`.
- [ ] Redact credentials, remote URLs with secrets, and environment values from status output.
- [ ] Return success without restarting when no update exists.

### Backend routes

- [ ] Add a small dedicated update router or place endpoints in the existing admin-owned system route.
- [ ] Implement `GET /api/admin/update/status`.
- [ ] Implement `POST /api/admin/update`.
- [ ] Require admin authentication for both endpoints.
- [ ] Return 404 or disabled state unless `ODYSSEUS_SELF_UPDATE=true`.
- [ ] Start only the fixed `odysseus-update.service` command.
- [ ] Use argument arrays with no shell interpolation.
- [ ] Use `systemctl --user start --no-block odysseus-update.service`.
- [ ] Reject a second request while an update is active.

### Failure behavior

- [ ] A fetch failure leaves the running process untouched.
- [ ] A dirty worktree leaves the running process untouched.
- [ ] A backup failure leaves the running process untouched.
- [ ] A dependency or setup failure does not restart the app.
- [ ] Every failure writes a concise status message and timestamp.
- [ ] Do not implement automatic Git rollback in MVP.

### Verification

- [ ] Run `rtk bash -n scripts/update_odysseus`.
- [ ] Test disabled update endpoints.
- [ ] Test non-admin denial.
- [ ] Test clean no-update result.
- [ ] Test dirty worktree rejection in an isolated temporary repository.
- [ ] Test non-fast-forward rejection in an isolated temporary repository.
- [ ] Test concurrent request rejection.
- [ ] Test status file redaction and atomic replacement.
- [ ] Test the update flow against a disposable native VM or equivalent environment.

### Phase gate

- [ ] Update cannot execute arbitrary browser-supplied input.
- [ ] Failed preparation never restarts the running service.
- [ ] Successful update restarts into the target commit.

## Phase 8: Updater UI and Deployment Documentation

### Settings UI

- [ ] Add a Native Update card under Settings > System.
- [ ] Show the card only to admins.
- [ ] Show disabled configuration clearly when self-update is off.
- [ ] Show current commit when available.
- [ ] Add an `Update & restart` button.
- [ ] Require confirmation before triggering an update.
- [ ] Poll update status while an update is active.
- [ ] Show updating, success, no-update, rejected, and failed states.
- [ ] Disable the button while an update is active.
- [ ] Do not display raw command output or environment values.

### Documentation

- [ ] Document native venv installation in `website/setup.md` if current instructions are insufficient.
- [ ] Document systemd user service installation.
- [ ] Document lingering, localhost binding, reverse proxy, and HTTPS expectations.
- [ ] Document `AUTH_ENABLED=true` and `LOCALHOST_BYPASS=false` for VM deployment.
- [ ] Document explicit self-update opt-in.
- [ ] Document dirty-worktree and fast-forward requirements.
- [ ] Document manual recovery after an update failure.

### Verification

- [ ] Run syntax checks for changed Settings JavaScript.
- [ ] Verify admin visibility.
- [ ] Verify non-admin invisibility and backend denial.
- [ ] Verify page reload during update recovers status from disk.
- [ ] Verify UI remains understandable after the app restarts.

### Phase gate

- [ ] Admin can trigger and observe a native update without terminal access.
- [ ] Non-admin users cannot discover or trigger update operations.

## Phase 9: End-to-End Verification and Stop

### Automated checks

- [ ] Run all focused project tests.
- [ ] Run all focused upload cleanup and ownership tests.
- [ ] Run all focused RAG tests.
- [ ] Run all focused session tests.
- [ ] Run all focused updater tests.
- [ ] Run Python compile checks for changed modules.
- [ ] Run JavaScript syntax checks for changed modules.
- [ ] Run shell syntax checks for changed scripts.
- [ ] Run systemd unit verification.
- [ ] Run the broader relevant test lane defined by repository guidance.

### Manual project smoke test

- [ ] Create Project A as User A.
- [ ] Add project instructions.
- [ ] Upload a supported document.
- [ ] Create two chats inside Project A.
- [ ] Confirm both chats can answer from the uploaded document.
- [ ] Confirm project instructions affect both chats.
- [ ] Create Project B and confirm it cannot retrieve Project A files.
- [ ] Create User B and confirm it cannot access Project A.
- [ ] Move an existing chat into Project A.
- [ ] Remove the chat from Project A without losing its messages.
- [ ] Delete Project A and confirm its chats survive detached.
- [ ] Run upload cleanup and confirm referenced files survive until references are removed.

### Manual updater smoke test

- [ ] Install Odysseus under a dedicated VM user.
- [ ] Start it through the systemd user service.
- [ ] Confirm it survives logout with lingering enabled.
- [ ] Confirm update is unavailable while disabled.
- [ ] Enable self-update and trigger a no-update run.
- [ ] Trigger an update against a newer fast-forward commit.
- [ ] Confirm backup creation.
- [ ] Confirm dependencies and setup complete.
- [ ] Confirm the service restarts on the target commit.
- [ ] Confirm dirty worktree rejection.

### Final review

- [ ] Review the complete diff for unrelated edits.
- [ ] Confirm no secrets, logs, backups, or runtime data are tracked.
- [ ] Confirm no new dependency was added without necessity.
- [ ] Confirm project and updater security tests cover trust boundaries.
- [ ] Update completed checkboxes in this file.
- [ ] Add final verification commands and results to the Execution Log.

### Stop condition

- [ ] Every Definition of Done item passes.
- [ ] All phase gates pass.
- [ ] Remaining non-goals stay unimplemented.
- [ ] Stop work. Do not add sharing, project memory, connectors, styling extras, or rollback automation.

## Execution Log

Add one entry after each executor run.

```text
Date:
Executor:
Phase:
Changed files:
Checks run:
Result:
Blockers:
Next phase:
```

Date: 2026-09-22
Executor: Codex
Phase: 0 - Baseline and Flow Confirmation
Changed files: PROJECTS_IMPLEMENTATION_PLAN.md (Phase 0 checklist and execution log only)
Checks run:
- `rtk git status --short` - only existing untracked `PROJECTS_IMPLEMENTATION_PLAN.md`
- Reviewed session: `routes/session_routes.py`, `core/session_manager.py`, `core/models.py`
- Reviewed prompt: `routes/chat_helpers.py`, `src/chat_processor.py`
- Reviewed upload: `routes/upload_routes.py`, `src/upload_handler.py`
- Reviewed RAG: `src/rag_vector.py`, `src/rag_manager.py`
- Reviewed Settings: `static/index.html`, `static/js/admin.js`, `static/js/settings/registry.js`
- Selected baseline: `tests/test_session_manager.py`, `tests/test_session_list_owner_scope.py`, `tests/test_upload_routes_owner_scope.py`, `tests/test_upload_handler_cleanup.py`, `tests/test_rag_keyword_fallback_owner.py`, `tests/test_auth_policy.py`, `tests/test_settings_store_shape.py`
- `rtk ./venv/bin/python -m pytest -q ...` - failed: `./venv/bin/python` is absent
- `rtk python -m pytest --version` - failed: `No module named pytest`
- `rtk git diff --check` - passed
Result: Phase 0 flow confirmation complete. Baseline tests did not run; phase gate remains open.
Blockers: Project virtual environment is absent and system Python has no pytest.
Next phase: Create or restore the project virtual environment, install `requirements.txt`, rerun the selected baseline tests, then complete Phase 0 gate.

Date: 2026-09-22
Executor: Codex
Phase: 0 - Baseline and Flow Confirmation
Changed files: PROJECTS_IMPLEMENTATION_PLAN.md (Phase 0 checklist, virtual-environment rule, and execution log only)
Checks run:
- `rtk python -m venv venv` - passed
- `rtk venv/bin/python -m pip install -r requirements.txt` - passed
- `rtk zsh -lc 'source venv/bin/activate; python -m pytest -q tests/test_session_manager.py tests/test_session_list_owner_scope.py tests/test_upload_routes_owner_scope.py tests/test_upload_handler_cleanup.py tests/test_rag_keyword_fallback_owner.py tests/test_auth_policy.py tests/test_settings_store_shape.py'` - passed: 63 passed, 1 existing SQLAlchemy deprecation warning
Result: Phase 0 gate passed. Existing baseline command failure was environment-only and resolved before the successful test run.
Blockers: None.
Next phase: Phase 1 - Database and Session Model, only when requested.

Date: 2026-09-22
Executor: Codex
Phase: 1 - Database and Session Model
Changed files: core/database.py, core/models.py, core/session_manager.py, tests/test_project_database.py, PROJECTS_IMPLEMENTATION_PLAN.md
Checks run:
- `rtk zsh -lc 'source venv/bin/activate; python -m pytest -q tests/test_project_database.py tests/test_session_manager.py tests/test_session_manager_persist_guard.py tests/test_session_routes_utcnow.py'` - passed: 18 passed
- `rtk zsh -lc 'source venv/bin/activate; python -m py_compile core/database.py core/models.py core/session_manager.py tests/test_project_database.py'` - passed
- `rtk git diff --check` - passed
Result: Phase 1 gate passed. Fresh schemas create project tables. Legacy session databases gain nullable `project_id` and index without rewriting rows.
Blockers: None.
Next phase: Phase 2 - Owner-Scoped Project API, only when requested.

Date: 2026-09-22
Executor: Codex
Phase: 2 - Owner-Scoped Project API
Changed files: app.py, routes/project_routes.py, routes/session_routes.py, routes/upload_routes.py, src/request_models.py, tests/test_project_routes.py, PROJECTS_IMPLEMENTATION_PLAN.md
Checks run:
- `rtk zsh -lc 'source venv/bin/activate; python -m pytest -q tests/test_project_database.py tests/test_project_routes.py tests/test_session_manager.py tests/test_session_list_owner_scope.py tests/test_session_owner_attribution.py tests/test_upload_handler_cleanup.py tests/test_upload_routes_owner_scope.py tests/test_app.py'` - passed: 69 passed
- `rtk zsh -lc 'source venv/bin/activate; python -m py_compile app.py routes/project_routes.py routes/session_routes.py routes/upload_routes.py src/request_models.py tests/test_project_routes.py'` - passed
- `rtk git diff --check` - passed
Result: Phase 2 gate passed. Project files reserve uploads and survive cleanup; project deletion detaches chats and preserves messages and upload bytes.
Blockers: Project RAG chunk lifecycle is deferred until Phase 4 provides it.
Next phase: Phase 3 - Project Instructions in Chat Context, only when requested.
