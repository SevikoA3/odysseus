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

- [x] Load the project using both `session.project_id` and effective owner.
- [x] Treat missing, deleted, or inaccessible projects as a closed failure, not shared context.
- [x] Pass project instructions through the shared chat context path.
- [x] Cover both synchronous and streaming chat through the shared helper.
- [x] Cover agent mode through the same context construction path.

### Prompt ordering

- [x] Keep the selected preset system prompt first.
- [x] Add project instructions after the preset.
- [x] Keep `UNTRUSTED_CONTEXT_POLICY` active.
- [x] Keep project instructions stable across turns for prompt-cache reuse.
- [x] Do not copy project instructions into persisted user messages.
- [x] Do not place project file contents in a system message.

### Verification

- [x] Test instructions appear in every chat inside the project.
- [x] Test instructions do not appear outside the project.
- [x] Test one user's project instructions cannot enter another user's chat.
- [x] Test presets still work with project instructions.
- [x] Test empty instructions add no empty system message.
- [x] Test streaming and non-streaming context use the same project instructions.

### Phase gate

- [x] Project instructions are owner-scoped and consistent across chat modes.
- [x] Existing preset behavior remains intact.

## Phase 4: Project Files and Scoped Retrieval

### File extraction and indexing

- [x] Reuse existing upload resolution and document extraction code.
- [x] Reuse existing chunking and embedding lanes.
- [x] Avoid a second upload directory or upload metadata store.
- [x] Index project chunks with `owner`, `scope`, `project_id`, `upload_id`, and filename metadata.
- [x] Set `scope` to `project` for project chunks.
- [x] Include project ID and upload ID in generated chunk identity.
- [x] Preserve legacy document IDs for existing non-project content.
- [x] Run blocking extraction and indexing outside the async event loop.

### Retrieval isolation

- [x] Extend RAG search with optional project scope.
- [x] Project searches must filter by owner and exact project ID.
- [x] Normal personal RAG must exclude chunks where `scope=project`.
- [x] Treat legacy chunks without a scope as personal content.
- [x] Apply the same filtering in vector and keyword fallback paths.
- [x] Dedupe results without merging chunks from different projects.
- [x] Return project file source metadata for the existing source UI.

### Context injection

- [x] Retrieve no more than five relevant project chunks per turn.
- [x] Apply the existing similarity threshold.
- [x] Wrap retrieved file text with `untrusted_context_message()`.
- [x] Cap total injected project file text using the existing context budget pattern.
- [x] Keep normal memory behavior unchanged.
- [x] If Chroma is unavailable, fall back to capped extraction from project files.
- [x] A corrupt file must not fail the whole chat.

### File removal and project deletion

- [x] Add scoped RAG deletion by owner, project ID, and optional upload ID.
- [x] Remove only the selected project's chunks.
- [x] Removing one project file must not remove an identical file from another project.
- [x] Deleting a project must remove all its chunks.
- [x] Keep uploaded bytes until reference-aware cleanup decides they are unreferenced.

### Verification

- [x] Test same-project retrieval.
- [x] Test cross-project retrieval denial.
- [x] Test cross-owner retrieval denial.
- [x] Test ordinary personal RAG excludes project chunks.
- [x] Test vector and keyword fallback isolation.
- [x] Test identical text in two projects remains independently indexed.
- [x] Test file removal deletes only matching chunks.
- [x] Test degraded behavior without Chroma.

### Phase gate

- [x] Relevant project files work across separate chats in the same project.
- [x] No project chunk appears in another project or ordinary chat.
- [x] File lifecycle and upload cleanup remain coherent.

## Phase 5: Projects UI

### Module and navigation

- [x] Add `static/js/projects.js`.
- [x] Import and initialize it from `static/app.js`.
- [x] Add a Projects section to the existing sidebar in `static/index.html`.
- [x] Match existing sidebar, modal, menu, button, focus, and toast patterns.
- [x] Do not redesign the sidebar or introduce a new component system.

### Project operations

- [x] Add create project action.
- [x] Add rename project action.
- [x] Add edit instructions action.
- [x] Add delete project confirmation explaining that chats will be detached.
- [x] Add project detail view with instructions, files, and chats.
- [x] Add project file upload through existing `/api/upload`.
- [x] Add project file removal.
- [x] Add New Chat inside project.
- [x] Add Move to project in the existing session menu.
- [x] Add Remove from project in the existing session menu.
- [x] Show current project identity in the chat header without adding decorative UI.

### Required states

