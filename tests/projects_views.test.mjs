import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

function makeClassList() {
  const values = new Set();
  return {
    add: (...names) => names.forEach(name => values.add(name)),
    remove: (...names) => names.forEach(name => values.delete(name)),
    contains: name => values.has(name),
  };
}

const elements = new Map();
function makeElement(tag = 'div') {
  let text = '';
  let html = '';
  const element = {
    tagName: tag.toUpperCase(), id: '', className: '', type: '', title: '', value: '',
    disabled: false, hidden: false, dataset: {}, style: {}, children: [],
    classList: makeClassList(), attributes: {},
    append(...nodes) { this.children.push(...nodes); },
    appendChild(node) { this.children.push(node); return node; },
    addEventListener(type, handler) { this[`${type}Handler`] = handler; },
    setAttribute(name, value) { this.attributes[name] = value; },
    querySelector(selector) { return this.queries?.[selector] || null; },
    remove() { this.removed = true; },
    after(node) { elements.set(node.id, node); this.afterNode = node; },
    focus() {},
  };
  Object.defineProperty(element, 'textContent', {
    get: () => text,
    set(value) { text = String(value); if (value === '') element.children = []; },
  });
  Object.defineProperty(element, 'innerHTML', {
    get: () => html,
    set(value) {
      html = String(value);
      if (!html.includes('projects-modal-title') && !html.includes('project-picker-title')) return;
      const title = makeElement('h4');
      const close = makeElement('button');
      const body = makeElement('div');
      const content = makeElement('div');
      const header = makeElement('div');
      if (html.includes('projects-modal-title')) elements.set('projects-modal-title', title);
      element.queries = {
        '.close-btn': close,
        '.modal-content': content,
        '.modal-header': header,
        '.project-modal-body': body,
        '.modal-body': body,
      };
    },
  });
  return element;
}

const projectList = makeElement();
elements.set('project-list', projectList);
elements.set('current-meta', makeElement());
globalThis.document = {
  getElementById: id => elements.get(id) || null,
  createElement: tag => makeElement(tag),
  addEventListener() {},
  querySelectorAll: () => [],
  body: { lastModal: null, appendChild(node) { this.lastModal = node; } },
};
globalThis.window = { location: { origin: 'http://test' } };
globalThis.requestAnimationFrame = callback => callback();
globalThis.projectDragCalls = [];

const source = readFileSync(new URL('../static/js/projects.js', import.meta.url), 'utf8')
  .replace("import uiModule from './ui.js';", "const uiModule = { isTouchInsideModal: () => false, showError() {}, showToast() {}, styledConfirm: async () => true, styledPrompt: async () => null };")
  .replace("import { makeWindowDraggable } from './windowDrag.js';", "const makeWindowDraggable = (...args) => globalThis.projectDragCalls.push(args);");
const { default: projects } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

const requests = [];
let projectGetCount = 0;
globalThis.fetch = async (url, options = {}) => {
  requests.push(url);
  if (url.endsWith('/api/projects/1')) {
    if (options.method === 'PATCH') return { ok: true, json: async () => ({ id: '1', name: 'eps 6 updated', instructions: 'Saved' }) };
    projectGetCount += 1;
    return { ok: true, json: async () => ({ project: { id: '1', name: 'eps 6', instructions: '' }, files: [], sessions: projectGetCount === 1 ? [] : [{ id: 's1', name: 'Chat one' }] }) };
  }
  return { ok: true, json: async () => [{ id: '1', name: 'eps 6' }] };
};

function contains(root, predicate) {
  return predicate(root) || root.children.some(child => contains(child, predicate));
}

await projects.loadProjects();
let sidebarRow = projectList.children[0];
await sidebarRow.children[0].clickHandler();
let modalBody = document.body.lastModal?.querySelector('.project-modal-body');
const title = elements.get('projects-modal-title');
assert.equal(title.textContent, 'eps 6');
assert.equal(projectDragCalls.length, 1);
assert.equal(projectDragCalls[0][0], document.body.lastModal);
assert.equal(projectDragCalls[0][1].enableDock, false);
assert.equal(projectDragCalls[0][1].enableResize, false);
assert.ok(contains(modalBody, child => child.textContent === 'Chats'));
assert.ok(contains(modalBody, child => child.textContent === 'No chats yet'));
assert.ok(contains(modalBody, child => child.textContent === 'Start a chat'));

sidebarRow = projectList.children[0];
await sidebarRow.children[1].clickHandler();
modalBody = document.body.lastModal.querySelector('.project-modal-body');
assert.equal(requests.filter(url => url.endsWith('/api/projects/1')).length, 2);
assert.ok(modalBody.children.some(child => child.className === 'project-field'));
assert.ok(modalBody.children.some(child => child.className === 'modal-footer project-actions'));
const save = modalBody.children.find(child => child.className === 'modal-footer project-actions').children[0];
await save.clickHandler();
assert.equal(projectGetCount, 2);
assert.equal(title.textContent, 'eps 6 updated');

projects.init({
  getSessions: () => [],
  getCurrentSessionId: () => 's1',
  getPendingChat: () => null,
  renderSessionList() {},
});
projects.syncSessionProject(null);
const projectLabel = elements.get('current-project-name');
assert.equal(projectLabel.disabled, false);
assert.equal(projectLabel.textContent, 'No project');
await projectLabel.clickHandler();
const pickerBody = document.body.lastModal.querySelector('.modal-body');
assert.ok(contains(pickerBody, child => child.textContent === 'eps 6 updated'));
console.log('ok');
