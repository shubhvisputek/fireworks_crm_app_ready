// Thin client for the JSON API. Errors carry the server's message and details.

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.status = status;
    Object.assign(this, details);
  }
}

let onUnauthorized = () => {};
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

async function request(path, options = {}) {
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