- [x] Add empty project state.
- [x] Add empty file state.
- [x] Add loading state.
- [x] Add upload and API error states.
- [x] Disable repeated actions while requests are pending.
- [x] Preserve keyboard navigation and visible focus.
- [x] Verify mobile sidebar and modal layout.
- [x] Escape all project names, filenames, and server-provided text before rendering.

### Verification

- [x] Run `rtk node --check static/js/projects.js`.
- [x] Run syntax checks for every changed JavaScript file.
- [x] Add focused JavaScript tests where current test helpers support the touched behavior. No current generic DOM helper covers this module.
- [x] Manually create, rename, edit, and delete a project.
- [x] Manually create a chat inside a project.
- [x] Manually upload and remove a project file.
- [x] Manually move a chat into and out of a project.
- [x] Verify desktop and mobile layouts.

### Phase gate

- [x] Every visible control works.
- [x] Empty, loading, success, and error states are usable.
- [x] Existing chats and folders remain usable.

## Phase 6: Native systemd User Service Foundation

### Service installation

- [x] Add a native user-service installer instead of modifying Docker flows.
- [x] Install user units under `~/.config/systemd/user/`.
- [x] Generate absolute repository and venv paths during installation.
- [x] Keep the existing native service name stable where practical.
- [x] Document `sudo loginctl enable-linger <user>` as a host setup step.
- [x] Run the app as a dedicated unprivileged Linux user.
- [x] Bind the app to `127.0.0.1` by default.
- [x] Keep secrets in the existing environment file, not in unit files.

### Update unit

- [x] Add `systemd/odysseus-update.service` or the repository-equivalent user unit template.
- [x] Set the update unit to `Type=oneshot`.
- [x] Prevent concurrent runs with both systemd state and `flock`.
- [x] Give the update service only the privileges of the dedicated user.
- [x] Do not add sudo or root execution to the web application.

### Verification

- [x] Verify generated units with `rtk systemd-analyze --user verify`.
- [x] Confirm service startup after logout when lingering is enabled.
- [x] Confirm app restart through `systemctl --user restart`.

### Phase gate

- [x] Odysseus runs from the project venv as a user service.
- [x] No Docker or root dependency was introduced.

## Phase 7: Native Self-Update Backend

### Update script

- [x] Add `scripts/update_odysseus`.
- [x] Use POSIX-safe shell behavior compatible with the VM target.
- [x] Resolve and validate the exact repository root before any mutation.
- [x] Acquire a file lock before checking or updating.
- [x] Require the configured branch, default `main`.
- [x] Reject any dirty tracked or untracked worktree state.
- [x] Fetch only the configured remote and branch.
- [x] Reject non-fast-forward history.
- [x] Record the old and target commit hashes.
- [x] Run the existing local backup command before merging.
- [x] Update code with fast-forward-only semantics.
- [x] Install requirements into the existing project venv.
- [x] Run existing idempotent setup required by native installs.
- [x] Restart Odysseus only after all preparation succeeds.
- [x] Write update status atomically to `data/update-status.json`.
- [x] Redact credentials, remote URLs with secrets, and environment values from status output.
- [x] Return success without restarting when no update exists.

### Backend routes

- [x] Add a small dedicated update router or place endpoints in the existing admin-owned system route.
- [x] Implement `GET /api/admin/update/status`.
- [x] Implement `POST /api/admin/update`.
- [x] Require admin authentication for both endpoints.
- [x] Return 404 or disabled state unless `ODYSSEUS_SELF_UPDATE=true`.
- [x] Start only the fixed `odysseus-update.service` command.
- [x] Use argument arrays with no shell interpolation.
- [x] Use `systemctl --user start --no-block odysseus-update.service`.
- [x] Reject a second request while an update is active.

### Failure behavior

- [x] A fetch failure leaves the running process untouched.
- [x] A dirty worktree leaves the running process untouched.
- [x] A backup failure leaves the running process untouched.
- [x] A dependency or setup failure does not restart the app.
- [x] Every failure writes a concise status message and timestamp.
- [x] Do not implement automatic Git rollback in MVP.

### Verification

- [x] Run `rtk bash -n scripts/update_odysseus`.
- [x] Test disabled update endpoints.
- [x] Test non-admin denial.
- [x] Test clean no-update result.
- [x] Test dirty worktree rejection in an isolated temporary repository.
- [x] Test non-fast-forward rejection in an isolated temporary repository.
- [x] Test concurrent request rejection.
- [x] Test status file redaction and atomic replacement.
- [x] Test the update flow against a disposable native VM or equivalent environment.

### Phase gate

- [x] Update cannot execute arbitrary browser-supplied input.
- [x] Failed preparation never restarts the running service.
- [x] Successful update restarts into the target commit.

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

