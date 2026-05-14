/**
 * projects.js — Project list and creation component.
 *
 * Handles:
 *   - List all projects for current user
 *   - Create new project
 *   - Select active project (sets context for upload + generation)
 *   - Shows original_image_url status indicator per project
 */

import * as api from '../api.js';
import * as state from '../state.js';
import { formatDate, truncate } from './utils.js';
import { normaliseProject } from '../app.js';

export async function renderProjects(container) {
  if (!container) return;

  if (!state.getIsAuthenticated()) {
    container.innerHTML = `
      <div class="panel">
        <div class="warning-banner">Please create or enter a user ID in the Auth tab first.</div>
      </div>`;
    return;
  }

  container.innerHTML = `
    <div class="panel">
      <h2>Projects</h2>

      <!-- Create project form -->
      <form id="project-form" novalidate>
        <div class="field">
          <label for="project-name">New project name</label>
          <input id="project-name" type="text" placeholder="My Test Project" required />
        </div>
        <div id="project-form-error" class="error-msg hidden"></div>
        <div class="btn-row">
          <button type="submit" class="btn-primary" id="project-submit">Create Project</button>
          <button type="button" class="btn-secondary" id="refresh-projects">↻ Refresh</button>
        </div>
      </form>
    </div>

    <div class="panel">
      <h3>Your Projects</h3>
      <div id="projects-list">
        <div class="loading-row"><span class="spinner"></span> Loading…</div>
      </div>
    </div>
  `;

  // Wire create form
  const form = container.querySelector('#project-form');
  const errorEl = container.querySelector('#project-form-error');
  const submitBtn = container.querySelector('#project-submit');

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const name = container.querySelector('#project-name').value.trim();
    if (!name) { showError(errorEl, 'Project name is required.'); return; }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Creating…';
    hideError(errorEl);

    try {
      const project = await api.createProject(name);
      const normalised = normaliseProject(project);
      state.addProject(normalised);
      state.setCurrentProject(normalised.id);
      container.querySelector('#project-name').value = '';
      state.addNotification('success', `Project "${normalised.name}" created.`);
      _renderList(container);
    } catch (err) {
      showError(errorEl, err.message);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Create Project';
    }
  });

  container.querySelector('#refresh-projects').addEventListener('click', () => {
    _loadProjects(container);
  });

  // Initial load
  await _loadProjects(container);
}

async function _loadProjects(container) {
  const listEl = container.querySelector('#projects-list');
  if (!listEl) return;
  listEl.innerHTML = '<div class="loading-row"><span class="spinner"></span> Loading…</div>';

  try {
    const projects = await api.listProjects();
    const normalised = projects.map(normaliseProject);
    state.setProjects(normalised);
    _renderList(container);
  } catch (err) {
    listEl.innerHTML = `<div class="error-msg">Failed to load projects: ${escHtml(err.message)}</div>`;
  }
}

function _renderList(container) {
  const listEl = container.querySelector('#projects-list');
  if (!listEl) return;

  const projects = state.getProjects();
  const currentId = state.getCurrentProjectId();

  if (projects.length === 0) {
    listEl.innerHTML = '<div class="empty-state"><strong>No projects yet</strong><p>Create one above to get started.</p></div>';
    return;
  }

  const ul = document.createElement('ul');
  ul.className = 'item-list';

  projects.forEach(p => {
    const li = document.createElement('li');
    const hasImage = !!p.originalImageUrl;

    li.innerHTML = `
      <div class="item-card ${p.id === currentId ? 'selected' : ''}">
        <div>
          <div class="item-card-title">${escHtml(p.name)}</div>
          <div class="item-card-meta">Created ${formatDate(p.createdAt)}</div>
        </div>
        <div class="item-card-right">
          <span class="${hasImage ? 'img-indicator-ok' : 'img-indicator-nil'}"
                title="${hasImage ? 'Input image set' : 'No input image — upload required before first generation'}">
            ${hasImage ? '🖼 Image set' : '⚠ No image'}
          </span>
          <button class="btn-secondary btn-sm select-btn" data-id="${p.id}">Select</button>
          <button class="btn-secondary btn-sm upload-btn" data-id="${p.id}">Upload Image</button>
        </div>
      </div>
    `;
    ul.appendChild(li);
  });

  listEl.innerHTML = '';
  listEl.appendChild(ul);

  // Select buttons
  listEl.querySelectorAll('.select-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const id = btn.dataset.id;
      state.setCurrentProject(id);
      _renderList(container);
      state.addNotification('info', `Project selected.`, 2000);
    });
  });

  // Upload image buttons
  listEl.querySelectorAll('.upload-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      state.setCurrentProject(btn.dataset.id);
      import('../app.js').then(app => app.switchView('image-upload'));
    });
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escHtml(str) {
  return String(str ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function showError(el, msg) { el.textContent = msg; el.classList.remove('hidden'); }
function hideError(el) { el.textContent = ''; el.classList.add('hidden'); }
