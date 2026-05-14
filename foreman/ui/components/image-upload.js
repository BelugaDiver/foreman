/**
 * image-upload.js — Image upload component.
 *
 * Flow:
 *   1. User picks a file (file input or drag-and-drop)
 *   2. Validate: content_type in allowed set, size ≤ 50MB
 *   3. POST /v1/projects/{id}/images → get presigned URL + image_id
 *   4. Check expires_at — if expired, re-request intent
 *   5. PUT file directly to presigned URL via XHR (tracks progress)
 *   6. GET /v1/images/{image_id} → retrieve signed download URL
 *   7. PATCH /v1/projects/{id} → set original_image_url
 *   8. Update project in state; refresh image gallery
 */

import * as api from '../api.js';
import * as state from '../state.js';
import { isExpired, formatBytes } from './utils.js';
import { normaliseProject, normaliseImage } from '../app.js';

const ALLOWED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/gif']);
const MAX_BYTES = 50 * 1024 * 1024; // 50 MB

export async function renderImageUpload(container) {
  if (!container) return;

  const project = state.getCurrentProject();

  if (!state.getIsAuthenticated()) {
    container.innerHTML = `<div class="panel"><div class="warning-banner">Please authenticate first.</div></div>`;
    return;
  }

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

  container.innerHTML = `
    <div class="panel">
      <h2>Upload Image</h2>
      <p class="text-muted mb-16">
        Project: <strong>${escHtml(project.name)}</strong>
        ${project.originalImageUrl
          ? ' — <span class="img-indicator-ok">Input image already set</span>'
          : ' — <span style="color:var(--status-warning)">⚠ No input image yet</span>'}
      </p>

      <div class="upload-zone" id="upload-zone" tabindex="0" role="button" aria-label="Click or drag a file to upload">
        <input type="file" id="file-input" accept="image/jpeg,image/png,image/webp,image/gif" />
        <p>Click to pick a file or drag and drop</p>
        <p class="text-muted text-small">JPEG, PNG, WebP, GIF — max 50 MB</p>
      </div>

      <div id="upload-status" class="hidden">
        <div id="upload-filename" class="text-bold mb-8"></div>
        <div class="progress-bar-track">
          <div class="progress-bar-fill" id="progress-fill" style="width:0%"></div>
        </div>
        <div id="upload-pct" class="text-muted text-small">0%</div>
      </div>

      <div id="upload-error" class="error-msg hidden"></div>
      <div id="upload-success" class="hidden" style="color:var(--color-success);margin-top:8px;"></div>
    </div>

    <div class="panel">
      <h3>Previously Uploaded Images</h3>
      <div id="image-gallery">
        <div class="loading-row"><span class="spinner"></span> Loading…</div>
      </div>
    </div>
  `;

  const zone = container.querySelector('#upload-zone');
  const fileInput = container.querySelector('#file-input');

  // Click to open file picker
  zone.addEventListener('click', () => fileInput.click());
  zone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') fileInput.click(); });

  // Drag-and-drop
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('dragover');
    const file = e.dataTransfer?.files?.[0];
    if (file) _handleFile(container, project.id, file);
  });

  fileInput.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    if (file) _handleFile(container, project.id, file);
  });

  // Load image gallery
  await _loadGallery(container, project.id);
}

// ---------------------------------------------------------------------------
// File handling
// ---------------------------------------------------------------------------