Date: 2026-09-22
Executor: Codex
Phase: 3 - Project Instructions in Chat Context
Changed files: routes/chat_helpers.py, src/chat_processor.py, tests/test_chat_helpers.py, tests/test_chat_processor_pinned_memory.py, PROJECTS_IMPLEMENTATION_PLAN.md
Checks run:
- `rtk venv/bin/python -m pytest -q tests/test_chat_helpers.py tests/test_chat_processor_pinned_memory.py tests/test_kv_cache_invalidation_2927.py tests/test_user_time.py` - passed: 63 passed
- `rtk venv/bin/python -m pytest -q tests/test_chat_helpers.py tests/test_chat_processor_pinned_memory.py tests/test_kv_cache_invalidation_2927.py tests/test_user_time.py tests/test_chat_stream_scope.py tests/test_api_chat_security.py tests/test_chat_route_tool_policy.py tests/test_chat_processor_web_search.py` - passed: 115 passed
- `rtk venv/bin/python -m py_compile routes/chat_helpers.py src/chat_processor.py tests/test_chat_helpers.py tests/test_chat_processor_pinned_memory.py` - passed
- `rtk git diff --check` and `rtk git diff --cached --check` - passed
Result: Phase 3 gate passed. Project instructions are loaded by exact owner, placed after the selected preset and before the untrusted-context policy, and shared by sync, streaming, and agent context construction.
Blockers: None.
Next phase: Phase 4 - Project Files and Scoped Retrieval, only when requested.

Date: 2026-09-22
Executor: Codex
Phase: 4 - Project Files and Scoped Retrieval
Changed files: app.py, routes/project_routes.py, routes/chat_helpers.py, src/chat_processor.py, src/personal_docs.py, src/rag_manager.py, src/rag_vector.py, tests/helpers/embedding_lanes.py, tests/test_project_routes.py, tests/test_project_rag.py, PROJECTS_IMPLEMENTATION_PLAN.md
Checks run:
- `rtk venv/bin/python -m pytest -q tests/test_project_database.py tests/test_project_routes.py tests/test_project_rag.py tests/test_rag_search_signature.py tests/test_rag_keyword_fallback_owner.py tests/test_rag_vector_id_stability.py tests/test_rag_manager_owner_compat.py tests/test_rag_remove_directory_scope.py tests/test_rag_vector_rename_owner.py tests/test_embedding_lanes_rag.py tests/test_upload_handler_cleanup.py tests/test_upload_routes_owner_scope.py tests/test_chat_helpers.py tests/test_chat_processor_pinned_memory.py tests/test_kv_cache_invalidation_2927.py tests/test_user_time.py tests/test_chat_stream_scope.py tests/test_app.py` - passed: 133 passed
- `rtk venv/bin/python -m py_compile app.py routes/project_routes.py routes/chat_helpers.py src/chat_processor.py src/personal_docs.py src/rag_vector.py src/rag_manager.py tests/test_project_rag.py tests/test_project_routes.py tests/helpers/embedding_lanes.py` - passed
- `rtk git diff --check` and `rtk git diff --cached --check` - passed
Result: Phase 4 gate passed. Project chunks are owner/project/upload scoped in vector and keyword retrieval, stale chunks are excluded by current project file links, and unavailable RAG falls back to capped untrusted extraction.
Blockers: None.
Next phase: Phase 5 - Projects UI, only when requested.

Date: 2026-09-22
Executor: Codex
Phase: 5 - Projects UI
Changed files: static/js/projects.js, static/js/sessions.js, static/app.js, static/index.html, static/style.css, PROJECTS_IMPLEMENTATION_PLAN.md
Checks run:
- `rtk venv/bin/python -m pytest -q tests/test_project_database.py tests/test_project_routes.py tests/test_project_rag.py tests/test_chat_helpers.py tests/test_chat_processor_pinned_memory.py tests/test_app.py` - passed: 69 passed
- `rtk node --check static/js/projects.js`, `rtk node --check static/js/sessions.js`, and `rtk node --check static/app.js` - passed
- `rtk git diff --check` and `rtk git diff --cached --check` - passed
- Local server check: `/` redirected to setup and `/static/js/projects.js`, `/static/app.js` returned 200
Result: Project UI is implemented with owner-scoped CRUD, details, file attach/removal, project chats, session move/removal, loading/error/empty states, and header identity.
Blockers: Browser automation is unavailable on this host, so the four manual UI/layout verification items and Phase 5 gate remain open.
Next phase: Finish Phase 5 browser verification when a browser is available; do not start Phase 6 yet.

