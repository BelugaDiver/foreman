/**
 * api.js — HTTP client for the Foreman API.
 *
 * All requests include the x-user-id header sourced from state.
 * Error responses throw an Error with a user-friendly message.
 *
 * Usage:
 *   import * as api from './api.js';
 *   const user = await api.createUser('dev@example.com', 'Dev User');
 */

import { getApiUrl, getUser } from './state.js';
import { parseApiError } from './components/utils.js';

// ---------------------------------------------------------------------------
// Base request
// ---------------------------------------------------------------------------

/**
 * Make an authenticated request to the foreman API.
 * @param {string} method
 * @param {string} path — path including leading slash, e.g. '/v1/users/'
 * @param {object|null} [body]
 * @param {{ skipAuth?: boolean }} [opts]
 * @returns {Promise<any>} parsed JSON response
 */
export async function apiRequest(method, path, body = null, opts = {}) {
  const baseUrl = getApiUrl().replace(/\/$/, '');
  const url = `${baseUrl}${path}`;

  const headers = { 'Content-Type': 'application/json' };

  if (!opts.skipAuth) {
    const { id } = getUser();
    if (id) headers['x-user-id'] = id;
  }

  const init = { method, headers };
  if (body !== null) init.body = JSON.stringify(body);

  let response;
  try {
    response = await fetch(url, init);
  } catch (err) {
    throw new Error(`Network error — could not reach foreman at ${baseUrl}. Is it running?`);
  }

  // 204 No Content
  if (response.status === 204) return null;

  let parsed = null;
  try {
    parsed = await response.json();
  } catch (_) { /* body may be empty */ }

  if (!response.ok) {
    throw new Error(parseApiError(response, parsed));
  }

  return parsed;
}

// ---------------------------------------------------------------------------
// Health / discovery
// ---------------------------------------------------------------------------

/** Check if foreman API is reachable. Returns health object or throws. */
export async function checkHealth() {
  return apiRequest('GET', '/health', null, { skipAuth: true });
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

/** Create a new test user. Does not require x-user-id. */
export async function createUser(email, fullName) {
  return apiRequest('POST', '/v1/users/', { email, full_name: fullName }, { skipAuth: true });
}

/** Get the currently authenticated user. */
export async function getUser_() {
  return apiRequest('GET', '/v1/users/me');
}

/** Update the current user. */
export async function updateUser(patch) {
  return apiRequest('PATCH', '/v1/users/me', patch);
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

/** List all projects for the current user. */
export async function listProjects(limit = 20, offset = 0) {
  return apiRequest('GET', `/v1/projects/?limit=${limit}&offset=${offset}`);
}

/** Create a new project. */
export async function createProject(name, originalImageUrl = null) {
  const body = { name };
  if (originalImageUrl) body.original_image_url = originalImageUrl;
  return apiRequest('POST', '/v1/projects/', body);
}

/** Get a single project by ID. */
export async function getProject(projectId) {
  return apiRequest('GET', `/v1/projects/${projectId}`);
}

/** Update project fields (e.g. set original_image_url after upload). */
export async function updateProject(projectId, patch) {
  return apiRequest('PATCH', `/v1/projects/${projectId}`, patch);
}

// ---------------------------------------------------------------------------
// Images
// ---------------------------------------------------------------------------

/**
 * Request a presigned upload URL from foreman.
 * @returns {{ upload_url, image_id, file_key, expires_at }}
 */
export async function createUploadIntent(projectId, filename, contentType, sizeBytes) {
  return apiRequest('POST', `/v1/projects/${projectId}/images`, {
    filename,
    content_type: contentType,
    size_bytes: sizeBytes,
  });
}

/** Get image metadata + a fresh signed download URL. */
export async function getImage(imageId) {
  return apiRequest('GET', `/v1/images/${imageId}`);
}

/** List all images for a project. */
export async function listImages(projectId, limit = 20, offset = 0) {
  return apiRequest('GET', `/v1/projects/${projectId}/images?limit=${limit}&offset=${offset}`);
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

/** List all available design styles. */
export async function listStyles(limit = 100) {
  return apiRequest('GET', `/v1/styles/?limit=${limit}&offset=0`);
}

// ---------------------------------------------------------------------------
// Generations
// ---------------------------------------------------------------------------

/**
 * Create a new generation job.
 * @param {string} projectId
 * @param {{ prompt: string, style_id?: string, parent_id?: string }} payload
 */
export async function createGeneration(projectId, payload) {
  return apiRequest('POST', `/v1/projects/${projectId}/generations`, payload);
}

/** Get a single generation by ID. */
export async function getGeneration(generationId) {
  return apiRequest('GET', `/v1/generations/${generationId}`);
}

/** List generations for a project. */
export async function listGenerations(projectId, limit = 20, offset = 0) {
  return apiRequest('GET', `/v1/projects/${projectId}/generations?limit=${limit}&offset=${offset}`);
}

/** Cancel a pending or processing generation. */
export async function cancelGeneration(generationId) {
  return apiRequest('POST', `/v1/generations/${generationId}/cancel`);
}

/** Retry a failed generation with original inputs. */
export async function retryGeneration(generationId) {
  return apiRequest('POST', `/v1/generations/${generationId}/retry`);
}

/** Fork a completed generation to create a child using its output. */
export async function forkGeneration(generationId, payload = {}) {
  return apiRequest('POST', `/v1/generations/${generationId}/fork`, payload);
}
