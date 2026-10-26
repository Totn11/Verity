const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(init.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });

  if (response.status === 401) {
    if (window.location.pathname !== "/login") window.location.assign("/login");
    throw new ApiError("Sign in is required.", 401);
  }

  if (!response.ok) {
    let message = `The API returned HTTP ${response.status}.`;
    try {
      const payload: unknown = await response.json();
      if (typeof payload === "object" && payload !== null && "detail" in payload
        && typeof payload.detail === "string") {
        message = payload.detail;
      }
    } catch {
      // Preserve the status-based message when the response has no JSON body.
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}