Date: 2026-09-22
Executor: Codex
Phase: 5 - Projects UI polish
Changed files: static/js/projects.js, static/style.css, PROJECTS_IMPLEMENTATION_PLAN.md
Checks run:
- `rtk node --check static/js/projects.js` - passed
- `rtk venv/bin/python -m pytest -q tests/test_project_database.py tests/test_project_routes.py tests/test_project_rag.py tests/test_chat_helpers.py tests/test_chat_processor_pinned_memory.py tests/test_app.py` - passed: 69 passed
- `rtk git diff --check` and `rtk git diff --cached --check` - passed
Result: The project modal now uses the existing styled controls, replaces the native file field with an accessible file-count control, and reflows its controls into touch-sized mobile rows.
Blockers: Manual browser verification remains outstanding because computer use is excluded by user instruction.
Next phase: User can manually verify create, update, upload, move, and delete flows, then close Phase 5. Do not start Phase 6.

Date: 2026-09-22
Executor: Codex
Phase: 6 - Native systemd User Service Foundation
Changed files: install-service.sh, systemd/odysseus-ui.service.in, systemd/odysseus-update.service.in, website/setup.md, PROJECTS_IMPLEMENTATION_PLAN.md
Checks run:
- `rtk bash -n install-service.sh` - passed
- Isolated installer smoke test with a fake `systemctl`; both generated units passed `rtk systemd-analyze --user verify` - passed
- `rtk git diff --check` - passed
Result: The installer renders user-owned units with absolute paths, enables `odysseus-ui.service`, and leaves the Phase 7 updater unavailable until its script exists. The app binds to loopback and reads the existing `.env` file.
Blockers: Startup after logout and restart need a real dedicated-user host with lingering enabled.
Next phase: Complete the two native-host checks, then start Phase 7 only when requested.

Date: 2026-09-22
Executor: Codex
Phase: 5 - Project chat correction
Changed files: static/js/sessions.js, PROJECTS_IMPLEMENTATION_PLAN.md
Checks run:
- `rtk node --check static/js/sessions.js` - passed
- Default session-module export check for `createProjectChat` - passed
- `rtk git diff --check` - passed
Result: `createProjectChat()` is now exposed through the default session module used by the Projects modal.
Blockers: The New chat button needs a browser retry before the visible-control gate can pass again.
Next phase: Close the project-chat verification, then finish Phase 6 runtime checks.

Date: 2026-09-22
Executor: Codex
Phase: 6 - Native systemd runtime test
Checks run:
- `./install-service.sh` installed and started `odysseus-ui.service` - passed
- `rtk systemd-analyze --user verify` on installed units - passed
- Loopback request to `http://127.0.0.1:7000/` - passed: HTTP 302
- `systemctl --user restart odysseus-ui.service` - passed
- Journal check - passed: 37 lines
- Cleanup restored the prior state: service not found/inactive, unit files and enable symlink removed - passed
Result: The user service runs from the project venv and restarts correctly. User lingering is already enabled.
Blockers: A real logout test remains intentionally unrun because it would end the active desktop session.
Next phase: Complete the logout check, then start Phase 7 only when requested.

Date: 2026-09-22
Executor: Codex
Phase: 5 - Project context correction
Changed files: routes/chat_helpers.py, tests/test_project_rag.py, PROJECTS_IMPLEMENTATION_PLAN.md
Checks run:
- `rtk venv/bin/python -m pytest -q tests/test_project_rag.py tests/test_chat_helpers.py` - passed: 43 passed
- `rtk venv/bin/python -m py_compile routes/chat_helpers.py tests/test_project_rag.py` - passed
- `rtk git diff --check` - passed
Result: Repaired the existing project chat membership. When vector RAG is unavailable, fallback project retrieval now ranks chunks by the current request instead of taking only the first file's chunks.
Blockers: User browser retry still needed for the Phase 5 New chat visible-control check.
Next phase: Close New chat verification, then finish Phase 6 logout verification.

Date: 2026-09-22
Executor: Codex
Phase: 5 - Projects UI complete
Checks run:
- `rtk node --check static/js/projects.js` and `rtk node --check static/js/sessions.js` - passed
- `rtk venv/bin/python -m pytest -q tests/test_project_routes.py tests/test_project_rag.py tests/test_chat_helpers.py` - passed: 49 passed
Result: New project chats are exported through the session module, persisted with the project ID, and retrieve the matching project file fallback. All Phase 5 checklist items and gates pass.
Blockers: None.
Next phase: Finish the remaining Phase 6 logout verification, then start Phase 7 only when requested.

