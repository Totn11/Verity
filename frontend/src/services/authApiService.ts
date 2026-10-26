import { apiRequest } from "../lib/api";

export type AuthenticatedUser = {
  email: string;
  userId: string;
  role: "admin" | "staff" | "lecturer";
  expiresAt: number;
};

async function requestSession(path: string, init?: RequestInit): Promise<AuthenticatedUser> {
  const payload: unknown = await apiRequest(`/api/auth/${path}`, init);
  if (typeof payload !== "object" || payload === null
    || !("authenticated" in payload) || payload.authenticated !== true
    || !("email" in payload) || typeof payload.email !== "string"
    || !("user_id" in payload) || typeof payload.user_id !== "string"
    || !("role" in payload) || (payload.role !== "admin" && payload.role !== "staff" && payload.role !== "lecturer")
    || !("expires_at" in payload) || typeof payload.expires_at !== "number") {
    throw new Error("The authentication service returned an invalid response.");
  }
  return {
    email: payload.email,
    userId: payload.user_id,
    role: payload.role,
    expiresAt: payload.expires_at,
  };
}

export function getCurrentSession(): Promise<AuthenticatedUser> {
  return requestSession("session");
}

export function signIn(email: string, password: string): Promise<AuthenticatedUser> {
  return requestSession("login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function signOut(): Promise<void> {
  await apiRequest<void>("/api/auth/logout", { method: "POST" });
}
