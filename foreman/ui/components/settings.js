/**
 * settings.js — Settings panel component.
 *
 * Allows the developer to configure:
 *   - Foreman API base URL
 *   - x-user-id (manual override)
 *   - Polling interval
 */

import * as state from '../state.js';
import { isValidUuid } from './utils.js';

export function renderSettings(container) {
  if (!container) return;

  const s = state.getSettings();
  const user = state.getUser();
  const apiStatus = state.getApiStatus();

  container.innerHTML = `
    <div class="panel">
      <h2>Settings</h2>

      <div class="api-status ${apiStatus.isDiscovered ? 'status-ok' : 'status-err'}">
        ${apiStatus.isDiscovered
          ? '✓ Connected to foreman API'
          : `✗ Not connected${apiStatus.discoveryError ? ': ' + apiStatus.discoveryError : ''}`}
      </div>

      <form id="settings-form" novalidate>
        <div class="field">
          <label for="api-url">Foreman API base URL</label>
          <input id="api-url" type="url" value="${escHtml(s.apiBaseUrl)}" placeholder="http://localhost:8000" />
        </div>

        <div class="field">
          <label for="user-id">x-user-id (UUID)</label>
          <input id="user-id" type="text" value="${escHtml(user.id || '')}"
            placeholder="550e8400-e29b-41d4-a716-446655440000" />
          <span class="field-hint">Leave blank to use the user created in the Auth tab.</span>
        </div>

        <div class="field">
          <label for="polling-interval">Polling interval (ms)</label>
          <input id="polling-interval" type="number" min="500" max="30000" step="500"
            value="${s.pollingIntervalMs}" />
        </div>

        <div id="settings-error" class="error-msg hidden"></div>

        <div class="btn-row">
          <button type="submit" class="btn-primary">Save Settings</button>
          <button type="button" id="test-connection" class="btn-secondary">Test Connection</button>
        </div>
      </form>
    </div>
  `;

  const form = container.querySelector('#settings-form');
  const errorEl = container.querySelector('#settings-error');

  form.addEventListener('submit', e => {
    e.preventDefault();
    const apiUrl = container.querySelector('#api-url').value.trim();
    const userId = container.querySelector('#user-id').value.trim();
    const interval = parseInt(container.querySelector('#polling-interval').value, 10);

    // Validate
    if (!apiUrl) {
      showError(errorEl, 'API URL is required.');
      return;
    }
    if (userId && !isValidUuid(userId)) {
      showError(errorEl, 'x-user-id must be a valid UUID.');
      return;
    }
    if (isNaN(interval) || interval < 500) {
      showError(errorEl, 'Polling interval must be at least 500ms.');
      return;
    }

    hideError(errorEl);
    state.setApiUrl(apiUrl);
    state.setPollingInterval(interval);

    if (userId) {
      // Manual override — merge into user state without clearing other fields
      const current = state.getUser();
      state.setUser({ ...current, id: userId });
    }

    state.addNotification('success', 'Settings saved.');
  });

  container.querySelector('#test-connection').addEventListener('click', async () => {
    import('../api.js').then(async api => {
      try {
        const health = await api.checkHealth();
        state.setApiStatus(true);
        state.addNotification('success', `Connected — foreman ${health.version || ''}`);
        renderSettings(container); // refresh status indicator
      } catch (err) {
        state.setApiStatus(false, err.message);
        state.addNotification('error', `Connection failed: ${err.message}`);
        renderSettings(container);
      }
    });
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function showError(el, msg) {
  el.textContent = msg;
  el.classList.remove('hidden');
}

function hideError(el) {
  el.textContent = '';
  el.classList.add('hidden');
}