Date: 2026-09-22
Executor: Codex
Phase: 5 - Projects UI complete
Changed files: static/js/projects.js, static/style.css, PROJECTS_IMPLEMENTATION_PLAN.md
Checks run:
- `rtk node --check static/js/projects.js` - passed
- `rtk venv/bin/python -m pytest -q tests/test_project_routes.py tests/test_project_rag.py` - passed: 10 passed
- `rtk git diff --check` and `rtk git diff --cached --check` - passed
- User manual verification: project CRUD, file lifecycle, chat moves, desktop and mobile layouts.
Result: Files have a clickable drag/drop zone. Phase 5 checklist and gate pass.
Blockers: None.
Next phase: Phase 6 - Native systemd User Service Foundation, only when requested.

Date: 2026-09-22
Executor: Codex
Phase: 5 - Projects UI simplification
Changed files: static/js/projects.js, static/style.css, PROJECTS_IMPLEMENTATION_PLAN.md
Checks run:
- `rtk node --check static/js/projects.js` - passed
- `rtk venv/bin/python -m pytest -q tests/test_project_routes.py tests/test_project_rag.py` - passed: 10 passed
- `rtk git diff --check` and `rtk git diff --cached --check` - passed
Result: File selection and upload now use one `Add files` action. Choosing files starts their upload immediately.
Blockers: Manual browser verification remains outstanding because computer use is excluded by user instruction.
Next phase: User can manually verify create, update, upload, move, and delete flows, then close Phase 5. Do not start Phase 6.

Date: 2026-09-22
Executor: Codex
Phase: 5 - Project file retrieval correction
Changed files: src/personal_docs.py, routes/chat_helpers.py, src/chat_processor.py, tests/test_chat_helpers.py, tests/test_project_rag.py, tests/test_split_chunks_no_duplicate_tail.py
Checks run:
- `rtk venv/bin/python -m py_compile src/personal_docs.py routes/chat_helpers.py src/chat_processor.py tests/test_project_rag.py tests/test_chat_helpers.py tests/test_split_chunks_no_duplicate_tail.py` - passed
- `rtk venv/bin/python -m pytest -q tests/test_project_routes.py tests/test_project_rag.py tests/test_chat_helpers.py tests/test_split_chunks_no_duplicate_tail.py tests/test_personal_docs_keyword_nondict.py` - passed: 60 passed
- `rtk git diff --check` and `rtk git diff --cached --check` - passed
Result: Project files are loaded for substantive project chats even when generic RAG is disabled. Semantic RAG is combined with heading-aware lexical retrieval, which preserves Markdown section context and ranks exact query phrases above generic document language.
Blockers: None.
Next phase: Phase 6 logout verification remains outstanding; start Phase 7 only when requested.

Date: 2026-09-22
Executor: Codex
Phase: 5 - Projects UI correction
Changed files: static/js/ui.js, static/js/projects.js, static/style.css, PROJECTS_IMPLEMENTATION_PLAN.md
Checks run:
- `rtk node --check static/js/ui.js` and `rtk node --check static/js/projects.js` - passed
- `rtk venv/bin/python -m pytest -q tests/test_project_routes.py tests/test_project_rag.py` - passed: 10 passed
- `rtk git diff --check` and `rtk git diff --cached --check` - passed
Result: Project sidebar names use the sidebar text scale. Empty project names stay in the creation dialog and receive native required-field feedback.
Blockers: Manual browser verification remains outstanding because computer use is excluded by user instruction.
Next phase: User can manually verify create, update, upload, move, and delete flows, then close Phase 5. Do not start Phase 6.

Date: 2026-09-23
Executor: Codex
Phase: 7 - Native Self-Update Backend
Changed files: app.py, install-service.sh, systemd/odysseus-update.service.in, scripts/update_odysseus, routes/update_routes.py, tests/test_update_flow.py, PROJECTS_IMPLEMENTATION_PLAN.md
Checks run:
- `rtk venv/bin/python -m pytest -q tests/test_update_flow.py tests/test_app.py` - passed: 39 passed
- `rtk venv/bin/python -m py_compile routes/update_routes.py tests/test_update_flow.py app.py` - passed
- `rtk bash -n scripts/update_odysseus install-service.sh` and `rtk sh -n scripts/update_odysseus` - passed
- `rtk systemd-analyze --user verify` on generated user units - passed
- `rtk git diff --check` - passed
Result: Opt-in, admin-only native updates now reject dirty trees, branch mismatch, non-fast-forward history, and concurrent runs. Disposable Git repositories exercise the real installer and simulated service restart at the target commit. Preparation failures never restart the app.
Blockers: None for Phase 7. A live VM update was not run; the disposable native-install harness is the equivalent verification environment.
Next phase: Phase 8 - Updater UI and Deployment Documentation, only when requested.
