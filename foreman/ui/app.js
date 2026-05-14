/**
 * app.js — Main application controller.
 *
 * Handles:
 *   - Initialization sequence (API discovery → user validation → styles load)
 *   - View routing (switchView mirrors state.switchView + DOM show/hide)
 *   - Generation polling (startPolling / stopPolling)
 *   - Notification rendering
 *   - Tab visibility pause/resume for polling
 */

import * as api from './api.js';
import * as state from './state.js';
import { isTerminalStatus } from './components/utils.js';
import { renderSettings } from './components/settings.js';
import { renderAuth } from './components/auth.js';
import { renderProjects } from './components/projects.js';
import { renderImageUpload } from './components/image-upload.js';
import { renderGenerationForm } from './components/generation-form.js';
import { renderJobList } from './components/job-list.js';
import { renderJobDetail } from './components/job-detail.js';

// ---------------------------------------------------------------------------
// View registry
// ---------------------------------------------------------------------------

const VIEW_RENDERERS = {
  settings:     renderSettings,
  auth:         renderAuth,
  projects:     renderProjects,
  'image-upload': renderImageUpload,
  'job-form':   renderGenerationForm,
  'job-list':   renderJobList,
  'job-detail': renderJobDetail,
};

// ---------------------------------------------------------------------------
// Routing
// ---------------------------------------------------------------------------

export function switchView(viewName) {
  // Hide all view sections
  document.querySelectorAll('main > section[id^="view-"]').forEach(s => {
    s.classList.remove('active');
  });

  // Show target
  const target = document.getElementById(`view-${viewName}`);
  if (target) target.classList.add('active');

  // Update nav active link
  document.querySelectorAll('nav a[data-view]').forEach(a => {
    a.classList.toggle('active', a.dataset.view === viewName);
  });

  // Update state
  state.switchView(viewName);

  // Render component into view
  const renderer = VIEW_RENDERERS[viewName];
  if (renderer) renderer(target);
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

function renderNotifications() {
  const container = document.getElementById('notifications');
  if (!container) return;

  const notifications = state.getNotifications();
  container.innerHTML = '';

  notifications.forEach(({ id, type, message, duration }) => {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.setAttribute('role', 'alert');

    const text = document.createElement('span');
    text.textContent = message;

    const closeBtn = document.createElement('button');
    closeBtn.className = 'toast-close';
    closeBtn.textContent = '×';
    closeBtn.setAttribute('aria-label', 'Dismiss');
    closeBtn.addEventListener('click', () => state.dismissNotification(id));

    toast.appendChild(text);
    toast.appendChild(closeBtn);
    container.appendChild(toast);

    if (duration > 0) {
      setTimeout(() => state.dismissNotification(id), duration);
    }
  });
}

// ---------------------------------------------------------------------------
// Polling
// ---------------------------------------------------------------------------

let _pollingTimer = null;
let _isPaused = false;

export function startPolling(generationId) {
  stopPolling();
  state.setPollingState(generationId, null, true);

  const tick = async () => {
    if (_isPaused) return;
    try {
      const gen = await api.getGeneration(generationId);
      // Normalise API snake_case → camelCase for state
      const normalised = normaliseGeneration(gen);
      state.updateGenerationInState(normalised);

      if (isTerminalStatus(gen.status)) {
        stopPolling();
      }
    } catch (err) {
      // Network hiccup — keep polling, don't crash
      console.warn('Polling error:', err.message);
    }
  };

  const intervalMs = state.getPollingInterval();
  _pollingTimer = setInterval(tick, intervalMs);
  state.setPollingState(generationId, _pollingTimer, true);

  // Run first tick immediately
  tick();
}

export function stopPolling() {
  if (_pollingTimer !== null) {
    clearInterval(_pollingTimer);
    _pollingTimer = null;
  }
  state.setPollingState(null, null, false);
}

// Pause polling when tab is hidden, resume when visible
document.addEventListener('visibilitychange', () => {
  _isPaused = document.hidden;
});

// ---------------------------------------------------------------------------
// API Discovery
// ---------------------------------------------------------------------------

async function discoverApi() {
  // 1. Try configured base URL (default: localhost:8000)
  try {
    await api.checkHealth();
    state.setApiStatus(true);
    return true;
  } catch (_) { /* fall through */ }

  // 2. Try /.well-known/openapi.json relative to current origin
  try {
    const res = await fetch('/.well-known/openapi.json');
    if (res.ok) {
      // Found a well-known discovery endpoint — use current origin as base
      const origin = window.location.origin;
      state.setApiUrl(origin);
      state.setApiStatus(true);
      return true;
    }
  } catch (_) { /* fall through */ }

  // 3. Manual override required
  state.setApiStatus(false, 'Could not reach foreman API. Please set the API URL in Settings.');
  return false;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Normalise API snake_case response to camelCase for state storage. */
export function normaliseGeneration(g) {
  return {
    id: g.id,
    projectId: g.project_id,
    parentId: g.parent_id ?? null,
    status: g.status,
    prompt: g.prompt,
    styleId: g.style_id ?? null,
    modelUsed: g.model_used ?? null,
    inputImageUrl: g.input_image_url ?? null,
    outputImageUrl: g.output_image_url ?? null,
    errorMessage: g.error_message ?? null,
    processingTimeMs: g.processing_time_ms ?? null,
    attempt: g.attempt ?? 1,
    metadata: g.metadata ?? null,
    createdAt: g.created_at,
    updatedAt: g.updated_at,
  };
}

export function normaliseProject(p) {
  return {
    id: p.id,
    userId: p.user_id,
    name: p.name,
    originalImageUrl: p.original_image_url ?? null,
    roomAnalysis: p.room_analysis ?? null,
    createdAt: p.created_at,
    updatedAt: p.updated_at,
  };
}

export function normaliseImage(img) {
  return {
    id: img.id,
    projectId: img.project_id,
    userId: img.user_id,
    filename: img.filename,
    contentType: img.content_type,
    sizeBytes: img.size_bytes,
    storageKey: img.storage_key,
    url: img.url ?? null,
    createdAt: img.created_at,
    updatedAt: img.updated_at,
  };
}

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------

async function init() {
  // Listen for state changes and update notifications
  state.onStateChange('ui', () => renderNotifications());

  // Wire nav links
  document.querySelectorAll('nav a[data-view]').forEach(a => {
    a.addEventListener('click', e => {
      e.preventDefault();
      switchView(a.dataset.view);
    });
  });

  // API discovery
  const discovered = await discoverApi();
  if (!discovered) {
    state.addNotification('warning',
      'Could not reach foreman API. Open Settings to set the API URL.', 0);
  }

  // Validate existing user ID
  if (state.getIsAuthenticated()) {
    try {
      const user = await api.getUser_();
      state.setUser(user);
    } catch (_) {
      state.clearUser();
      state.addNotification('warning', 'Saved user ID is no longer valid. Please create or re-enter your user ID.', 0);
    }
  }

  // Pre-load styles for generation form
  try {
    const styles = await api.listStyles();
    state.setStyles(styles);
  } catch (_) { /* styles are optional */ }

  // Route to initial view
  const initialView = state.getIsAuthenticated() ? 'projects' : 'auth';
  switchView(initialView);
}

// Boot
init().catch(err => console.error('Foreman UI init error:', err));
