/**
 * job-list.js — Paginated list of generation jobs for the current project. (US3)
 */

import * as api from '../api.js';
import * as state from '../state.js';
import { formatDate, formatStatus, truncate } from './utils.js';
import { normaliseGeneration } from '../app.js';

const PAGE_SIZE = 20;

export async function renderJobList(container) {
  if (!container) return;

  if (!state.getIsAuthenticated()) {
    container.innerHTML = `<div class="panel"><div class="warning-banner">Please authenticate first.</div></div>`;
    return;
  }

  const project = state.getCurrentProject();

  container.innerHTML = `
    <div class="panel">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
        <h2>Jobs${project ? ` — ${escHtml(project.name)}` : ''}</h2>
        <div class="btn-row" style="margin:0;">
          <button class="btn-primary btn-sm" id="new-gen-btn">+ New Generation</button>
          <button class="btn-secondary btn-sm" id="refresh-btn">↻ Refresh</button>
        </div>
      </div>

      ${!project ? '<div class="warning-banner">No project selected. Go to Projects and select one.</div>' : ''}

      <div id="job-list-content">
        ${project ? '<div class="loading-row"><span class="spinner"></span> Loading…</div>' : ''}
      </div>

      <div class="pagination hidden" id="pagination">
        <button class="btn-secondary btn-sm" id="prev-btn">← Prev</button>
        <span id="page-info"></span>
        <button class="btn-secondary btn-sm" id="next-btn">Next →</button>
      </div>
    </div>
  `;

  container.querySelector('#new-gen-btn').addEventListener('click', () => {
    import('../app.js').then(app => app.switchView('job-form'));
  });

  if (!project) return;

  let currentOffset = 0;

  const load = async (offset) => {
    currentOffset = offset;
    await _loadPage(container, project.id, offset);
  };

  container.querySelector('#refresh-btn').addEventListener('click', () => load(currentOffset));

  container.querySelector('#prev-btn')?.addEventListener('click', () => {
    if (currentOffset >= PAGE_SIZE) load(currentOffset - PAGE_SIZE);
  });

  container.querySelector('#next-btn')?.addEventListener('click', () => {
    load(currentOffset + PAGE_SIZE);
  });

  await load(0);
}

async function _loadPage(container, projectId, offset) {
  const contentEl = container.querySelector('#job-list-content');
  if (!contentEl) return;

  contentEl.innerHTML = '<div class="loading-row"><span class="spinner"></span> Loading…</div>';

  try {
    const generations = await api.listGenerations(projectId, PAGE_SIZE, offset);
    const normalised = generations.map(normaliseGeneration);

    // Merge into state
    const existing = state.getGenerations();
    const existingIds = new Set(existing.map(g => g.id));
    const merged = [...existing.filter(g => g.projectId !== projectId), ...normalised];
    state.setGenerations(merged);

    _renderPage(container, normalised, offset);
  } catch (err) {
    contentEl.innerHTML = `<div class="error-msg">Failed to load jobs: ${escHtml(err.message)}</div>`;
  }
}

function _renderPage(container, generations, offset) {
  const contentEl = container.querySelector('#job-list-content');
  if (!contentEl) return;

  if (generations.length === 0 && offset === 0) {
    contentEl.innerHTML = `
      <div class="empty-state">
        <strong>No jobs yet</strong>
        <p>Submit a generation using the Generate tab.</p>
      </div>`;
    return;
  }

  if (generations.length === 0) {
    contentEl.innerHTML = '<div class="empty-state"><p>No more jobs on this page.</p></div>';
    return;
  }

  const ul = document.createElement('ul');
  ul.className = 'item-list';

  generations.forEach(gen => {
    const { label, cssClass } = formatStatus(gen.status);
    const li = document.createElement('li');
    li.innerHTML = `
      <div class="item-card" data-id="${escHtml(gen.id)}">
        <div>
          <div class="item-card-title">${escHtml(truncate(gen.prompt, 70))}</div>
          <div class="item-card-meta">${formatDate(gen.createdAt)}${gen.modelUsed ? ` · ${escHtml(gen.modelUsed)}` : ''}</div>
          ${gen.generatedImageDescription ? `<div class="item-card-desc">${escHtml(truncate(gen.generatedImageDescription, 100))}</div>` : ''}
        </div>
        <div class="item-card-right">
          <span class="badge ${cssClass}">${label}</span>
          <button class="btn-danger btn-sm delete-gen-btn" data-id="${escHtml(gen.id)}" title="Delete generation" aria-label="Delete generation">🗑</button>
        </div>
      </div>`;
    ul.appendChild(li);

    // Delete button — stop propagation so row click doesn't fire
    li.querySelector('.delete-gen-btn').addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!confirm('Delete this generation? This cannot be undone.')) return;
      try {
        await api.deleteGeneration(gen.id);
        state.removeGenerationFromState(gen.id);
        li.remove();
        state.addNotification('success', 'Generation deleted.');
      } catch (err) {
        state.addNotification('error', `Failed to delete: ${err.message}`);
      }
    });
  });

  contentEl.innerHTML = '';
  contentEl.appendChild(ul);

  // Click row → job detail
  contentEl.querySelectorAll('.item-card').forEach(card => {
    card.addEventListener('click', () => {
      const id = card.dataset.id;
      state.setCurrentGeneration(id);
      import('../app.js').then(app => app.switchView('job-detail'));
    });
  });

  // Show/update pagination
  const paginationEl = container.querySelector('#pagination');
  const prevBtn = container.querySelector('#prev-btn');
  const nextBtn = container.querySelector('#next-btn');
  const pageInfo = container.querySelector('#page-info');

  paginationEl.classList.remove('hidden');
  prevBtn.disabled = offset === 0;
  nextBtn.disabled = generations.length < PAGE_SIZE;
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  pageInfo.textContent = `Page ${page}`;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escHtml(str) {
  return String(str ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
