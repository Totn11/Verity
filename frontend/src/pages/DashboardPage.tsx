import { useEffect, useRef, useState } from "react";
import {
  Activity, Battery, CalendarClock, Camera, CameraOff, CircleAlert, CircleHelp, CloudOff,
  GraduationCap, ShieldAlert, Users, UserCheck, UserMinus,
} from "lucide-react";
import PageHeader from "../components/PageHeader";

type DashboardSummary = {
  total_registered_students: number;
  classes_scheduled_today: number;
  active_sessions: number;
  students_present: number | null;
  students_absent: number | null;
  students_unverified: number | null;
  attendance_activity: {
    student_id: string;
    student_name: string;
    student_number: string;
    mark: "present" | "late" | "absent" | "excused";
    method: "manual" | "face_recognition" | "offline_sync";
    marked_at: string;
  }[];
  upcoming_classes: {
    section_id: string;
    course_name: string;
    course_code: string;
    section_code: string;
    starts_at: string | null;
    classroom_label: string | null;
  }[];
  upcoming_sessions: {
    session_id: string;
    class_section_id: string;
    course_name: string;
    course_code: string;
    section_code: string;
    starts_at: string;
  }[];
  recognition_review_available: boolean;
  recognition_failures_pending_review: number | null;
};

function localDate() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function localTime() {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:00`;
}

function formatTime(value: string) {
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime())
    ? "Time unavailable"
    : new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(timestamp);
}

function StatCard({ title, value, note, icon: Icon, tone }: {
  title: string;
  value: number | string;
  note: string;
  icon: typeof Users;
  tone: "teal" | "blue" | "green" | "amber" | "rose";
}) {
  return (
    <article className="verity-stat-card">
      <div className={`verity-stat-icon tone-${tone}`}><Icon size={19} aria-hidden="true" /></div>
      <div><span>{title}</span><strong>{value}</strong><small>{note}</small></div>
    </article>
  );
}

export function CameraQualityCard() {
  const [cameraState, setCameraState] = useState<"stopped" | "starting" | "streaming" | "unavailable" | "denied" | "error">("stopped");
  const [message, setMessage] = useState("");
  const [brightness, setBrightness] = useState<number | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const cameraRequestRef = useRef(0);

  useEffect(() => {
    const stream = streamRef.current;
    const video = videoRef.current;
    if (!stream || !video || cameraState !== "streaming") return;
    video.srcObject = stream;
    void video.play().catch((error: unknown) => {
      setMessage(error instanceof Error ? error.message : "Camera preview could not be started.");
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setCameraState("error");
    });

    const timer = window.setInterval(() => {
      const canvas = canvasRef.current;
      if (!canvas || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      if (!context) return;
      canvas.width = 32;
      canvas.height = 24;
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let totalLuma = 0;
      for (let index = 0; index < pixels.length; index += 4) {
        totalLuma += 0.2126 * pixels[index] + 0.7152 * pixels[index + 1] + 0.0722 * pixels[index + 2];
      }
      setBrightness(Math.round(totalLuma / (pixels.length / 4)));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [cameraState]);

  useEffect(() => () => {
    cameraRequestRef.current += 1;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  async function toggleCamera() {
    if (streamRef.current) {
      cameraRequestRef.current += 1;
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      if (videoRef.current) videoRef.current.srcObject = null;
      setBrightness(null);
      setCameraState("stopped");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraState("unavailable");
      setMessage("This browser does not provide camera access.");
      return;
    }
    setMessage("");
    setCameraState("starting");
    const requestId = ++cameraRequestRef.current;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" }, width: { ideal: 320 }, height: { ideal: 240 } },
      });
      if (requestId !== cameraRequestRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      stream.getVideoTracks()[0]?.addEventListener("ended", () => {
        if (streamRef.current !== stream) return;
        streamRef.current = null;
        setBrightness(null);
        setCameraState("unavailable");
        setMessage("The camera connection ended.");
      }, { once: true });
      setCameraState("streaming");
    } catch (error) {
      if (requestId !== cameraRequestRef.current) return;
      if (error instanceof DOMException && (error.name === "NotAllowedError" || error.name === "PermissionDeniedError")) {
        setCameraState("denied");
        setMessage("Camera permission was denied. Change browser permissions to preview image quality.");
      } else if (error instanceof DOMException && error.name === "NotFoundError") {
        setCameraState("unavailable");
        setMessage("No camera device was found.");
      } else {
        setCameraState("error");
        setMessage(error instanceof Error ? error.message : "Unable to access the camera.");
      }
    }
  }

  const lightLabel = brightness === null
    ? "Not measured"
    : brightness < 45 ? "Low light"
      : brightness > 190 ? "Bright"
        : "Usable ambient light";

  return (
    <section className="verity-panel device-panel" aria-labelledby="camera-status-title">
      <div className="verity-panel-heading"><div><span className="panel-kicker">DEVICE CHECK</span><h2 id="camera-status-title">Camera & image quality</h2></div><Camera size={18} /></div>
      <div className={`camera-preview ${cameraState === "streaming" ? "camera-preview-active" : ""}`}>
        {cameraState === "streaming"
          ? <video ref={videoRef} autoPlay muted playsInline aria-label="Local camera preview" />
          : <div className="camera-preview-empty"><CameraOff size={22} /><span>{cameraState === "starting" ? "Starting camera…" : "Camera preview is off"}</span></div>}
        <canvas ref={canvasRef} className="visually-hidden" aria-hidden="true" />
      </div>
      <div className="device-readout"><span>Camera</span><strong>{cameraState === "streaming" ? "Preview active" : cameraState === "starting" ? "Starting" : cameraState === "stopped" ? "Not started" : "Unavailable"}</strong></div>
      <div className="device-readout"><span>Ambient brightness</span><strong>{lightLabel}{brightness !== null && <small> · {brightness}/255</small>}</strong></div>
      <p className="device-note">Brightness is sampled in this browser only. Frames are not saved or uploaded; no face recognition is running.</p>
      {message && <p className="inline-error" role="status">{message}</p>}
      <button className="button button-secondary" onClick={() => void toggleCamera()} disabled={cameraState === "starting"}>
        {cameraState === "streaming" ? "Stop preview" : "Start camera preview"}
      </button>
    </section>
  );
}

function ConnectivityCard() {
  const [online, setOnline] = useState(navigator.onLine);
  const [battery, setBattery] = useState<string | null>(null);

  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  useEffect(() => {
    let active = true;
    type BatteryInfo = { level: number; charging: boolean; addEventListener: (name: string, callback: () => void) => void };
    const batteryNavigator = navigator as Navigator & { getBattery?: () => Promise<BatteryInfo> };
    if (!batteryNavigator.getBattery) {
      setBattery("Not reported by this device");
      return;
    }
    void batteryNavigator.getBattery().then((info) => {
      const update = () => {
        if (active) setBattery(`${Math.round(info.level * 100)}%${info.charging ? " · charging" : ""}`);
      };
      update();
      info.addEventListener("levelchange", update);
      info.addEventListener("chargingchange", update);
    }).catch(() => {
      if (active) setBattery("Unavailable");
    });
    return () => { active = false; };
  }, []);

  return (
    <section className="verity-panel" aria-labelledby="connectivity-title">
      <div className="verity-panel-heading"><div><span className="panel-kicker">DEVICE & SYNC</span><h2 id="connectivity-title">Connectivity & power</h2></div><Activity size={18} /></div>
      <div className="device-readout"><span>Network</span><strong className={online ? "status-online" : "status-offline"}>{online ? "Online" : "Offline"}</strong></div>
      <div className="device-readout"><span>Local offline storage</span><strong>Not enabled</strong></div>
      <div className="device-readout"><span>Server synchronization</span><strong>Not available</strong></div>
      <p className="device-note">Offline attendance queue and synchronization are not implemented. Do not rely on this device to retain records offline.</p>
      <div className="device-readout"><span><Battery size={15} /> Device battery</span><strong>{battery ?? "Checking…"}</strong></div>
    </section>
  );
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [online, setOnline] = useState(navigator.onLine);

  async function loadSummary(signal?: AbortSignal) {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/v1/dashboard/summary?local_date=${localDate()}&local_time=${localTime()}`, {
        credentials: "include",
        signal,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(body?.detail ?? `Dashboard data could not be loaded (${response.status}).`);
      }
      setSummary(await response.json() as DashboardSummary);
    } catch (loadError) {
      if (loadError instanceof DOMException && loadError.name === "AbortError") return;
      setError(loadError instanceof Error ? loadError.message : "Dashboard data could not be loaded.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    void loadSummary(controller.signal);
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  return (
    <>
      <PageHeader
        eyebrow="CLASSROOM ATTENDANCE"
        title="Attendance dashboard"
        description="A clear view of today's classes, active roll calls, and verified attendance."
        action={<a className="button button-primary" href="/attendance"><UserCheck size={16} /> Start attendance session</a>}
      />
      {!online && <div className="verity-alert" role="status"><CloudOff size={17} /><span><strong>Offline</strong> — live server data is unavailable. Offline attendance sync is not enabled.</span></div>}
      {error && <div className="verity-alert verity-alert-error" role="alert"><CircleAlert size={17} /><span><strong>Could not load attendance data.</strong> {error}</span><button className="button button-secondary" onClick={() => void loadSummary()}>Retry</button></div>}
      {loading && <div className="verity-loading" role="status">Loading current attendance data…</div>}
      {!loading && !error && summary && (
        <>
          <section className="verity-stats-grid" aria-label="Current attendance metrics">
            <StatCard title="Registered students" value={summary.total_registered_students} note="Active student records" icon={Users} tone="blue" />
            <StatCard title="Classes today" value={summary.classes_scheduled_today} note="From configured class schedules" icon={GraduationCap} tone="teal" />
            <StatCard title="Active sessions" value={summary.active_sessions} note="Open attendance sessions" icon={CalendarClock} tone="green" />
            <StatCard title="Present" value={summary.students_present ?? "—"} note={summary.active_sessions ? "Marked present or late in open sessions" : "Open a session to view class attendance"} icon={UserCheck} tone="green" />
            <StatCard title="Marked absent" value={summary.students_absent ?? "—"} note="Explicitly marked absent" icon={UserMinus} tone="rose" />
            <StatCard title="Not yet verified" value={summary.students_unverified ?? "—"} note="Enrolled but no attendance mark in an open session" icon={CircleHelp} tone="amber" />
          </section>
          {summary.total_registered_students === 0 && <div className="verity-empty"><Users size={22} /><strong>No students registered</strong><span>Add students to begin managing classroom attendance.</span><a href="/students" className="button button-primary">Register students</a></div>}
          <section className="verity-dashboard-grid">
            <div className="verity-panel">
              <div className="verity-panel-heading"><div><span className="panel-kicker">RECENT</span><h2>Attendance activity</h2></div><Activity size={18} /></div>
              {summary.attendance_activity.length === 0
                ? <div className="verity-panel-empty">No attendance records yet. Open a session and record attendance to see activity here.</div>
                : <ul className="attendance-activity-list">{summary.attendance_activity.map((item, index) => (
                  <li key={`${item.student_id}-${item.marked_at}-${index}`}>
                    <span className={`activity-mark mark-${item.mark}`}>{item.mark === "present" || item.mark === "late" ? <UserCheck size={16} /> : item.mark === "absent" ? <UserMinus size={16} /> : <CircleHelp size={16} />}</span>
                    <span className="activity-person"><strong>{item.student_name}</strong>                    <small>{item.student_number} · {item.method.replace(/_/g, " ")}</small></span>
                    <span className={`activity-status mark-${item.mark}`}>{item.mark}</span>
                    <time dateTime={item.marked_at}>{formatTime(item.marked_at)}</time>
                  </li>
                ))}</ul>}
            </div>
            <div className="verity-panel">
              <div className="verity-panel-heading"><div><span className="panel-kicker">SCHEDULE</span><h2>Upcoming classes today</h2></div><CalendarClock size={18} /></div>
              {summary.upcoming_classes.length === 0
                ? <div className="verity-panel-empty">No classes are scheduled for today, or class schedule times have not been configured.</div>
                : <ul className="upcoming-class-list">{summary.upcoming_classes.map((item) => (
                  <li key={item.section_id}><span className="class-time">{item.starts_at?.slice(0, 5) ?? "Time TBD"}</span><span><strong>{item.course_code} · {item.course_name}</strong><small>Section {item.section_code}{item.classroom_label ? ` · ${item.classroom_label}` : ""}</small></span></li>
                ))}</ul>}
              <div className="scheduled-session-divider"><span>Scheduled sessions</span></div>
              {summary.upcoming_sessions.length === 0
                ? <div className="verity-panel-empty">No upcoming attendance sessions have been scheduled.</div>
                : <ul className="upcoming-class-list">{summary.upcoming_sessions.map((item) => (
                  <li key={item.session_id}><span className="class-time">{formatTime(item.starts_at)}</span><span><strong>{item.course_code} · {item.course_name}</strong><small>Section {item.section_code} · Scheduled roll call</small></span></li>
                ))}</ul>}
            </div>
          </section>
          <section className="verity-dashboard-grid verity-device-grid">
            <CameraQualityCard />
            <ConnectivityCard />
            <section className="verity-panel" aria-labelledby="review-title">
              <div className="verity-panel-heading"><div><span className="panel-kicker">MANUAL REVIEW</span><h2 id="review-title">Recognition review queue</h2></div><ShieldAlert size={18} /></div>
              {summary.recognition_review_available
                ? <div className="review-queue-count">{summary.recognition_failures_pending_review ?? 0}<span> unresolved matches</span></div>
                : <div className="verity-unavailable"><CircleAlert size={17} /><span>Not connected. Automated face recognition is not enabled; no recognition results or failures are being generated.</span></div>}
              <p className="device-note">Manual attendance entry remains available for lecturers.</p>
            </section>
          </section>
        </>
      )}
    </>
  );
}
