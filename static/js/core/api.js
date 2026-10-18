// Thin client for the JSON API. Errors carry the server's message and details.

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.status = status;
    // Copy the server's extra fields (code, validation_errors, ...) but never ones that would replace built-ins.
    for (const [key, value] of Object.entries(details || {})) {
      if (!['__proto__', 'constructor', 'prototype', 'status', 'message', 'stack'].includes(key)) this[key] = value;
    }
  }
}

let onUnauthorized = () => {};
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

// A thin bar at the top of the screen while any request takes longer than a moment.
let active = 0;
let barTimer;
function loading(delta) {
  active += delta;
  clearTimeout(barTimer);
  if (active > 0) barTimer = setTimeout(() => document.body.classList.add('is-loading'), 150);
  else document.body.classList.remove('is-loading');
}

async function request(path, options = {}) {
  loading(1);
  try {
    return await send(path, options);
  } finally {
    loading(-1);
  }
}

async function send(path, options) {
  const response = await fetch(path, { credentials: 'same-origin', ...options });
  let data = {};
  try {
    data = await response.json();
  } catch {
    /* empty or non-JSON body */
  }
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/login') onUnauthorized();
    throw new ApiError(data.error || 'Request failed', response.status, data);
  }
  return data;
}

export const api = {
  get: (path, params) => request(params ? `${path}?${new URLSearchParams(params)}` : path),
  post: (path, body = {}) =>
    request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  upload: (path, formData) => request(path, { method: 'POST', body: formData }),
};
