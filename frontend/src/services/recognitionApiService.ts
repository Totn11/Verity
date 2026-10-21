export type RecognitionApiStatus =
  | { status: "checking" }
  | { status: "ready" }
  | { status: "disabled"; reason: string }
  | { status: "unavailable"; reason: string }
  | { status: "offline"; reason: string };

import { ApiError, apiRequest } from "../lib/api";

export async function getRecognitionApiStatus(signal: AbortSignal): Promise<RecognitionApiStatus> {
  try {
    const payload: unknown = await apiRequest("/api/recognition/status", { signal });
    if (typeof payload !== "object" || payload === null || !("status" in payload)) {
      return { status: "unavailable", reason: "The backend returned an invalid status response." };
    }
    const status = payload.status;
    if (status === "ready") return { status: "ready" };
    if ((status === "disabled" || status === "unavailable") && "reason" in payload && typeof payload.reason === "string") {
      return { status, reason: payload.reason };
    }
    return { status: "unavailable", reason: "The backend returned an invalid status response." };
  } catch (error) {
    if (error instanceof TypeError) {
      return { status: "offline", reason: "The backend could not be reached." };
    }
    if (error instanceof ApiError) {
      return { status: "unavailable", reason: error.message };
    }
    throw error;
  }
}

export async function verifyImagePair(probe: Blob, reference: Blob): Promise<{ matched: boolean; score: number }> {
  const form = new FormData();
  form.append("probe", probe, "probe.jpg");
  form.append("reference", reference, "reference.jpg");
  const payload: unknown = await apiRequest("/api/recognition/verify", {
    method: "POST",
    body: form,
  });
  if (typeof payload !== "object" || payload === null || !("matched" in payload) || !("score" in payload)
    || typeof payload.matched !== "boolean" || typeof payload.score !== "number") {
    throw new Error("The verification API returned an invalid result.");
  }
  return { matched: payload.matched, score: payload.score };
}
