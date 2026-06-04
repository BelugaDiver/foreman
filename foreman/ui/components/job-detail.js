/**
 * job-detail.js — Generation job detail + polling component. (US2, US3, US4)
 *
 * Displays all generation fields, polls for status updates until terminal state,
 * and provides action buttons: Cancel, Retry (failed), Fork (completed).
 */

import * as api from '../api.js';
import * as state from '../state.js';
import { removeGenerationFromState } from '../state.js';

import { formatDate, formatDuration, formatStatus, isTerminalStatus, truncate } from './utils.js';
import { normaliseGeneration } from '../app.js';
import { setForkParentId } from './generation-form.js';
import { startPolling, stopPolling } from '../app.js';

export function renderJobDetail(container) {
  if (!container) return;

  const gen = state.getCurrentGeneration();

  if (!gen) {
    container.innerHTML = `
      <div class="panel">
        <div class="empty-state">
          <strong>No generation selected</strong>
          <p>Submit a generation from the Generate tab or pick one from Jobs.</p>
        </div>
      </div>`;
    return;
  }

  _render(container, gen);

  // Start polling if not in terminal state
  if (!isTerminalStatus(gen.status)) {
    startPolling(gen.id);
  }

  // Re-render when generation state updates
  const unsubscribe = _subscribeToGen(gen.id, container);

  // Clean up polling when view changes away
  state.onViewChange(() => {
    stopPolling();
    unsubscribe();
  });
}

function _subscribeToGen(genId, container) {
  let active = true;
  state.onGenerationsChange(() => {
    if (!active) return;
    const updated = state.getGenerationById(genId);
    if (updated) _render(container, updated);
  });
  return () => { active = false; };
}

