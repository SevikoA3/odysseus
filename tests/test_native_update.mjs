import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { initNativeUpdate, refreshNativeUpdate } from '../static/js/nativeUpdate.js';

assert.match(
  readFileSync(new URL('../static/index.html', import.meta.url), 'utf8'),
  /class="admin-card admin-only" id="settings-native-update-card" style="display:none"/,
);

const elements = Object.fromEntries(
  ['adm-nativeUpdateBtn', 'adm-nativeUpdateStatus', 'adm-nativeUpdateCommit', 'settings-modal']
    .map(id => [id, {
      textContent: id === 'adm-nativeUpdateCommit' ? 'Loading…' : '',
      dataset: {}, disabled: true, className: '',
      classList: { contains: () => false },
      addEventListener(type, handler) { this[`${type}Handler`] = handler; },
      click() { return this.clickHandler(); },
    }]),
);
globalThis.document = { getElementById: id => elements[id] };
globalThis.window = { _isAdmin: true };
let poll;
globalThis.setInterval = callback => { poll = callback; return 1; };
globalThis.clearInterval = () => { poll = null; };

const responses = [];
const calls = [];
globalThis.fetch = async (url, options = {}) => {
  calls.push([url, options.method || 'GET']);
  const response = responses.shift();
  assert.ok(response, `Unexpected request: ${url}`);
  if (response.throw) throw new Error('Connection lost');
  return { status: response.status || 200, ok: !response.status || response.status === 200, json: async () => response.body };
};

const button = elements['adm-nativeUpdateBtn'];
const message = elements['adm-nativeUpdateStatus'];
let confirmed = false;
initNativeUpdate(async () => confirmed);

window._isAdmin = false;
await refreshNativeUpdate();
assert.equal(calls.length, 0);
window._isAdmin = true;

responses.push({ status: 404 });
await refreshNativeUpdate();
assert.match(message.textContent, /Self-update is off/);
assert.equal(button.disabled, true);

responses.push({ body: { state: 'running', active: true, current_commit: 'a'.repeat(40) } });
await refreshNativeUpdate();
assert.equal(button.disabled, true);
assert.equal(elements['adm-nativeUpdateCommit'].textContent, 'a'.repeat(12));
assert.ok(poll);

responses.push({ body: { state: 'up_to_date', active: false, current_commit: 'a'.repeat(40) } });
await refreshNativeUpdate();
assert.match(message.textContent, /Already up to date/);
assert.equal(button.disabled, false);
assert.equal(poll, null);

await button.click();
assert.equal(calls.filter(([, method]) => method === 'POST').length, 0);

confirmed = true;
responses.push({ body: { ok: true, state: 'running' } });
responses.push({ body: { state: 'success', active: false, current_commit: 'b'.repeat(40) } });
await button.click();
assert.match(message.textContent, /Update completed/);
assert.equal(button.disabled, false);
assert.equal(calls.filter(([, method]) => method === 'POST').length, 1);

responses.push({ body: { state: 'failed', message: 'secret raw output' } });
await refreshNativeUpdate();
assert.equal(message.textContent, 'Update failed. Check the update service journal.');

responses.push({ body: { state: 'failed', message: 'Dirty worktree rejected' } });
await refreshNativeUpdate();
assert.equal(message.textContent, 'Dirty worktree rejected');

responses.push({ throw: true });
await refreshNativeUpdate();
assert.match(message.textContent, /Retrying/);
assert.equal(button.disabled, true);
responses.push({ body: { state: 'success', active: false, current_commit: 'b'.repeat(40) } });
await poll();
assert.match(message.textContent, /Update completed/);
assert.equal(poll, null);
