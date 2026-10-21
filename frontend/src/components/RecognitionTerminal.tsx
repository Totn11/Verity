import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowDownToLine, ArrowUpFromLine, Camera, CameraOff, Check, CircleAlert, Clock3, Fingerprint, Info, MapPin, RotateCcw, ScanFace, ShieldCheck, UserRoundX, VideoOff, X } from "lucide-react";
import Avatar from "./Avatar";
import PageHeader from "./PageHeader";
import StatusBadge from "./StatusBadge";
import { usePeople } from "../data/PeopleContext";
import type { AttendanceAction, AttendanceRecord, Person } from "../data/models";
import { runMockRecognition, type MockRecognitionResult } from "../services/mockRecognitionService";
import { getRecognitionApiStatus, type RecognitionApiStatus } from "../services/recognitionApiService";
import { useFacilityQueries, useAttendanceMutation } from "../data/useFacilityQueries";

type CameraStatus = "stopped" | "starting" | "streaming" | "permission-denied" | "unavailable" | "error";
type RecognitionState = "idle" | "processing" | "matched" | "no-match" | "error";
const terminalId = "EN-01";
const terminalLocation = "Northstar HQ · East Entrance";
const errorMessage: Record<Exclude<CameraStatus, "stopped" | "starting" | "streaming">, { title: string; detail: string }> = {
  "permission-denied": { title: "Camera permission denied", detail: "Allow camera access in your browser settings, then try again. The camera remains stopped until you start it." },
  unavailable: { title: "Camera unavailable", detail: "No compatible camera was found. Connect a camera and try again, or contact your facility administrator." },
  error: { title: "Could not start camera", detail: "The camera may be in use by another app or blocked by browser policy. Close other apps using it and retry." },
};

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "medium" }).format(new Date(value));
}

function mostRecentAction(records: AttendanceRecord[], personId: string): AttendanceAction | null {
  return [...records].filter((record) => record.personId === personId).sort((a, b) => b.timestamp.localeCompare(a.timestamp))[0]?.action ?? null;
}

