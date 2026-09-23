let polling = null;
let loading = false;
let triggering = false;

const el = id => document.getElementById(id);

function render(status) {
  const button = el('adm-nativeUpdateBtn');
  const message = el('adm-nativeUpdateStatus');
  const commit = el('adm-nativeUpdateCommit');
  if (!button || !message || !commit) return;

  if ('current_commit' in status) {
    commit.textContent = /^[0-9a-f]{40,64}$/.test(status.current_commit)
      ? status.current_commit.slice(0, 12) : 'Unavailable';
  } else if (commit.textContent === 'Loading…') commit.textContent = 'Unavailable';

  const state = status.state;
  message.dataset.state = state;
  if (state === 'disabled') message.textContent = 'Self-update is off. Set ODYSSEUS_SELF_UPDATE=true in .env and restart the service.';
  else if (state === 'running') message.textContent = 'Updating and restarting. Connection may pause briefly.';
  else if (state === 'success') message.textContent = 'Update completed. Service restarted.';
  else if (state === 'up_to_date') message.textContent = 'Already up to date. No restart needed.';
  else if (state === 'failed' && /^(Dirty worktree rejected|Non-fast-forward update rejected|Current branch differs from configured branch)$/.test(status.message)) {
    message.textContent = status.message;
  } else if (state === 'failed') message.textContent = 'Update failed. Check the update service journal.';
  else if (state === 'forbidden') message.textContent = 'Admin access required.';
  else if (state === 'error') message.textContent = 'Could not reach update status. Retrying.';
  else message.textContent = 'Ready to check for updates.';

  message.className = 'admin-toggle-sub';
  button.disabled = triggering || state === 'running' || state === 'disabled' || state === 'forbidden' || state === 'error';

  if (state === 'running' || state === 'error') {
    if (!polling) polling = setInterval(() => {
      if (el('settings-modal')?.classList.contains('hidden')) {
        clearInterval(polling);
        polling = null;
      } else return refreshNativeUpdate();
    }, 3000);
  } else if (polling) {
    clearInterval(polling);
    polling = null;
  }
}

export async function refreshNativeUpdate() {
  if (!window._isAdmin || loading) return;
  loading = true;
  try {
    const response = await fetch('/api/admin/update/status', { credentials: 'same-origin' });
    if (response.status === 404) render({ state: 'disabled' });
    else if (response.status === 403 || response.status === 401) render({ state: 'forbidden' });
    else if (!response.ok) render({ state: 'error' });
    else render(await response.json());
  } catch (_) {
    render({ state: 'error' });
  } finally {
    loading = false;
  }
}

export function initNativeUpdate(confirm) {
  const button = el('adm-nativeUpdateBtn');
  if (!button) return;
  button.addEventListener('click', async () => {
    if (triggering || button.disabled) return;
    triggering = true;
    button.disabled = true;
    try {
      if (!await confirm('Update Odysseus and restart the service? Active chats will disconnect.', { confirmText: 'Update & restart' })) return;
      render({ state: 'running' });
      const response = await fetch('/api/admin/update', { method: 'POST', credentials: 'same-origin' });
      if (response.status === 404) render({ state: 'disabled' });
      else if (response.status === 403 || response.status === 401) render({ state: 'forbidden' });
      else await refreshNativeUpdate();
    } catch (_) {
      render({ state: 'error' });
    } finally {
      triggering = false;
      button.disabled = ['running', 'disabled', 'forbidden', 'error'].includes(
        el('adm-nativeUpdateStatus')?.dataset.state
      );
    }
  });
}
