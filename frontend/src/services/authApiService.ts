import { apiRequest } from "../lib/api";

export type AuthenticatedUser = {
  email: string;
};

async function requestSession(path: string, init?: RequestInit): Promise<AuthenticatedUser> {
  const payload: unknown = await apiRequest(`/api/auth/${path}`, init);
  if (init?.method === "POST" && path === "logout") return { email: "" };
  if (typeof payload !== "object" || payload === null
    || !("authenticated" in payload) || payload.authenticated !== true
    || !("email" in payload) || typeof payload.email !== "string") {
    throw new Error("The authentication service returned an invalid response.");
  }
  return { email: payload.email };
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
  await requestSession("logout", { method: "POST" });
}