function _render(container, gen) {
  const { label, cssClass } = formatStatus(gen.status);
  const terminal = isTerminalStatus(gen.status);

  container.innerHTML = `
    <div class="panel">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
        <h2>Generation Detail</h2>
        <span class="badge ${cssClass}">${label}</span>
      </div>

      ${!terminal ? '<div class="loading-row"><span class="spinner"></span> Polling for updates…</div>' : ''}

      <dl class="gen-meta-grid">
        <dt>ID</dt>              <dd><code>${escHtml(gen.id)}</code></dd>
        <dt>Project ID</dt>      <dd><code>${escHtml(gen.projectId)}</code></dd>
        <dt>Status</dt>          <dd><span class="badge ${cssClass}">${label}</span></dd>
        <dt>Prompt</dt>          <dd>${escHtml(gen.prompt)}</dd>
        <dt>Style ID</dt>        <dd>${escHtml(gen.styleId || '—')}</dd>
        <dt>Model</dt>           <dd>${escHtml(gen.modelUsed || '—')}</dd>
        <dt>Processing time</dt> <dd>${formatDuration(gen.processingTimeMs)}</dd>
        <dt>Attempt</dt>         <dd>${gen.attempt ?? 1}</dd>
        <dt>Parent ID</dt>       <dd>${gen.parentId ? `<a href="#" class="parent-link" data-id="${escHtml(gen.parentId)}">${escHtml(truncate(gen.parentId, 36))}</a>` : '—'}</dd>
        <dt>Created</dt>         <dd>${formatDate(gen.createdAt)}</dd>
        <dt>Updated</dt>         <dd>${formatDate(gen.updatedAt)}</dd>
      </dl>

      ${gen.generatedImageDescription ? `
        <div class="gen-description">
          <strong>Description</strong>
          <div class="gen-description-body">${renderMarkdown(gen.generatedImageDescription)}</div>
        </div>` : ''}

      ${gen.inputImageUrl ? `
        <div class="mb-16">
          <strong>Input image:</strong>
          <div class="output-image">
            <img src="${escHtml(gen.inputImageUrl)}" alt="Input image" loading="lazy" />
          </div>
        </div>` : ''}

      ${gen.status === 'completed' && gen.outputImageUrl ? `
        <div class="output-image">
          <strong>Output image:</strong>
          <img src="${escHtml(gen.outputImageUrl)}" alt="Generated output" loading="lazy" />
          <div class="mt-8">
            <a href="${escHtml(gen.outputImageUrl)}" target="_blank" rel="noopener" class="btn btn-secondary btn-sm">Open full size ↗</a>
          </div>
        </div>` : ''}

      ${gen.status === 'failed' && gen.errorMessage ? `
        <div class="error-msg mt-16">Error: ${escHtml(gen.errorMessage)}</div>` : ''}

      <div class="btn-row" style="margin-top:20px;">
        ${(gen.status === 'pending' || gen.status === 'processing') ? `
          <button class="btn-danger btn-sm" id="cancel-btn">Cancel</button>` : ''}
        ${gen.status === 'failed' ? `
          <button class="btn-secondary btn-sm" id="retry-btn">↺ Retry</button>` : ''}
        ${gen.status === 'completed' && gen.outputImageUrl ? `
          <button class="btn-secondary btn-sm" id="fork-btn">⑂ Fork</button>` : ''}
        <button class="btn-danger btn-sm" id="delete-btn">🗑 Delete</button>
        <button class="btn-secondary btn-sm" id="back-jobs-btn">← Back to Jobs</button>
      </div>

      <div id="action-error" class="error-msg hidden mt-8"></div>
    </div>
  `;

  // Parent link
  container.querySelector('.parent-link')?.addEventListener('click', async e => {
    e.preventDefault();
    const parentId = e.currentTarget.dataset.id;
    try {
      const parent = await api.getGeneration(parentId);
      const normalised = normaliseGeneration(parent);
      state.updateGenerationInState(normalised);
      state.setCurrentGeneration(parentId);
      // Re-render with parent
      stopPolling();
      renderJobDetail(container);
    } catch (err) {
      state.addNotification('error', `Could not load parent: ${err.message}`);
    }
  });

  // Cancel
  container.querySelector('#cancel-btn')?.addEventListener('click', async () => {
    const errorEl = container.querySelector('#action-error');
    try {
      const updated = await api.cancelGeneration(gen.id);
      state.updateGenerationInState(normaliseGeneration(updated));
      stopPolling();
      state.addNotification('success', 'Generation cancelled.');
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.classList.remove('hidden');
    }
  });

  // Retry
  container.querySelector('#retry-btn')?.addEventListener('click', async () => {
    const errorEl = container.querySelector('#action-error');
    try {
      const newGen = await api.retryGeneration(gen.id);
      const normalised = normaliseGeneration(newGen);
      state.addGeneration(normalised);
      state.setCurrentGeneration(normalised.id);
      state.addNotification('success', 'Retry created — watching new job.');
      import('../app.js').then(app => {
        stopPolling();
        renderJobDetail(container);
      });
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.classList.remove('hidden');
    }
  });

  // Fork
  container.querySelector('#fork-btn')?.addEventListener('click', () => {
    setForkParentId(gen.id);
    import('../app.js').then(app => app.switchView('job-form'));
  });

  // Delete
  container.querySelector('#delete-btn').addEventListener('click', async () => {
    if (!confirm('Delete this generation? This cannot be undone.')) return;
    const errorEl = container.querySelector('#action-error');
    try {
      await api.deleteGeneration(gen.id);
      removeGenerationFromState(gen.id);
      stopPolling();
      state.addNotification('success', 'Generation deleted.');
      import('../app.js').then(app => app.switchView('job-list'));
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.classList.remove('hidden');
    }
  });

  // Back to jobs
  container.querySelector('#back-jobs-btn').addEventListener('click', () => {
    import('../app.js').then(app => app.switchView('job-list'));
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escHtml(str) {
  return String(str ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** Minimal Markdown → HTML: bold, italic, inline code, bullet lists, paragraphs. */
function renderMarkdown(text) {
  if (!text) return '';
  const lines = text.split('\n');
  const out = [];
  let inList = false;

  for (const raw of lines) {
    const line = raw.trim();
    const isBullet = /^[-*]\s+/.test(line);

    if (isBullet) {
      if (!inList) { out.push('<ul>'); inList = true; }
      out.push(`<li>${_inline(line.replace(/^[-*]\s+/, ''))}</li>`);
    } else {
      if (inList) { out.push('</ul>'); inList = false; }
      if (line === '') {
        out.push('<br>');
      } else {
        out.push(`<p>${_inline(line)}</p>`);
      }
    }
  }
  if (inList) out.push('</ul>');
  return out.join('');
}

function _inline(text) {
  return escHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>');
}
