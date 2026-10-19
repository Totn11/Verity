export type RecognitionApiStatus =
  | { status: "checking" }
  | { status: "ready" }
  | { status: "disabled"; reason: string }
  | { status: "unavailable"; reason: string }
  | { status: "offline"; reason: string };

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export async function getRecognitionApiStatus(signal: AbortSignal): Promise<RecognitionApiStatus> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/api/recognition/status`, {
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (error) {
    if (error instanceof TypeError) {
      return { status: "offline", reason: "The backend could not be reached." };
    }
    throw error;
  }

  if (!response.ok) {
    return { status: "unavailable", reason: `The backend returned HTTP ${response.status}.` };
  }

  const payload: unknown = await response.json();
  if (typeof payload !== "object" || payload === null || !("status" in payload)) {
    return { status: "unavailable", reason: "The backend returned an invalid status response." };
  }
  const status = payload.status;
  if (status === "ready") return { status: "ready" };
  if ((status === "disabled" || status === "unavailable") && "reason" in payload && typeof payload.reason === "string") {
    return { status, reason: payload.reason };
  }
  return { status: "unavailable", reason: "The backend returned an invalid status response." };
}

export async function verifyImagePair(probe: Blob, reference: Blob): Promise<{ matched: boolean; score: number }> {
  const form = new FormData();
  form.append("probe", probe, "probe.jpg");
  form.append("reference", reference, "reference.jpg");
  const response = await fetch(`${apiBaseUrl}/api/recognition/verify`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    const payload: unknown = await response.json();
    const detail = typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string"
      ? payload.detail
      : `The verification API returned HTTP ${response.status}.`;
    throw new Error(detail);
  }

  const payload: unknown = await response.json();
  if (typeof payload !== "object" || payload === null || !("matched" in payload) || !("score" in payload)
    || typeof payload.matched !== "boolean" || typeof payload.score !== "number") {
    throw new Error("The verification API returned an invalid result.");
  }
  return { matched: payload.matched, score: payload.score };
}
