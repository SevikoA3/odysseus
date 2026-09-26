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
    tagName: tag.toUpperCase(), className: '', type: '', title: '', value: '',
    disabled: false, hidden: false, dataset: {}, style: {}, children: [],
    classList: makeClassList(), attributes: {},
    append(...nodes) { this.children.push(...nodes); },
    appendChild(node) { this.children.push(node); return node; },
    addEventListener(type, handler) { this[`${type}Handler`] = handler; },
    setAttribute(name, value) { this.attributes[name] = value; },
    querySelector(selector) { return this.queries?.[selector] || null; },
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
      if (!html.includes('projects-modal-title')) return;
      const title = makeElement('h4');
      const close = makeElement('button');
      const body = makeElement('div');
      elements.set('projects-modal-title', title);
      element.queries = { '.close-btn': close, '.project-modal-body': body };
    },
  });
  return element;
}

const projectList = makeElement();
elements.set('project-list', projectList);
globalThis.document = {
  getElementById: id => elements.get(id) || null,
  createElement: tag => makeElement(tag),
  addEventListener() {},
  querySelectorAll: () => [],
  body: { lastModal: null, appendChild(node) { this.lastModal = node; } },
};
globalThis.window = { location: { origin: 'http://test' } };
globalThis.requestAnimationFrame = callback => callback();

const source = readFileSync(new URL('../static/js/projects.js', import.meta.url), 'utf8')
  .replace("import uiModule from './ui.js';", "const uiModule = { isTouchInsideModal: () => false, showError() {}, showToast() {}, styledConfirm: async () => true, styledPrompt: async () => null };");
const { default: projects } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

const requests = [];
globalThis.fetch = async url => {
  requests.push(url);
  if (url.endsWith('/api/projects/1')) {
    return { ok: true, json: async () => ({ project: { id: '1', name: 'eps 6' }, files: [], sessions: [{ id: 's1', name: 'Chat one' }] }) };
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
assert.ok(contains(modalBody, child => child.textContent === 'Chats'));
assert.ok(contains(modalBody, child => child.textContent === 'Chat one'));

sidebarRow = projectList.children[0];
await sidebarRow.children[1].clickHandler();
modalBody = document.body.lastModal.querySelector('.project-modal-body');
assert.equal(requests.filter(url => url.endsWith('/api/projects/1')).length, 2);
assert.ok(modalBody.children.some(child => child.className === 'project-field'));
assert.ok(modalBody.children.some(child => child.className === 'modal-footer project-actions'));
console.log('ok');
