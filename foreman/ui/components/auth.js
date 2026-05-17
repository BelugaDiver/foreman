/**
 * auth.js — User creation and authentication component.
 *
 * Handles:
 *   - User creation form (email + full name)
 *   - Stores returned user ID in state + localStorage
 *   - Displays current authenticated user
 *   - Warning if no user is set
 */

import * as api from '../api.js';
import * as state from '../state.js';
import { parseApiError } from './utils.js';

export function renderAuth(container) {
  if (!container) return;

  const user = state.getUser();

  if (user.id) {
    _renderLoggedIn(container, user);
  } else {
    _renderCreateForm(container);
  }
}

// ---------------------------------------------------------------------------
// Logged-in view
// ---------------------------------------------------------------------------

function _renderLoggedIn(container, user) {
  container.innerHTML = `
    <div class="panel">
      <h2>Authentication</h2>
      <div class="api-status status-ok">✓ Authenticated</div>
      <dl class="gen-meta-grid">
        <dt>User ID</dt>
        <dd><code>${escHtml(user.id)}</code></dd>
        <dt>Email</dt>
        <dd>${escHtml(user.email || '—')}</dd>
        <dt>Name</dt>
        <dd>${escHtml(user.fullName || '—')}</dd>
      </dl>
      <div class="btn-row">
        <button class="btn-secondary" id="switch-user-btn">Use a different user</button>
      </div>
    </div>
  `;

  container.querySelector('#switch-user-btn').addEventListener('click', () => {
    state.clearUser();
    renderAuth(container);
  });
}

// ---------------------------------------------------------------------------
// Create user form
// ---------------------------------------------------------------------------

function _renderCreateForm(container) {
  container.innerHTML = `
    <div class="panel">
      <h2>Create Test User</h2>
      <p class="text-muted mb-16">
        Create a test user to get an x-user-id for all API requests.
        Or enter an existing UUID manually in <a href="#" data-view="settings">Settings</a>.
      </p>

      <form id="auth-form" novalidate>
        <div class="field">
          <label for="auth-email">Email</label>
          <input id="auth-email" type="email" placeholder="dev@example.com" autocomplete="email" required />
        </div>
        <div class="field">
          <label for="auth-name">Full name</label>
          <input id="auth-name" type="text" placeholder="Dev User" autocomplete="name" required />
        </div>

        <div id="auth-error" class="error-msg hidden"></div>

        <div class="btn-row">
          <button type="submit" class="btn-primary" id="auth-submit">Create User</button>
        </div>
      </form>
    </div>
  `;

  // Wire settings link
  container.querySelector('a[data-view]').addEventListener('click', e => {
    e.preventDefault();
    import('../app.js').then(app => app.switchView('settings'));
  });

  const form = container.querySelector('#auth-form');
  const errorEl = container.querySelector('#auth-error');
  const submitBtn = container.querySelector('#auth-submit');

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const email = container.querySelector('#auth-email').value.trim();
    const name = container.querySelector('#auth-name').value.trim();

    if (!email || !name) {
      showError(errorEl, 'Email and name are required.');
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Creating…';
    hideError(errorEl);

    try {
      const user = await api.createUser(email, name);
      state.setUser(user);
      state.addNotification('success', `User created — ID: ${user.id}`);

      // Navigate to projects view
      import('../app.js').then(app => app.switchView('projects'));
    } catch (err) {
      showError(errorEl, err.message);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Create User';
    }
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
