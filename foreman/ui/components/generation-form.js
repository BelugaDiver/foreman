/**
 * generation-form.js — Generation job creation form component.
 *
 * Handles:
 *   - Prompt textarea (required)
 *   - Style dropdown (optional, populated from state)
 *   - Warning banner if project.original_image_url is null (blocks submit)
 *   - Optional parent_id (pre-filled when forking)
 *   - Submits to POST /v1/projects/{id}/generations
 *   - Navigates to job-detail on success
 */

import * as api from '../api.js';
import * as state from '../state.js';
import { normaliseGeneration } from '../app.js';

// Parent ID pre-fill (set by fork button in job-detail.js)
let _pendingParentId = null;

export function setForkParentId(generationId) {
  _pendingParentId = generationId;
}

export async function renderGenerationForm(container) {
  if (!container) return;

  if (!state.getIsAuthenticated()) {
    container.innerHTML = `<div class="panel"><div class="warning-banner">Please authenticate first.</div></div>`;
    return;
  }

  const project = state.getCurrentProject();
  if (!project) {
    container.innerHTML = `
      <div class="panel">
        <div class="warning-banner">No project selected. Go to Projects and select one first.</div>
        <div class="btn-row mt-16">
          <button class="btn-primary" id="go-projects">Go to Projects</button>
        </div>
      </div>`;
    container.querySelector('#go-projects').addEventListener('click', () => {
      import('../app.js').then(app => app.switchView('projects'));
    });
    return;
  }

  const hasImage = !!project.originalImageUrl;
  const styles = state.getStyles();
  const parentId = _pendingParentId;

  // Clear pending parent after reading
  _pendingParentId = null;

  container.innerHTML = `
    <div class="panel">
      <h2>New Generation</h2>
      <p class="text-muted mb-16">Project: <strong>${escHtml(project.name)}</strong></p>

      ${!hasImage ? `
        <div class="warning-banner">
          This project has no input image set. Upload an image before submitting a generation —
          the API will reject the request without one.
          <a href="#" id="go-upload">Upload now</a>
        </div>
      ` : ''}

      <form id="gen-form" novalidate>
        <div class="field">
          <label for="gen-prompt">Prompt <span style="color:var(--color-danger)">*</span></label>
          <textarea id="gen-prompt" placeholder="Modern minimalist interior design…" required></textarea>
        </div>

        <div class="field">
          <label for="gen-style">Style (optional)</label>
          <select id="gen-style">
            <option value="">— No style —</option>
            ${styles.map(s => `<option value="${escHtml(s.id)}">${escHtml(s.name)}</option>`).join('')}
          </select>
          ${styles.length === 0 ? '<span class="field-hint">No styles available — generation will use default model settings.</span>' : ''}
        </div>

        <div class="field">
          <label for="gen-parent">Parent generation ID (optional — for forking)</label>
          <input id="gen-parent" type="text"
            placeholder="550e8400-e29b-41d4-a716-446655440002"
            value="${escHtml(parentId || '')}" />
          <span class="field-hint">If set, uses the parent's output image as input instead of the project's original image.</span>
        </div>

        <div id="gen-error" class="error-msg hidden"></div>

        <div class="btn-row">
          <button type="submit" class="btn-primary" id="gen-submit"
            ${!hasImage ? 'title="Upload an image to this project first"' : ''}>
            Submit Generation
          </button>
          <button type="button" class="btn-secondary" id="go-upload-btn">Upload Image</button>
        </div>
      </form>
    </div>
  `;

  if (!hasImage) {
    container.querySelector('#go-upload')?.addEventListener('click', e => {
      e.preventDefault();
      import('../app.js').then(app => app.switchView('image-upload'));
    });
  }

  container.querySelector('#go-upload-btn').addEventListener('click', () => {
    import('../app.js').then(app => app.switchView('image-upload'));
  });

  const form = container.querySelector('#gen-form');
  const errorEl = container.querySelector('#gen-error');
  const submitBtn = container.querySelector('#gen-submit');

  form.addEventListener('submit', async e => {
    e.preventDefault();

    const prompt = container.querySelector('#gen-prompt').value.trim();
    const styleId = container.querySelector('#gen-style').value;
    const rawParentId = container.querySelector('#gen-parent').value.trim();

    if (!prompt) {
      showError(errorEl, 'Prompt is required.');
      return;
    }

    const payload = { prompt };
    if (styleId) payload.style_id = styleId;
    if (rawParentId) payload.parent_id = rawParentId;

    submitBtn.disabled = true;
    submitBtn.textContent = 'Submitting…';
    hideError(errorEl);

    try {
      const gen = await api.createGeneration(project.id, payload);
      const normalised = normaliseGeneration(gen);
      state.addGeneration(normalised);
      state.setCurrentGeneration(normalised.id);
      state.addNotification('success', `Generation created — ID: ${normalised.id}`);
      import('../app.js').then(app => app.switchView('job-detail'));
    } catch (err) {
      showError(errorEl, err.message);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Submit Generation';
    }
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