export default function RecognitionTerminal() {
  const { terminalEvents, recordRecognitionEvent } = usePeople();
  const facility = useFacilityQueries();
  const people = facility.people.data ?? [];
  const attendanceRecords = facility.attendance.data ?? [];
  const attendanceMutation = useAttendanceMutation();
  const [cameraStatus, setCameraStatus] = useState<CameraStatus>("stopped");
  const [recognitionState, setRecognitionState] = useState<RecognitionState>("idle");
  const [selectedPersonId, setSelectedPersonId] = useState("");
  const [recognitionResult, setRecognitionResult] = useState<MockRecognitionResult | null>(null);
  const [attendanceResult, setAttendanceResult] = useState<{ action: AttendanceAction; timestamp: string; person: Person } | null>(null);
  const [terminalError, setTerminalError] = useState("");
  const [recordError, setRecordError] = useState("");
  const [message, setMessage] = useState("");
  const [apiStatus, setApiStatus] = useState<RecognitionApiStatus>({ status: "checking" });
  const streamRef = useRef<MediaStream | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const matchSequenceRef = useRef(0);
  const cameraRequestRef = useRef(0);
  const statusRequestRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(false);

  const activePeople = useMemo(() => people.filter((person) => person.registrationStatus === "Active"), [people]);
  const recentEvents = facility.isApi
    ? attendanceRecords.slice(0, 6).map((record) => ({
      id: record.id,
      personId: record.personId,
      personName: record.personName,
      initials: record.initials,
      avatar: record.avatar,
      action: record.action,
      timestamp: record.timestamp,
      location: record.room,
      source: record.source,
      terminal: "API",
    }))
    : terminalEvents.slice(0, 6);
  const identifiedPerson = recognitionResult?.status === "match" ? recognitionResult.person : null;
  const latestAction = identifiedPerson ? mostRecentAction(attendanceRecords, identifiedPerson.id) : null;
  const nextAction: AttendanceAction | null = identifiedPerson ? latestAction === "Check-in" ? "Check-out" : latestAction === "Check-out" ? "Check-in" : identifiedPerson.status === "Present" ? "Check-out" : "Check-in" : null;
  const duplicateAction = Boolean(identifiedPerson && attendanceResult?.person.id === identifiedPerson.id);

  const stopCamera = useCallback(() => {
    cameraRequestRef.current += 1;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraStatus("stopped");
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      statusRequestRef.current?.abort();
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    };
  }, []);

  async function refreshApiStatus() {
    statusRequestRef.current?.abort();
    const controller = new AbortController();
    statusRequestRef.current = controller;
    setApiStatus({ status: "checking" });
    try {
      setApiStatus(await getRecognitionApiStatus(controller.signal));
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setApiStatus({
        status: "unavailable",
        reason: error instanceof Error ? error.message : "The verification API returned an unexpected error.",
      });
    }
  }

  useEffect(() => {
    void refreshApiStatus();
    return () => statusRequestRef.current?.abort();
  }, []);

  useEffect(() => {
    if (cameraStatus !== "streaming" || !streamRef.current || !videoRef.current) return;
    const currentStream = streamRef.current;
    videoRef.current.srcObject = currentStream;
    void videoRef.current.play().catch(() => {
      if (streamRef.current !== currentStream) return;
      setTerminalError("Camera preview could not be displayed. Stop the camera and try again.");
      setCameraStatus("error");
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    });
  }, [cameraStatus]);

  async function startCamera() {
    cameraRequestRef.current += 1;
    const requestSequence = cameraRequestRef.current;
    setTerminalError("");
    setRecordError("");
    setMessage("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraStatus("unavailable");
      return;
    }
    setCameraStatus("starting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: "user" } } });
      if (!mountedRef.current || requestSequence !== cameraRequestRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      stream.getVideoTracks()[0]?.addEventListener("ended", () => {
        if (streamRef.current !== stream) return;
        streamRef.current = null;
        setCameraStatus("unavailable");
        setTerminalError("The camera connection ended. Check the device and reconnect it before continuing.");
      }, { once: true });
      setCameraStatus("streaming");
    } catch (error) {
      if (!mountedRef.current || requestSequence !== cameraRequestRef.current) return;
      if (error instanceof DOMException && (error.name === "NotAllowedError" || error.name === "PermissionDeniedError")) {
        setCameraStatus("permission-denied");
      } else if (error instanceof DOMException && (error.name === "NotFoundError" || error.name === "DevicesNotFoundError" || error.name === "OverconstrainedError")) {
        setCameraStatus("unavailable");
      } else {
        setCameraStatus("error");
        setTerminalError(error instanceof Error ? error.message : "The browser could not start the camera.");
      }
    }
  }

  async function simulateRecognition(personId: string | null) {
    if (cameraStatus !== "streaming" || recognitionState === "processing") return;
    matchSequenceRef.current += 1;
    const currentSequence = matchSequenceRef.current;
    setRecognitionState("processing");
    setRecognitionResult(null);
    setAttendanceResult(null);
    setRecordError("");
    setMessage("Mock service is returning a demonstration result. Camera frames are not sent to or inspected by this service.");
    try {
      const result = await runMockRecognition(personId, people);
      if (currentSequence !== matchSequenceRef.current) return;
      const eventTimestamp = new Date().toISOString();
      recordRecognitionEvent({
        id: `${terminalId}-recognition-${Date.now()}`,
        personId: result.status === "match" ? result.person.id : null,
        personName: result.status === "match" ? result.person.name : "Unknown visitor",
        outcome: result.status === "match" ? "success" : "failed",
        timestamp: eventTimestamp,
        source: "mock-terminal",
        location: terminalLocation,
        confidence: result.status === "match" ? `${result.confidence.toFixed(1)}%` : "No match",
        isDemo: true,
      });
      setRecognitionResult(result);
      setRecognitionState(result.status === "match" ? "matched" : "no-match");
      setMessage(result.status === "match"
        ? "Mock candidate returned. This is not authentication or authorization."
        : "No registered person was returned by the mock recognition service.");
    } catch (error) {
      if (currentSequence !== matchSequenceRef.current) return;
      setRecognitionState("error");
      setTerminalError(error instanceof Error ? error.message : "The mock recognition service failed.");
      setMessage("");
    }
  }

  async function recordAttendance() {
    if (!identifiedPerson || !nextAction || duplicateAction) return;
    const timestamp = new Date().toISOString();
    const room = facility.rooms.data?.find((entry) =>
      entry.name.toLowerCase().includes("east entrance")
      || entry.id === "east-entrance",
    );
    try {
      await attendanceMutation.mutateAsync({
        action: nextAction,
        personId: identifiedPerson.id,
        roomId: room?.id,
        timestamp,
        idempotencyKey: `${terminalId}-${identifiedPerson.id}-${Date.now()}`,
      });
    } catch (error) {
      setRecordError(error instanceof Error ? error.message : "Attendance could not be recorded.");
      return;
    }
    setAttendanceResult({ action: nextAction, timestamp, person: identifiedPerson });
    setRecordError("");
  }

  function resetTerminal() {
    matchSequenceRef.current += 1;
    setRecognitionState("idle");
    setRecognitionResult(null);
    setAttendanceResult(null);
    setTerminalError("");
    setRecordError("");
    setMessage("");
  }

  const cameraIsActive = cameraStatus === "streaming";

  return (
    <>
      <PageHeader eyebrow="AUTHORIZED ENTRY · TERMINAL EN-01" title="Recognition terminal" description="Camera preview and check-in station for an authorized facility entrance." action={<div className={`terminal-connection ${cameraIsActive ? "terminal-connection-active" : ""}`}><span />{cameraIsActive ? "Camera connected" : "Camera stopped"}</div>} />
      <div className="demo-banner terminal-demo-banner"><span className="demo-banner-icon"><Fingerprint size={16} /></span><span><strong>Mock recognition mode</strong> — preview is separate from recognition. The mock service does not inspect camera frames. Results are demonstrations only and do not authenticate or authorize anyone.</span></div>
      <div className="terminal-location-strip"><MapPin size={15} /><span><strong>Terminal location</strong> {terminalLocation}</span><span className="terminal-id">ID: {terminalId}</span></div>

      <div className="terminal-layout">
        <section className="panel terminal-camera-panel" aria-label="Camera preview and recognition controls">
          <div className="terminal-panel-heading"><div><h2>Camera preview</h2><p>Camera access begins only after you select Start camera.</p></div><span className={`camera-status-pill camera-status-${cameraStatus}`}><i />{cameraStatus === "streaming" ? "Connected" : cameraStatus === "starting" ? "Connecting…" : cameraStatus === "stopped" ? "Stopped" : "Needs attention"}</span></div>
          <div className={`terminal-preview ${cameraIsActive ? "terminal-preview-active" : ""}`}>
            {cameraIsActive
              ? <video ref={videoRef} autoPlay playsInline muted aria-label="Live camera preview" />
              : <div className="terminal-preview-placeholder"><span className="preview-camera-icon"><VideoOff size={30} /></span><strong>{cameraStatus === "starting" ? "Connecting to camera…" : "Camera is stopped"}</strong><span>Start camera to enable a local preview. No frames are saved or used for mock recognition.</span></div>}
            {cameraIsActive && <span className="camera-live-label"><i /> LIVE PREVIEW · LOCAL ONLY</span>}
            {cameraIsActive && <div className="camera-guide" aria-hidden="true"><span /><span /><span /><span /></div>}
          </div>
          <div className="camera-control-row">
            {cameraStatus === "starting"
              ? <button className="button button-secondary terminal-camera-button" onClick={stopCamera}><X size={16} /> Cancel camera request</button>
              : !cameraIsActive
                ? <button className="button button-primary terminal-camera-button" onClick={startCamera}><Camera size={16} /> Start camera</button>
              : <button className="button button-danger terminal-camera-button" onClick={stopCamera}><CameraOff size={16} /> Stop camera</button>}
            <span className="camera-control-note"><ShieldCheck size={14} /> Browser permission required</span>
          </div>
          {cameraStatus !== "stopped" && cameraStatus !== "starting" && cameraStatus !== "streaming" && <div className="terminal-error" role="alert"><AlertTriangle size={17} /><div><strong>{errorMessage[cameraStatus].title}</strong><span>{terminalError || errorMessage[cameraStatus].detail}</span><button className="text-link" onClick={startCamera}>Try again</button></div></div>}
          {terminalError && cameraStatus === "streaming" && <div className="terminal-error" role="alert"><AlertTriangle size={17} /><div><strong>System error</strong><span>{terminalError}</span></div></div>}
          <div className="terminal-camera-footnote"><Info size={14} /> Camera preview uses browser MediaDevices and only displays the local stream. It does not perform face recognition.</div>
        </section>

        <section className="panel terminal-recognition-panel" aria-label="Recognition result and attendance action">
          <div className="terminal-panel-heading"><div><h2>Recognition result</h2><p>Provided by a clearly labelled mock service</p></div><span className={`recognition-state-pill recognition-state-${recognitionState}`}><i />{recognitionState === "processing" ? "Processing demo" : recognitionState === "matched" ? "Mock candidate" : recognitionState === "no-match" ? "No match" : recognitionState === "error" ? "Error" : "Waiting"}</span></div>
          <div className={`recognition-result-box recognition-box-${recognitionState}`} aria-live="polite">
            {recognitionState === "matched" && identifiedPerson ? <>
              <div className="candidate-topline"><span className="candidate-match-icon"><Check size={17} /></span><span>SIMULATED MATCH CANDIDATE · NOT VERIFIED</span></div>
              <div className="candidate-profile"><Avatar person={identifiedPerson} size="lg" /><div><strong>{identifiedPerson.name}</strong><span>{identifiedPerson.id}</span><small>{identifiedPerson.department} · {identifiedPerson.role}</small></div></div>
              <div className="candidate-notice"><ShieldCheck size={14} /> A real service must verify identity and authorization server-side before granting access.</div>
            </> : recognitionState === "no-match" ? <div className="recognition-empty"><UserRoundX size={25} /><strong>No match returned</strong><span>Do not grant access based on this demo result. Follow your facility’s manual review procedure.</span></div>
              : recognitionState === "processing" ? <div className="recognition-empty"><span className="processing-spinner" /><strong>Waiting for mock response</strong><span>Local camera frames are not submitted to the mock service.</span></div>
                : recognitionState === "error" ? <div className="recognition-empty recognition-error-empty"><CircleAlert size={24} /><strong>Recognition service error</strong><span>{terminalError || "The mock service could not return a result."}</span></div>
                  : <div className="recognition-empty"><span className="recognition-empty-icon"><ScanFace size={25} /></span><strong>Awaiting an explicit demo action</strong><span>Start the camera, then use the mock controls to generate a sample response.</span></div>}
          </div>
          <div className={`model-api-status model-api-status-${apiStatus.status}`} role="status">
            <span className="model-api-status-indicator" />
            <div>
              <strong>Siamese verification API · {apiStatus.status}</strong>
              <span>{apiStatus.status === "ready"
                ? "The notebook model is available for pairwise image comparison only. It does not identify a person or process this camera."
                : apiStatus.status === "checking"
                  ? "Checking whether a model artifact is configured."
                  : apiStatus.status === "disabled"
                    ? apiStatus.reason === "model_artifact_missing"
                      ? "The configured model artifact is missing. Recognition remains demo-only."
                      : "No model artifact is configured. Recognition remains demo-only."
                    : apiStatus.status === "offline"
                      ? "The backend could not be reached. Mock results remain separate and simulated."
                      : `Model verification is unavailable (${apiStatus.reason}). Mock results remain separate and simulated.`}</span>
            </div>
            <button className="text-link" onClick={() => void refreshApiStatus()} disabled={apiStatus.status === "checking"}>Refresh</button>
          </div>
          <div className="mock-service-controls">
            <div className="mock-service-label"><span className="demo-tag">MOCK SERVICE</span><span>Choose test outcome · independent of video</span></div>
            <label className="mock-person-select">Demo person<select value={selectedPersonId} onChange={(event) => setSelectedPersonId(event.target.value)} disabled={!cameraIsActive || recognitionState === "processing"}><option value="">No matching person</option>{activePeople.map((person) => <option key={person.id} value={person.id}>{person.name} · {person.id}</option>)}</select></label>
            <div className="mock-action-buttons"><button className="button button-secondary" disabled={!cameraIsActive || recognitionState === "processing"} onClick={() => void simulateRecognition(selectedPersonId || null)}><Fingerprint size={15} /> Run mock result</button><button className="button button-secondary" disabled={!cameraIsActive || recognitionState === "processing"} onClick={() => void simulateRecognition(null)}><UserRoundX size={15} /> Simulate no match</button></div>
          </div>
          {message && <div className={`terminal-inline-message ${recognitionState === "matched" ? "message-info" : ""}`} role="status"><Info size={14} />{message}</div>}
          {recordError && <div className="terminal-inline-message message-error" role="alert"><CircleAlert size={14} />{recordError}</div>}
          {attendanceResult && <div className="terminal-attendance-success" role="status"><Check size={17} /><div><strong>{attendanceResult.action} recorded {facility.isApi ? "by the API" : "in demo"}</strong><span>{attendanceResult.person.name} · {formatTimestamp(attendanceResult.timestamp)} · {terminalLocation}</span></div></div>}
          <div className="terminal-attendance-action">
            {identifiedPerson && nextAction
              ? <button className="button button-primary" disabled={!cameraIsActive || recognitionState !== "matched" || duplicateAction || attendanceMutation.isPending} onClick={() => void recordAttendance()}>{nextAction === "Check-in" ? <ArrowDownToLine size={16} /> : <ArrowUpFromLine size={16} />}{attendanceMutation.isPending ? "Recording…" : duplicateAction ? `${nextAction} already recorded` : `Record ${facility.isApi ? "" : "demo "}${nextAction.toLowerCase()}`}</button>
              : <button className="button button-primary" disabled><Fingerprint size={16} /> Attendance action unavailable</button>}
            <button className="button button-secondary" onClick={resetTerminal} disabled={recognitionState === "processing"}><RotateCcw size={15} /> Reset</button>
          </div>
          <div className="terminal-auth-note"><ShieldCheck size={14} /><span>Recognition candidates are not authentication or authorization decisions. This page cannot unlock doors.</span></div>
        </section>
      </div>

      <section className="panel terminal-events-panel">
        <div className="terminal-panel-heading"><div><h2>Recent attendance events</h2><p>{facility.isApi ? "Persisted facility API events" : "Current browser session only · not persisted"}</p></div><span className="demo-tag">{facility.isApi ? "API DATA" : "DEMO EVENTS"}</span></div>
        {recentEvents.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>PERSON</th><th>EVENT</th><th>TIMESTAMP</th><th>TERMINAL LOCATION</th><th>SOURCE</th><th>RECORD</th></tr></thead><tbody>{recentEvents.map((event) => <tr key={event.id}><td><span className="person-cell"><Avatar person={{ name: event.personName, initials: event.initials, avatar: event.avatar }} size="sm" /><span><strong>{event.personName}</strong><small>{event.personId}</small></span></span></td><td><StatusBadge tone={event.action === "Check-in" ? "green" : "blue"}>{event.action}</StatusBadge></td><td><span className="table-time"><Clock3 size={13} />{formatTimestamp(event.timestamp)}</span></td><td><span className="table-time"><MapPin size={13} />{event.location}</span></td><td>{facility.isApi ? event.source : `Mock terminal · ${event.terminal}`}</td><td><StatusBadge tone="gray">{facility.isApi ? "Recorded" : "Demo only"}</StatusBadge></td></tr>)}</tbody></table></div>
          : <div className="terminal-history-empty"><Clock3 size={17} /><span>No attendance events are available in this {facility.isApi ? "API" : "demo"} session.</span></div>}
      </section>
      <div className="terminal-footer-note"><ShieldCheck size={14} /> No facial images or biometric templates are stored in browser storage. The camera stream is stopped when this page is closed.</div>
    </>
  );
}
