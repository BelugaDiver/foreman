/**
 * state.js — Centralized client-side state for the Foreman Test UI.
 *
 * All components read via getters and write via setters. Setters fire
 * registered listeners so the UI can react without polling state.
 *
 * localStorage keys:
 *   foremanUI::userId          — x-user-id header value
 *   foremanUI::apiBaseUrl      — foreman API base URL
 *   foremanUI::pollingInterval — polling interval in ms
 *   foremanUI::lastKnownUser   — cached user object (JSON)
 */

// ---------------------------------------------------------------------------
// Internal state
// ---------------------------------------------------------------------------

const _state = {
  user: {
    id: null,
    email: null,
    fullName: null,
    isActive: null,
    createdAt: null,
  },

  settings: {
    apiBaseUrl: 'http://localhost:8000',
    pollingIntervalMs: 3000,
    autoDiscoveryEnabled: true,
  },

  apiStatus: {
    isDiscovered: false,
    lastChecked: null,
    discoveryError: null,
  },

  projects: {
    items: [],
    isLoading: false,
    error: null,
    currentProjectId: null,
  },

  generations: {
    items: [],
    isLoading: false,
    error: null,
    currentGenerationId: null,
  },

  images: {
    byProject: {},
    isLoading: false,
    error: null,
    upload: {
      inProgress: false,
      fileName: null,
      progressPercent: 0,
      intent: null,
      error: null,
    },
  },

  styles: {
    items: [],
    isLoading: false,
    error: null,
  },

  ui: {
    currentView: 'auth',
    navHistory: [],
    notificationQueue: [],
  },

  polling: {
    activeJobId: null,
    pollingTimer: null,
    isPolling: false,
  },
};

// ---------------------------------------------------------------------------
// Listeners
// ---------------------------------------------------------------------------

/** @type {Record<string, Function[]>} */
const _listeners = {};

/**
 * Register a listener that fires whenever the named top-level key changes.
 * @param {string} key
 * @param {Function} callback
 */
export function onStateChange(key, callback) {
  if (!_listeners[key]) _listeners[key] = [];
  _listeners[key].push(callback);
}

export function onUserChange(cb) { onStateChange('user', cb); }
export function onProjectsChange(cb) { onStateChange('projects', cb); }
export function onGenerationsChange(cb) { onStateChange('generations', cb); }
export function onViewChange(cb) { onStateChange('ui', cb); }

function _fire(key) {
  (_listeners[key] || []).forEach(fn => fn(_state[key]));
}

// ---------------------------------------------------------------------------
// Hydrate from localStorage on module load
// ---------------------------------------------------------------------------

(function _hydrate() {
  const userId = localStorage.getItem('foremanUI::userId');
  if (userId) _state.user.id = userId;

  const cached = localStorage.getItem('foremanUI::lastKnownUser');
  if (cached) {
    try {
      const u = JSON.parse(cached);
      Object.assign(_state.user, u);
    } catch (_) { /* ignore corrupted cache */ }
  }

  const apiUrl = localStorage.getItem('foremanUI::apiBaseUrl');
  if (apiUrl) _state.settings.apiBaseUrl = apiUrl;

  const interval = localStorage.getItem('foremanUI::pollingInterval');
  if (interval) _state.settings.pollingIntervalMs = Number(interval);
})();

// ---------------------------------------------------------------------------
// Getters
// ---------------------------------------------------------------------------

export function getUser() { return { ..._state.user }; }
export function getApiUrl() { return _state.settings.apiBaseUrl; }
export function getPollingInterval() { return _state.settings.pollingIntervalMs; }
export function getSettings() { return { ..._state.settings }; }
export function getApiStatus() { return { ..._state.apiStatus }; }
export function getIsAuthenticated() { return _state.user.id !== null; }

export function getProjects() { return _state.projects.items; }
export function getCurrentProjectId() { return _state.projects.currentProjectId; }
export function getCurrentProject() {
  return _state.projects.items.find(p => p.id === _state.projects.currentProjectId) || null;
}
export function getProjectById(id) {
  return _state.projects.items.find(p => p.id === id) || null;
}

export function getGenerations() { return _state.generations.items; }
export function getCurrentGenerationId() { return _state.generations.currentGenerationId; }
export function getCurrentGeneration() {
  return _state.generations.items.find(g => g.id === _state.generations.currentGenerationId) || null;
}
export function getGenerationById(id) {
  return _state.generations.items.find(g => g.id === id) || null;
}
export function getGenerationsForProject(projectId) {
  return _state.generations.items.filter(g => g.projectId === projectId);
}

export function getStyles() { return _state.styles.items; }

export function getImagesForProject(projectId) {
  return _state.images.byProject[projectId] || [];
}
export function getUploadState() { return { ..._state.images.upload }; }

export function getCurrentView() { return _state.ui.currentView; }
export function getNotifications() { return [..._state.ui.notificationQueue]; }

export function isPollingActive() { return _state.polling.isPolling; }
export function getPollingJobId() { return _state.polling.activeJobId; }

// ---------------------------------------------------------------------------
// Setters
// ---------------------------------------------------------------------------

