import uiModule from './ui.js';
import { makeWindowDraggable } from './windowDrag.js';

const API = `${window.location.origin}/api`;
let sessionModule = null;
let projects = [];
let activeProjectId = null;
let modal = null;
let instructionsDrafts = {};

function detail(error, fallback) {
  return error?.message || fallback;
}

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, { credentials: 'same-origin', ...options });
  let data = null;
  try { data = await response.json(); } catch (_) {}
  if (!response.ok) throw new Error(data?.detail || data?.error || `Request failed (${response.status})`);
  return data;
}

function button(label, className = '') {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = className;
  el.textContent = label;
  return el;
}

function setPending(controls, pending) {
  controls.forEach(control => { if (control) control.disabled = pending; });
}

function projectName(projectId) {
  return projects.find(project => project.id === projectId)?.name || '';
}

function renderSidebar(state = '') {
  const list = document.getElementById('project-list');
  if (!list) return;
  list.textContent = '';
  if (state) {
    const status = document.createElement('div');
    status.className = 'project-sidebar-state';
    status.setAttribute('role', 'status');
    status.textContent = state;
    list.appendChild(status);
    if (state === 'Unable to load projects') {
      const retry = button('Retry', 'project-row-action');
      retry.addEventListener('click', loadProjects);
      list.appendChild(retry);
    }
    return;
  }
  if (!projects.length) {
    const empty = document.createElement('div');
    empty.className = 'project-sidebar-state';
    empty.textContent = 'No projects yet';
    list.appendChild(empty);
    return;
  }
  projects.forEach(project => {
    const row = document.createElement('div');
    row.className = 'project-sidebar-row';
    const open = button(project.name || 'Untitled project', 'list-item project-list-item');
    open.title = project.name || 'Untitled project';
    open.dataset.projectId = project.id;
    open.addEventListener('click', () => openProject(project.id));
    const settings = button('Settings', 'project-settings-btn');
    settings.title = `Settings for ${project.name || 'project'}`;
    settings.setAttribute('aria-label', settings.title);
    settings.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-1.8 1.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5v.1h-2.6v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1-1.8-1.8.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H6.4v-2.6h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1 1.8-1.8.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.5v-.1H15v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1 1.8 1.8-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5 1h.1v2.6h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>';
    settings.addEventListener('click', () => openProjectSettings(project.id));
    row.append(open, settings);
    list.appendChild(row);
  });
}

async function loadProjects() {
  renderSidebar('Loading projects…');
  try {
    projects = await request('/projects');
    renderSidebar();
    syncSessionProject(sessionModule?.getPendingChat?.()?.projectId || sessionModule?.getSessions?.().find(session => session.id === sessionModule?.getCurrentSessionId?.())?.project_id);
    return projects;
  } catch (error) {
    renderSidebar('Unable to load projects');
    uiModule.showError(`Projects: ${detail(error, 'Unable to load')}`);
    return [];
  }
}

function closeModal() {
  if (!modal) return;
  modal.classList.add('hidden');
  modal.style.display = 'none';
  activeProjectId = null;
}

function ensureModal() {
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'projects-modal';
  modal.className = 'modal hidden';
  modal.innerHTML = '<div class="modal-content project-modal-content" role="dialog" aria-modal="true" aria-labelledby="projects-modal-title"><div class="modal-header"><h4 id="projects-modal-title">Project</h4><button type="button" class="close-btn" aria-label="Close project">✖</button></div><div class="modal-body project-modal-body"></div></div>';
  modal.querySelector('.close-btn').addEventListener('click', closeModal);
  modal.addEventListener('click', event => {
    if (event.target === modal && !uiModule.isTouchInsideModal()) closeModal();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && modal && !modal.classList.contains('hidden')) closeModal();
  });
  document.body.appendChild(modal);
  makeWindowDraggable(modal, {
    content: modal.querySelector('.modal-content'),
    header: modal.querySelector('.modal-header'),
    enableDock: false,
    enableResize: false,
  });
  return modal;
}

function showModal() {
  const el = ensureModal();
  el.classList.remove('hidden');
  el.style.display = '';
  return el.querySelector('.project-modal-body');
}

function showDetailState(message) {
  const body = showModal();
  body.textContent = '';
  const state = document.createElement('div');
  state.className = 'project-detail-state';
  state.setAttribute('role', 'status');
  state.textContent = message;
  body.appendChild(state);
}

function makeField(labelText, value, multiline = false) {
  const wrap = document.createElement('label');
  wrap.className = 'project-field';
  const label = document.createElement('span');
  label.textContent = labelText;
  const input = document.createElement(multiline ? 'textarea' : 'input');
  if (!multiline) input.type = 'text';
  input.value = value || '';
  input.maxLength = multiline ? 20000 : 100;
  if (multiline) input.rows = 5;
  wrap.append(label, input);
  return { wrap, input };
}

