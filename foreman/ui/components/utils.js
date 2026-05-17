/**
 * utils.js — Shared helper functions for the Foreman Test UI.
 */

// ---------------------------------------------------------------------------
// Date formatting
// ---------------------------------------------------------------------------

/**
 * Format an ISO8601 timestamp to a human-readable local string.
 * @param {string|null} iso
 * @returns {string}
 */
export function formatDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch (_) {
    return iso;
  }
}

/**
 * Format a duration in milliseconds to a readable string (e.g. "12.3s").
 * @param {number|null} ms
 * @returns {string}
 */
export function formatDuration(ms) {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ---------------------------------------------------------------------------
// Status formatting
// ---------------------------------------------------------------------------

const STATUS_META = {
  pending:    { label: 'Pending',    cssClass: 'status-pending' },
  processing: { label: 'Processing', cssClass: 'status-processing' },
  completed:  { label: 'Completed',  cssClass: 'status-completed' },
  failed:     { label: 'Failed',     cssClass: 'status-failed' },
  cancelled:  { label: 'Cancelled',  cssClass: 'status-cancelled' },
};

/**
 * Return display label and CSS class for a generation status.
 * @param {string} status
 * @returns {{ label: string, cssClass: string }}
 */
export function formatStatus(status) {
  return STATUS_META[status] || { label: status, cssClass: 'status-unknown' };
}

/**
 * Return true if the generation status is terminal (no more transitions).
 * @param {string} status
 * @returns {boolean}
 */
export function isTerminalStatus(status) {
  return status === 'completed' || status === 'failed' || status === 'cancelled';
}

// ---------------------------------------------------------------------------
// API error parsing
// ---------------------------------------------------------------------------

/**
 * Parse a foreman API error response into a user-friendly string.
 * Handles FastAPI 422 validation errors (detail array) and plain messages.
 * @param {Response} response
 * @param {unknown} body — already-parsed JSON body (or null)
 * @returns {string}
 */
export function parseApiError(response, body) {
  if (!body) return `HTTP ${response.status}: ${response.statusText}`;

  // FastAPI 422 validation error — array of field errors
  if (Array.isArray(body.detail)) {
    return body.detail
      .map(e => {
        const loc = Array.isArray(e.loc) ? e.loc.slice(1).join('.') : '';
        return loc ? `${loc}: ${e.msg}` : e.msg;
      })
      .join('; ');
  }

  // Plain string detail
  if (typeof body.detail === 'string') return body.detail;

  // Generic message field
  if (typeof body.message === 'string') return body.message;

  return `HTTP ${response.status}: ${response.statusText}`;
}

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

/**
 * Create a DOM element with optional attributes and children.
 * @param {string} tag
 * @param {Record<string, string>} [attrs]
 * @param {(string|Node)[]} [children]
 * @returns {HTMLElement}
 */
export function createElement(tag, attrs = {}, children = []) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'className') {
      el.className = v;
    } else if (k.startsWith('on') && typeof v === 'function') {
      el.addEventListener(k.slice(2).toLowerCase(), v);
    } else {
      el.setAttribute(k, v);
    }
  }
  for (const child of children) {
    if (typeof child === 'string') {
      el.appendChild(document.createTextNode(child));
    } else if (child instanceof Node) {
      el.appendChild(child);
    }
  }
  return el;
}

/**
 * Set the inner text of an element, creating it if needed.
 * @param {string} selector
 * @param {string} text
 */
export function setText(selector, text) {
  const el = document.querySelector(selector);
  if (el) el.textContent = text;
}

/**
 * Show or hide an element by toggling the 'hidden' class.
 * @param {HTMLElement|string} elOrSelector
 * @param {boolean} visible
 */
export function setVisible(elOrSelector, visible) {
  const el = typeof elOrSelector === 'string'
    ? document.querySelector(elOrSelector)
    : elOrSelector;
  if (!el) return;
  if (visible) {
    el.classList.remove('hidden');
  } else {
    el.classList.add('hidden');
  }
}

// ---------------------------------------------------------------------------
// Validation helpers
// ---------------------------------------------------------------------------

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/**
 * Return true if the string looks like a valid UUID v1–v5.
 * @param {string} str
 * @returns {boolean}
 */
export function isValidUuid(str) {
  return typeof str === 'string' && UUID_RE.test(str);
}

/**
 * Return true if the ISO8601 timestamp is in the past (i.e. expired).
 * @param {string|null} isoTimestamp
 * @returns {boolean}
 */
export function isExpired(isoTimestamp) {
  if (!isoTimestamp) return true;
  return new Date(isoTimestamp).getTime() <= Date.now();
}

/**
 * Truncate a string to maxLen characters, appending '…' if truncated.
 * @param {string} str
 * @param {number} maxLen
 * @returns {string}
 */
export function truncate(str, maxLen = 60) {
  if (!str) return '';
  return str.length <= maxLen ? str : str.slice(0, maxLen) + '…';
}

/**
 * Format a file size in bytes to a human-readable string.
 * @param {number} bytes
 * @returns {string}
 */
export function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