async function _handleFile(container, projectId, file) {
  const errorEl = container.querySelector('#upload-error');
  const successEl = container.querySelector('#upload-success');

  hideEl(errorEl);
  hideEl(successEl);

  // Validate type
  if (!ALLOWED_TYPES.has(file.type)) {
    showError(errorEl, `Unsupported file type: ${file.type}. Use JPEG, PNG, WebP, or GIF.`);
    return;
  }

  // Validate size
  if (file.size > MAX_BYTES) {
    showError(errorEl, `File too large: ${formatBytes(file.size)}. Maximum is 50 MB.`);
    return;
  }

  // Show progress UI
  const statusEl = container.querySelector('#upload-status');
  const fileNameEl = container.querySelector('#upload-filename');
  const fillEl = container.querySelector('#progress-fill');
  const pctEl = container.querySelector('#upload-pct');

  fileNameEl.textContent = file.name;
  statusEl.classList.remove('hidden');
  _setProgress(fillEl, pctEl, 0);

  try {
    // Step 1: Get presigned upload URL from foreman
    let intent = await api.createUploadIntent(projectId, file.name, file.type, file.size);
    state.setUploadIntent({ ...intent, fileName: file.name });

    // Step 2: Check expiry before PUT
    if (isExpired(intent.expires_at)) {
      intent = await api.createUploadIntent(projectId, file.name, file.type, file.size);
      state.setUploadIntent({ ...intent, fileName: file.name });
    }

    // Step 3: PUT file directly to storage via XHR (enables progress tracking)
    await _xhrPut(intent.upload_url, file, (pct) => {
      state.setUploadProgress(pct);
      _setProgress(fillEl, pctEl, pct);
    });

    _setProgress(fillEl, pctEl, 100);

    // Step 4: Get signed download URL
    const imageData = await api.getImage(intent.image_id);
    const image = normaliseImage(imageData);

    // Step 5: PATCH project to set original_image_url (only if not already set)
    const currentProject = state.getCurrentProject();
    if (!currentProject.originalImageUrl && image.url) {
      const updated = await api.updateProject(projectId, { original_image_url: image.url });
      state.updateProjectInState(normaliseProject(updated));
    }

    state.clearUpload();

    successEl.textContent = `✓ Uploaded "${file.name}" successfully.`;
    successEl.classList.remove('hidden');
    state.addNotification('success', 'Image uploaded and linked to project.');

    // Refresh gallery
    await _loadGallery(container, projectId);
  } catch (err) {
    state.setUploadError(err.message);
    showError(errorEl, err.message);
    _setProgress(fillEl, pctEl, 0);
  }
}

// ---------------------------------------------------------------------------
// XHR PUT with progress
// ---------------------------------------------------------------------------

function _xhrPut(url, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', url, true);
    xhr.setRequestHeader('Content-Type', file.type);

    xhr.upload.addEventListener('progress', e => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    });

    xhr.addEventListener('load', () => {
      if (xhr.status === 200 || xhr.status === 204) {
        resolve();
      } else if (xhr.status === 403) {
        reject(new Error('Upload URL has expired. Please try uploading again.'));
      } else {
        reject(new Error(`Storage upload failed with status ${xhr.status}.`));
      }
    });

    xhr.addEventListener('error', () => reject(new Error('Network error during file upload.')));
    xhr.addEventListener('abort', () => reject(new Error('Upload was aborted.')));

    xhr.send(file);
  });
}

// ---------------------------------------------------------------------------
// Image gallery
// ---------------------------------------------------------------------------

async function _loadGallery(container, projectId) {
  const galleryEl = container.querySelector('#image-gallery');
  if (!galleryEl) return;

  galleryEl.innerHTML = '<div class="loading-row"><span class="spinner"></span> Loading…</div>';

  try {
    const images = await api.listImages(projectId);
    const normalised = images.map(normaliseImage);
    state.setImagesForProject(projectId, normalised);

    if (normalised.length === 0) {
      galleryEl.innerHTML = '<div class="empty-state"><p>No images uploaded yet.</p></div>';
      return;
    }

    const gallery = document.createElement('div');
    gallery.className = 'image-gallery';

    normalised.forEach(img => {
      const thumb = document.createElement('div');
      thumb.className = 'image-thumb';

      if (img.url) {
        const imgEl = document.createElement('img');
        imgEl.src = img.url;
        imgEl.alt = img.filename;
        imgEl.loading = 'lazy';
        thumb.appendChild(imgEl);
      } else {
        const placeholder = document.createElement('div');
        placeholder.style.cssText = 'height:90px;display:flex;align-items:center;justify-content:center;color:#aaa;font-size:24px;';
        placeholder.textContent = '🖼';
        thumb.appendChild(placeholder);
      }

      const name = document.createElement('div');
      name.className = 'image-thumb-name';
      name.textContent = img.filename;
      name.title = img.filename;
      thumb.appendChild(name);

      gallery.appendChild(thumb);
    });

    galleryEl.innerHTML = '';
    galleryEl.appendChild(gallery);
  } catch (err) {
    galleryEl.innerHTML = `<div class="error-msg">Failed to load images: ${escHtml(err.message)}</div>`;
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _setProgress(fillEl, pctEl, pct) {
  fillEl.style.width = `${pct}%`;
  pctEl.textContent = `${pct}%`;
}

function escHtml(str) {
  return String(str ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function showError(el, msg) { el.textContent = msg; el.classList.remove('hidden'); }
function hideEl(el) { el.classList.add('hidden'); el.textContent = ''; }