function renderSettings(data) {
  const body = showModal();
  const project = data.project;
  activeProjectId = project.id;
  document.getElementById('projects-modal-title').textContent = project.name || 'Project';
  body.textContent = '';

  const name = makeField('Name', project.name);
  const instructions = makeField('Instructions', instructionsDrafts[project.id] ?? project.instructions ?? '', true);
  instructions.input.placeholder = 'Instructions for chats in this project';
  instructions.input.addEventListener('input', () => { instructionsDrafts[project.id] = instructions.input.value; });
  const save = button('Save', 'confirm-btn confirm-btn-primary');
  const removeProject = button('Delete project', 'confirm-btn confirm-btn-danger');
  const settingsActions = document.createElement('div');
  settingsActions.className = 'modal-footer project-actions';
  settingsActions.append(save, removeProject);
  body.append(name.wrap, instructions.wrap, settingsActions);
  requestAnimationFrame(() => name.input.focus());

  save.addEventListener('click', async () => {
    setPending([save, removeProject], true);
    try {
      const updated = await request(`/projects/${encodeURIComponent(project.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.input.value, instructions: instructions.input.value }),
      });
      projects = projects.map(item => item.id === updated.id ? updated : item);
      delete instructionsDrafts[project.id];
      Object.assign(project, updated);
      name.input.value = project.name || '';
      instructions.input.value = project.instructions || '';
      document.getElementById('projects-modal-title').textContent = project.name || 'Project';
      renderSidebar();
      syncSessionProject(sessionModule?.getPendingChat?.()?.projectId || sessionModule?.getSessions?.().find(session => session.id === sessionModule?.getCurrentSessionId?.())?.project_id);
      uiModule.showToast('Project saved');
    } catch (error) {
      uiModule.showError(`Project: ${detail(error, 'Could not save')}`);
    } finally {
      setPending([save, removeProject], false);
    }
  });

  removeProject.addEventListener('click', async () => {
    if (!await uiModule.styledConfirm('Delete this project? Its chats will be detached.', { title: 'Delete project', confirmText: 'Delete', danger: true })) return;
    setPending([save, removeProject], true);
    try {
      await request(`/projects/${encodeURIComponent(project.id)}`, { method: 'DELETE' });
      projects = projects.filter(item => item.id !== project.id);
      const current = sessionModule?.getSessions?.().find(session => session.id === sessionModule?.getCurrentSessionId?.());
      if (current?.project_id === project.id) current.project_id = null;
      await sessionModule?.loadSessions?.();
      renderSidebar();
      syncSessionProject(current?.project_id);
      closeModal();
      uiModule.showToast('Project deleted');
    } catch (error) {
      uiModule.showError(`Project: ${detail(error, 'Could not delete')}`);
    } finally {
      setPending([save, removeProject], false);
    }
  });

  const filesTitle = document.createElement('h5');
  filesTitle.textContent = 'Files';
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.multiple = true;
  fileInput.hidden = true;
  fileInput.setAttribute('aria-label', 'Choose project files');
  const dropZone = button('Drop files here or click to upload', 'project-drop-zone');
  const uploadStatus = document.createElement('div');
  uploadStatus.className = 'project-upload-status';
  uploadStatus.setAttribute('role', 'status');
  body.append(filesTitle, fileInput, dropZone, uploadStatus);

  const files = document.createElement('div');
  files.className = 'project-file-list';
  if (!data.files.length) {
    const empty = document.createElement('div');
    empty.className = 'project-detail-state';
    empty.textContent = 'No files attached';
    files.appendChild(empty);
  }
  data.files.forEach(file => {
    const row = document.createElement('div');
    row.className = 'project-file-row';
    const filename = document.createElement('span');
    filename.className = 'text-ellipsis';
    filename.textContent = file.filename || 'Unnamed file';
    filename.title = file.filename || 'Unnamed file';
    const remove = button('Remove', 'project-row-action');
    remove.addEventListener('click', async () => {
      setPending([remove, dropZone], true);
      try {
        await request(`/projects/${encodeURIComponent(project.id)}/files/${encodeURIComponent(file.upload_id)}`, { method: 'DELETE' });
        uiModule.showToast('File removed');
        await openProjectSettings(project.id);
      } catch (error) {
        uiModule.showError(`File: ${detail(error, 'Could not remove')}`);
      } finally {
        setPending([remove, dropZone], false);
      }
    });
    row.append(filename, remove);
    files.appendChild(row);
  });
  body.appendChild(files);

  async function uploadFiles(selected) {
    if (!selected.length || dropZone.disabled) return;
    setPending([fileInput, dropZone], true);
    dropZone.textContent = 'Uploading files…';
    try {
      const form = new FormData();
      selected.forEach(file => form.append('files', file, file.name));
      const uploaded = await request('/upload', { method: 'POST', body: form });
      for (const file of uploaded.files || []) {
        await request(`/projects/${encodeURIComponent(project.id)}/files`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ upload_id: file.id }),
        });
      }
      uiModule.showToast('Files attached');
      await openProjectSettings(project.id);
    } catch (error) {
      uploadStatus.textContent = `Upload failed: ${detail(error, 'Unknown error')}`;
      uiModule.showError('Project file upload failed');
    } finally {
      setPending([fileInput, dropZone], false);
      dropZone.textContent = 'Drop files here or click to upload';
    }
  }

  dropZone.addEventListener('click', () => fileInput.click());
  ['dragenter', 'dragover'].forEach(type => dropZone.addEventListener(type, event => {
    event.preventDefault();
    if (dropZone.disabled) return;
    dropZone.classList.add('dragover');
  }));
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', event => {
    event.preventDefault();
    dropZone.classList.remove('dragover');
    if (dropZone.disabled) return;
    uploadFiles(Array.from(event.dataTransfer?.files || []));
  });
  fileInput.addEventListener('change', () => {
    const selected = Array.from(fileInput.files || []);
    fileInput.value = '';
    uploadFiles(selected);
  });

}

function renderChats(data) {
  const body = showModal();
  const project = data.project;
  activeProjectId = project.id;
  document.getElementById('projects-modal-title').textContent = project.name || 'Project';
  body.textContent = '';

  const chatsTitle = document.createElement('h5');
  chatsTitle.textContent = 'Chats';
  const hasChats = data.sessions.length > 0;
  const newChat = button(hasChats ? 'New chat' : 'Start a chat', 'confirm-btn confirm-btn-secondary');
  newChat.addEventListener('click', async () => {
    setPending([newChat], true);
    try {
      await sessionModule.createProjectChat(project.id);
      syncSessionProject(project.id);
      closeModal();
    } catch (error) {
      uiModule.showError(`Project chat: ${detail(error, 'Choose a default chat model first')}`);
    } finally {
      setPending([newChat], false);
    }
  });
  const chatsHeader = document.createElement('div');
  chatsHeader.className = 'project-chats-header';
  chatsHeader.append(chatsTitle);
  if (hasChats) chatsHeader.append(newChat);
  body.appendChild(chatsHeader);
  const chats = document.createElement('div');
  chats.className = 'project-chat-list';
  if (!hasChats) {
    const empty = document.createElement('div');
    empty.className = 'project-chat-empty';
    const icon = document.createElement('div');
    icon.className = 'project-chat-empty-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/></svg>';
    const title = document.createElement('h6');
    title.textContent = 'No chats yet';
    const description = document.createElement('p');
    description.textContent = 'Start the first chat in this project.';
    empty.append(icon, title, description, newChat);
    chats.appendChild(empty);
  }
  data.sessions.forEach(session => {
    const row = button(session.name || 'Untitled chat', 'project-chat-row');
    row.addEventListener('click', () => {
      closeModal();
      sessionModule?.selectSession?.(session.id);
    });
    chats.appendChild(row);
  });
  body.appendChild(chats);
}

async function openProject(projectId) {
  activeProjectId = projectId;
  showDetailState('Loading project…');
  try {
    const data = await request(`/projects/${encodeURIComponent(projectId)}`);
    if (activeProjectId !== projectId) return;
    renderChats(data);
    request('/projects').then(items => {
      projects = items;
      renderSidebar();
    }).catch(() => {});
  } catch (error) {
    showDetailState(`Unable to load project: ${detail(error, 'Unknown error')}`);
  }
}

async function openProjectSettings(projectId) {
  activeProjectId = projectId;
  showDetailState('Loading project settings…');
  try {
    const data = await request(`/projects/${encodeURIComponent(projectId)}`);
    if (activeProjectId !== projectId) return;
    renderSettings(data);
  } catch (error) {
    showDetailState(`Unable to load project settings: ${detail(error, 'Unknown error')}`);
  }
}

async function createProject() {
  const name = await uiModule.styledPrompt('Name your project.', { title: 'New project', placeholder: 'Project name', confirmText: 'Create', maxLength: 100, required: true });
  if (!name) return;
  const create = document.getElementById('project-create-btn');
  setPending([create], true);
  try {
    const project = await request('/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    projects.unshift(project);
    renderSidebar();
    uiModule.showToast('Project created');
    openProjectSettings(project.id);
  } catch (error) {
    uiModule.showError(`Project: ${detail(error, 'Could not create')}`);
  } finally {
    setPending([create], false);
  }
}

function syncSessionProject(projectId) {
  let label = document.getElementById('current-project-name');
  if (!label) {
    const current = document.getElementById('current-meta');
    if (!current) return;
    label = document.createElement('button');
    label.id = 'current-project-name';
    label.className = 'current-project-name';
    label.type = 'button';
    label.addEventListener('click', async () => {
      const currentId = sessionModule?.getCurrentSessionId?.();
      const pending = sessionModule?.getPendingChat?.();
      const session = sessionModule?.getSessions?.().find(item => item.id === currentId)
        || (currentId ? { id: currentId, project_id: label.dataset.projectId || null } : pending);
      if (!session) return;
      const sessionProjectId = session.project_id || session.projectId;
      if (sessionProjectId) openProject(sessionProjectId);
      else {
        if (!projects.length) await loadProjects();
        openProjectPicker(session);
      }
    });
    current.after(label);
  }
  const name = projectName(projectId);
  label.textContent = projectId ? name || 'Project' : 'No project';
  label.title = projectId ? `Open project: ${name || 'Project'}` : (
    sessionModule?.getCurrentSessionId?.()
      ? 'Move this chat to a project to use its files'
      : 'Start a chat inside a project to use its files'
  );
  label.setAttribute('aria-label', label.title);
  label.dataset.projectId = projectId || '';
  label.disabled = !sessionModule?.getCurrentSessionId?.() && !sessionModule?.getPendingChat?.();
}

async function moveSession(session, projectId) {
  if (session.id) {
    await request(`/projects/${encodeURIComponent(projectId)}/sessions/${encodeURIComponent(session.id)}`, { method: 'POST' });
    session.project_id = projectId;
    sessionModule?.renderSessionList?.();
  } else {
    session.projectId = projectId;
  }
  if (sessionModule?.getCurrentSessionId?.() === session.id || sessionModule?.getPendingChat?.() === session) syncSessionProject(projectId);
  uiModule.showToast('Chat moved to project');
}

async function removeSession(session) {
  await request(`/projects/${encodeURIComponent(session.project_id)}/sessions/${encodeURIComponent(session.id)}`, { method: 'DELETE' });
  session.project_id = null;
  sessionModule?.renderSessionList?.();
  if (sessionModule?.getCurrentSessionId?.() === session.id) syncSessionProject(null);
  uiModule.showToast('Chat removed from project');
}

function openProjectPicker(session) {
  document.querySelectorAll('.session-dropdown-menu, .session-folder-submenu').forEach(menu => { menu.style.display = 'none'; });
  const picker = document.createElement('div');
  picker.className = 'modal';
  picker.innerHTML = '<div class="modal-content project-picker-content" role="dialog" aria-modal="true" aria-labelledby="project-picker-title"><div class="modal-header"><h4 id="project-picker-title">Move to project</h4><button type="button" class="close-btn" aria-label="Close">✖</button></div><div class="modal-body"></div></div>';
  const onKeydown = event => { if (event.key === 'Escape') close(); };
  const close = () => {
    document.removeEventListener('keydown', onKeydown);
    picker.remove();
  };
  picker.querySelector('.close-btn').addEventListener('click', close);
  picker.addEventListener('click', event => { if (event.target === picker) close(); });
  document.addEventListener('keydown', onKeydown);
  const body = picker.querySelector('.modal-body');
  if (!projects.length) {
    const empty = document.createElement('div');
    empty.className = 'project-detail-state';
    empty.textContent = 'Create a project first.';
    body.appendChild(empty);
  }
  projects.forEach(project => {
    const row = button(project.name || 'Untitled project', 'project-chat-row');
    row.addEventListener('click', async () => {
      setPending([row], true);
      try {
        await moveSession(session, project.id);
        close();
      } catch (error) {
        uiModule.showError(`Project: ${detail(error, 'Could not move chat')}`);
        setPending([row], false);
      }
    });
    body.appendChild(row);
  });
  document.body.appendChild(picker);
  requestAnimationFrame(() => picker.querySelector('button:not(.close-btn)')?.focus());
}

function sessionMenuItems(session) {
  const move = button('Move to project', 'dropdown-item-compact');
  move.addEventListener('click', async event => {
    event.stopPropagation();
    if (!projects.length) await loadProjects();
    openProjectPicker(session);
  });
  const items = [move];
  if (session.project_id) {
    const remove = button('Remove from project', 'dropdown-item-compact');
    remove.addEventListener('click', async event => {
      event.stopPropagation();
      setPending([move, remove], true);
      try {
        await removeSession(session);
      } catch (error) {
        uiModule.showError(`Project: ${detail(error, 'Could not remove chat')}`);
        setPending([move, remove], false);
      }
    });
    items.push(remove);
  }
  return items;
}

function init(sessions) {
  sessionModule = sessions;
  const create = document.getElementById('project-create-btn');
  if (create) create.addEventListener('click', createProject);
  loadProjects();
}

const projectsModule = { init, loadProjects, openProject, syncSessionProject, sessionMenuItems };

export default projectsModule;
