/** Cookie-based local API session. CSRF stays only in memory, never in localStorage. */
const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
let csrfToken = '';

export const apiBase = API_URL;
export function setCsrfToken(value: string) { csrfToken = value; }
export function clearCsrfToken() { csrfToken = ''; }

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const method = (init.method || 'GET').toUpperCase();
  const headers = new Headers(init.headers || {});
  if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS' && csrfToken) {
    headers.set('X-AQUAVERSE-CSRF', csrfToken);
  }
  return fetch(input, { ...init, method, headers, credentials: 'include' });
}
