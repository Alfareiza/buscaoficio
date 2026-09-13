/** Same-origin call to FastAPI via `/api/backend`. Cookie stays HttpOnly. */
export function backendFetch(path: string, init?: RequestInit): Promise<Response> {
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return fetch(`/api/backend${suffix}`, { ...init, credentials: "same-origin" });
}
