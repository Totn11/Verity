import type {
  AttendanceEvent,
  AttendanceSummary,
  AttendanceWrite,
  Page,
  Person,
  Room,
} from "./api-types";
import type { PersonWrite } from "../data/facilityProvider";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
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
      if (
        typeof payload === "object"
        && payload !== null
        && "detail" in payload
        && typeof payload.detail === "string"
      ) {
        message = payload.detail;
      }
    } catch {
      // Keep the HTTP status message when the response has no JSON body.
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

async function listAll<T>(path: string): Promise<T[]> {
  const items: T[] = [];
  let cursor: string | null = null;
  do {
    const separator = path.includes("?") ? "&" : "?";
    const page: Page<T> = await apiRequest<Page<T>>(
      `${path}${separator}limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
    );
    items.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor);
  return items;
}

export const api = {
  listPeople(): Promise<Person[]> {
    return listAll<Person>("/api/v1/people");
  },
  listAttendance(personId?: string): Promise<AttendanceEvent[]> {
    const query = personId ? `?person_id=${encodeURIComponent(personId)}` : "";
    return listAll<AttendanceEvent>(`/api/v1/attendance${query}`);
  },
  listRooms(): Promise<Room[]> {
    return listAll<Room>("/api/v1/rooms");
  },
  attendanceSummary(from: string, to: string): Promise<AttendanceSummary[]> {
    return listAll<AttendanceSummary>(
      `/api/v1/reports/attendance-summary?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
    );
  },
  async checkIn(input: AttendanceWrite, idempotencyKey?: string): Promise<AttendanceEvent> {
    return apiRequest<AttendanceEvent>("/api/v1/attendance/check-in", {
      method: "POST",
      body: JSON.stringify(input),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
    });
  },
  async checkOut(input: AttendanceWrite, idempotencyKey?: string): Promise<AttendanceEvent> {
    return apiRequest<AttendanceEvent>("/api/v1/attendance/check-out", {
      method: "POST",
      body: JSON.stringify(input),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
    });
  },
  createPerson(input: PersonWrite): Promise<Person> {
    return apiRequest<Person>("/api/v1/people", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  updatePerson(id: string, changes: Partial<PersonWrite>): Promise<Person> {
    return apiRequest<Person>(`/api/v1/people/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    });
  },
};

export type { AttendanceEvent, AttendanceSummary, AttendanceWrite, Page, Person, Room };