export function setUser(user) {
  Object.assign(_state.user, {
    id: user.id ?? null,
    email: user.email ?? null,
    fullName: user.full_name ?? user.fullName ?? null,
    isActive: user.is_active ?? user.isActive ?? null,
    createdAt: user.created_at ?? user.createdAt ?? null,
  });
  localStorage.setItem('foremanUI::userId', _state.user.id || '');
  localStorage.setItem('foremanUI::lastKnownUser', JSON.stringify(_state.user));
  _fire('user');
}

export function clearUser() {
  Object.assign(_state.user, { id: null, email: null, fullName: null, isActive: null, createdAt: null });
  localStorage.removeItem('foremanUI::userId');
  localStorage.removeItem('foremanUI::lastKnownUser');
  _fire('user');
}

export function setApiUrl(url) {
  _state.settings.apiBaseUrl = url;
  localStorage.setItem('foremanUI::apiBaseUrl', url);
  _fire('settings');
}

export function setPollingInterval(ms) {
  _state.settings.pollingIntervalMs = ms;
  localStorage.setItem('foremanUI::pollingInterval', String(ms));
  _fire('settings');
}

export function setApiStatus(isDiscovered, error = null) {
  _state.apiStatus.isDiscovered = isDiscovered;
  _state.apiStatus.lastChecked = new Date().toISOString();
  _state.apiStatus.discoveryError = error;
  _fire('apiStatus');
}

export function setProjects(projects) {
  _state.projects.items = projects;
  _state.projects.isLoading = false;
  _state.projects.error = null;
  _fire('projects');
}

export function setProjectsLoading(loading) {
  _state.projects.isLoading = loading;
  _fire('projects');
}

export function setProjectsError(error) {
  _state.projects.isLoading = false;
  _state.projects.error = error;
  _fire('projects');
}

export function addProject(project) {
  _state.projects.items = [project, ..._state.projects.items];
  _fire('projects');
}

export function updateProjectInState(updated) {
  _state.projects.items = _state.projects.items.map(p => p.id === updated.id ? updated : p);
  _fire('projects');
}

export function setCurrentProject(projectId) {
  _state.projects.currentProjectId = projectId;
  _fire('projects');
}

export function setGenerations(generations) {
  _state.generations.items = generations;
  _state.generations.isLoading = false;
  _state.generations.error = null;
  _fire('generations');
}

export function setGenerationsLoading(loading) {
  _state.generations.isLoading = loading;
  _fire('generations');
}

export function addGeneration(generation) {
  _state.generations.items = [generation, ..._state.generations.items];
  _fire('generations');
}

export function updateGenerationInState(updated) {
  _state.generations.items = _state.generations.items.map(g => g.id === updated.id ? updated : g);
  _fire('generations');
}

export function removeGenerationFromState(genId) {
  _state.generations.items = _state.generations.items.filter(g => g.id !== genId);
  if (_state.generations.currentGenerationId === genId) {
    _state.generations.currentGenerationId = null;
  }
  _fire('generations');
}

export function setCurrentGeneration(genId) {
  _state.generations.currentGenerationId = genId;
  _fire('generations');
}

export function setStyles(styles) {
  _state.styles.items = styles;
  _state.styles.isLoading = false;
  _state.styles.error = null;
  _fire('styles');
}

export function setImagesForProject(projectId, images) {
  _state.images.byProject = { ..._state.images.byProject, [projectId]: images };
  _state.images.isLoading = false;
  _state.images.error = null;
  _fire('images');
}

export function setUploadProgress(percent) {
  _state.images.upload.progressPercent = percent;
  _state.images.upload.inProgress = percent < 100;
  _fire('images');
}

export function setUploadIntent(intent) {
  _state.images.upload.intent = intent;
  _state.images.upload.inProgress = true;
  _state.images.upload.error = null;
  _state.images.upload.fileName = intent.fileName ?? null;
  _fire('images');
}

export function setUploadError(message) {
  _state.images.upload.error = message;
  _state.images.upload.inProgress = false;
  _fire('images');
}

export function clearUpload() {
  _state.images.upload = {
    inProgress: false,
    fileName: null,
    progressPercent: 0,
    intent: null,
    error: null,
  };
  _fire('images');
}

export function switchView(viewName) {
  const prev = _state.ui.currentView;
  if (prev !== viewName) {
    _state.ui.navHistory.push(prev);
    if (_state.ui.navHistory.length > 20) _state.ui.navHistory.shift();
  }
  _state.ui.currentView = viewName;
  _fire('ui');
}

export function goBack() {
  const prev = _state.ui.navHistory.pop();
  if (prev) {
    _state.ui.currentView = prev;
    _fire('ui');
  }
}

let _notifCounter = 0;

export function addNotification(type, message, duration = 5000) {
  const id = `notif-${++_notifCounter}`;
  _state.ui.notificationQueue = [..._state.ui.notificationQueue, { id, type, message, duration }];
  _fire('ui');
  return id;
}

export function dismissNotification(id) {
  _state.ui.notificationQueue = _state.ui.notificationQueue.filter(n => n.id !== id);
  _fire('ui');
}

export function setPollingState(activeJobId, timer, isPolling) {
  _state.polling.activeJobId = activeJobId;
  _state.polling.pollingTimer = timer;
  _state.polling.isPolling = isPolling;
}
