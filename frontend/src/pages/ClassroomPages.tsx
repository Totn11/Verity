import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { ArrowRight, Download, Fingerprint, Plus, RefreshCw, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import PageHeader from "../components/PageHeader";
import { useAuth } from "../data/AuthContext";
import { apiRequest } from "../lib/api";
import { CameraQualityCard } from "./DashboardPage";

type Student = { id: string; student_number: string; first_name: string; last_name: string; email: string | null; is_active: boolean };
type Course = { id: string; code: string; name: string; description: string | null };
type Semester = { id: string; name: string; starts_on: string; ends_on: string };
type Lecturer = { id: string; display_name: string; email: string };
type Section = { id: string; course_id: string; semester_id: string; section_code: string; classroom_label: string | null; schedule_weekday: number | null; schedule_starts_at: string | null; schedule_ends_at: string | null };
type AttendanceSession = { id: string; class_section_id: string; started_at: string; scheduled_for: string | null; ended_at: string | null; status: "scheduled" | "open" | "closed"; confidence_threshold: string };
type AttendanceRecord = { id: string; session_id: string; student_id: string; mark: "present" | "late" | "absent" | "excused"; method: string; marked_at: string };
type RecognitionStatus = { inference_ready: boolean; enrollment_ready: boolean; validated_thresholds: boolean; automatic_attendance_enabled: boolean; reason: string | null };
type RecognitionResult = {
  outcome: string;
  candidate_student_id: string | null;
  similarity: number | null;
  margin: number | null;
  quality: Record<string, number | string[]>;
  model_version: string | null;
  validation_id: string | null;
  attendance_recorded: boolean;
  already_recorded: boolean;
  review_required: boolean;
};

function localDateTimeInput() {
  const value = new Date(Date.now() + 60_000);
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`;
}

function useResource<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  useEffect(() => {
    if (!url) {
      setLoading(false);
      setData(null);
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void apiRequest<T>(url, { signal: controller.signal }).then(setData).catch((reason: unknown) => {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setError(reason instanceof Error ? reason.message : "Could not load this data.");
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [url, refreshKey]);
  return { data, loading, error, reload: () => setRefreshKey((value) => value + 1) };
}

function ResourceState({ loading, error, empty, children }: {
  loading: boolean;
  error: string | null;
  empty: boolean;
  children: ReactNode;
}) {
  if (loading) return <div className="verity-loading" role="status">Loading application data…</div>;
  if (error) return <div className="verity-alert verity-alert-error" role="alert">{error}</div>;
  if (empty) return <div className="verity-empty">No records yet. Add data to get started.</div>;
  return <>{children}</>;
}

function useMutationError() {
  const [error, setError] = useState<string | null>(null);
  async function run<T>(operation: () => Promise<T>) {
    setError(null);
    try {
      return await operation();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The request could not be completed.");
      throw reason;
    }
  }
  return { error, run };
}

export function LoginPage() {
  const { status, initialError, signIn } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  if (status === "authenticated") return <div className="auth-loading">You are signed in. <Link to="/">Continue to dashboard</Link></div>;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const data = new FormData(event.currentTarget);
    try {
      await signIn(String(data.get("email") ?? ""), String(data.get("password") ?? ""));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to sign in.");
    } finally {
      setSubmitting(false);
    }
  }
  return (
    <main className="login-screen">
      <div className="login-brand"><span className="brand-mark"><Fingerprint size={21} /></span><span className="brand-name">verity<span>.</span></span></div>
      <section className="login-card"><span className="login-kicker">CLASSROOM ATTENDANCE</span><h1>Sign in to Verity</h1><p>Manage student records, classes, and attendance sessions.</p>
        {(error || initialError) && <div className="login-error" role="alert">{error ?? initialError}</div>}
        <form onSubmit={submit}><label>Email address<input name="email" type="email" autoComplete="username" required /></label><label>Password<input name="password" type="password" autoComplete="current-password" required /></label><button className="button button-primary login-submit" type="submit" disabled={submitting || status === "checking"}>{submitting ? "Signing in…" : "Sign in"} <ArrowRight size={16} /></button></form>
        <div className="login-security"><ShieldCheck size={15} /> Protected session</div>
      </section>
    </main>
  );
}

export function StudentsPage() {
  const { user } = useAuth();
  const { data: students, loading, error, reload } = useResource<Student[]>("/api/v1/students");
  const { error: mutationError, run } = useMutationError();
  const [query, setQuery] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const visible = (students ?? []).filter((student) =>
    `${student.student_number} ${student.first_name} ${student.last_name}`.toLowerCase().includes(query.toLowerCase()),
  );
  async function createStudent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    try {
      await run(() => apiRequest("/api/v1/students", {
        method: "POST",
        body: JSON.stringify({
          student_number: form.get("student_number"),
          first_name: form.get("first_name"),
          last_name: form.get("last_name"),
          email: form.get("email") || null,
        }),
      }));
      setFormOpen(false);
      reload();
    } catch { /* Error is presented in the page. */ } finally { setSaving(false); }
  }
  return (
    <>
      <PageHeader eyebrow="STUDENT RECORDS" title="Students" description="Register and manage student records used by classroom attendance." action={user?.role === "admin" ? <button className="button button-primary" onClick={() => setFormOpen((value) => !value)}><Plus size={16} /> Register student</button> : undefined} />
      {mutationError && <div className="verity-alert verity-alert-error" role="alert">{mutationError}</div>}
      {formOpen && user?.role === "admin" && <form className="verity-panel academic-form" onSubmit={(event) => void createStudent(event)}><h2>Register student</h2><label>Student number<input name="student_number" required maxLength={64} /></label><label>First name<input name="first_name" required maxLength={120} /></label><label>Last name<input name="last_name" required maxLength={120} /></label><label>Email (optional)<input name="email" type="email" /></label><button className="button button-primary" disabled={saving}>{saving ? "Saving…" : "Save student"}</button></form>}
      <div className="verity-panel">
        <div className="academic-toolbar"><label className="search-field"><span aria-hidden="true">⌕</span><input aria-label="Filter students" placeholder="Search student number or name" value={query} onChange={(event) => setQuery(event.target.value)} /></label><button className="button button-secondary" onClick={reload}><RefreshCw size={15} /> Refresh</button></div>
        <ResourceState loading={loading} error={error} empty={Boolean(students && visible.length === 0)}>
          <div className="academic-table-wrap"><table className="academic-table"><thead><tr><th>Student number</th><th>Student</th><th>Email</th><th>Status</th></tr></thead><tbody>{visible.map((student) => <tr key={student.id}><td>{student.student_number}</td><td>{student.first_name} {student.last_name}</td><td>{student.email ?? "—"}</td><td>{student.is_active ? "Active" : "Inactive"}</td></tr>)}</tbody></table></div>
        </ResourceState>
      </div>
    </>
  );
}

export function CoursesPage() {
  const courses = useResource<Course[]>("/api/v1/courses");
  const semesters = useResource<Semester[]>("/api/v1/semesters");
  const sections = useResource<Section[]>("/api/v1/class-sections");
  const students = useResource<Student[]>("/api/v1/students");
  const { user } = useAuth();
  const lecturers = useResource<Lecturer[]>(user?.role === "admin" ? "/api/v1/lecturers" : "");
  const { error: mutationError, run } = useMutationError();
  const [formType, setFormType] = useState<"course" | "semester" | "section" | "enrollment" | null>(null);
  const [saving, setSaving] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!formType) return;
    const form = new FormData(event.currentTarget);
    let path = "";
    let payload: Record<string, unknown> = {};
    if (formType === "course") {
      path = "/api/v1/courses";
      payload = { code: form.get("code"), name: form.get("name"), description: form.get("description") || null };
    } else if (formType === "semester") {
      path = "/api/v1/semesters";
      payload = { name: form.get("name"), starts_on: form.get("starts_on"), ends_on: form.get("ends_on") };
    } else if (formType === "section") {
      path = "/api/v1/class-sections";
      payload = {
        course_id: form.get("course_id"), semester_id: form.get("semester_id"),
        lecturer_user_id: form.get("lecturer_user_id") || null,
        section_code: form.get("section_code"), classroom_label: form.get("classroom_label") || null,
        schedule_weekday: form.get("schedule_weekday") === "" ? null : Number(form.get("schedule_weekday")),
        schedule_starts_at: form.get("schedule_starts_at") || null,
        schedule_ends_at: form.get("schedule_ends_at") || null,
      };
    } else {
      const sectionId = String(form.get("class_section_id") ?? "");
      path = `/api/v1/class-sections/${sectionId}/enrollments`;
      payload = { student_id: form.get("student_id") };
    }
    setSaving(true);
    try {
      await run(() => apiRequest(path, { method: "POST", body: JSON.stringify(payload) }));
      setFormType(null);
      courses.reload();
      semesters.reload();
      sections.reload();
    } catch { /* Error is presented in the page. */ } finally { setSaving(false); }
  }
  const courseName = new Map((courses.data ?? []).map((course) => [course.id, `${course.code} · ${course.name}`]));
  const semesterName = new Map((semesters.data ?? []).map((semester) => [semester.id, semester.name]));
  const busy = courses.loading || semesters.loading || sections.loading || students.loading || lecturers.loading;
  const loadError = courses.error ?? semesters.error ?? sections.error ?? students.error ?? lecturers.error;
  return (
    <>
      <PageHeader eyebrow="ACADEMIC SETUP" title="Courses and classes" description="Organize courses, academic terms, class sections, and local weekly schedules." action={user?.role === "admin" ? <div className="academic-actions"><button className="button button-secondary" onClick={() => setFormType("semester")}>Add semester</button><button className="button button-secondary" onClick={() => setFormType("course")}>Add course</button><button className="button button-secondary" onClick={() => setFormType("enrollment")}>Enroll student</button><button className="button button-primary" onClick={() => setFormType("section")}><Plus size={16} /> Add class</button></div> : undefined} />
      {mutationError && <div className="verity-alert verity-alert-error" role="alert">{mutationError}</div>}
      {formType && user?.role === "admin" && <form className="verity-panel academic-form" onSubmit={(event) => void submit(event)}><h2>{formType === "course" ? "New course" : formType === "semester" ? "New semester" : formType === "section" ? "New class section" : "Enroll student"}</h2>
        {formType === "course" && <><label>Course code<input name="code" required /></label><label>Course name<input name="name" required /></label><label>Description<input name="description" /></label></>}
        {formType === "semester" && <><label>Semester name<input name="name" required /></label><label>Starts on<input name="starts_on" type="date" required /></label><label>Ends on<input name="ends_on" type="date" required /></label></>}
        {formType === "section" && <><label>Course<select name="course_id" required><option value="">Select course</option>{(courses.data ?? []).map((course) => <option key={course.id} value={course.id}>{course.code} · {course.name}</option>)}</select></label><label>Semester<select name="semester_id" required><option value="">Select semester</option>{(semesters.data ?? []).map((semester) => <option key={semester.id} value={semester.id}>{semester.name}</option>)}</select></label><label>Lecturer<select name="lecturer_user_id" defaultValue=""><option value="">Unassigned</option>{(lecturers.data ?? []).map((lecturer) => <option key={lecturer.id} value={lecturer.id}>{lecturer.display_name} · {lecturer.email}</option>)}</select></label><label>Section code<input name="section_code" required /></label><label>Classroom label (optional)<input name="classroom_label" /></label><label>Day of week<select name="schedule_weekday" defaultValue=""><option value="">Not scheduled</option><option value="0">Monday</option><option value="1">Tuesday</option><option value="2">Wednesday</option><option value="3">Thursday</option><option value="4">Friday</option><option value="5">Saturday</option><option value="6">Sunday</option></select></label><label>Start time<input name="schedule_starts_at" type="time" /></label><label>End time<input name="schedule_ends_at" type="time" /></label></>}
        {formType === "enrollment" && <><label>Class section<select name="class_section_id" required><option value="">Select class</option>{(sections.data ?? []).map((section) => <option key={section.id} value={section.id}>{courseName.get(section.course_id) ?? "Course"} · {section.section_code}</option>)}</select></label><label>Student<select name="student_id" required><option value="">Select student</option>{(students.data ?? []).map((student) => <option key={student.id} value={student.id}>{student.student_number} · {student.first_name} {student.last_name}</option>)}</select></label></>}
        <button className="button button-primary" disabled={saving}>{saving ? "Saving…" : "Save"}</button><button className="button button-secondary" type="button" onClick={() => setFormType(null)}>Cancel</button>
      </form>}
      <ResourceState loading={busy} error={loadError} empty={Boolean(courses.data && sections.data && courses.data.length === 0 && sections.data.length === 0)}>
        <div className="academic-course-grid">{(sections.data ?? []).map((section) => <article className="verity-panel course-card" key={section.id}><span className="panel-kicker">{courseName.get(section.course_id) ?? "Course"}</span><h2>Section {section.section_code}</h2><p>{semesterName.get(section.semester_id) ?? "Semester"}{section.classroom_label ? ` · ${section.classroom_label}` : ""}</p><small>{section.schedule_weekday === null ? "Weekly schedule not configured" : `${["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][section.schedule_weekday]} · ${section.schedule_starts_at?.slice(0, 5) ?? "Time TBD"}–${section.schedule_ends_at?.slice(0, 5) ?? "Time TBD"}`}</small></article>)}</div>
      </ResourceState>
      {!busy && !loadError && sections.data?.length === 0 && courses.data?.length ? <div className="verity-empty">Courses are configured, but no class sections are assigned yet.</div> : null}
    </>
  );
}

export function AttendanceSessionsPage() {
  const sections = useResource<Section[]>("/api/v1/class-sections");
  const students = useResource<Student[]>("/api/v1/students");
  const sessions = useResource<AttendanceSession[]>("/api/v1/attendance-sessions");
  const { error: mutationError, run } = useMutationError();
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [selectedStudentId, setSelectedStudentId] = useState("");
  const [mark, setMark] = useState<AttendanceRecord["mark"]>("present");
  const [saving, setSaving] = useState(false);
  const records = useResource<AttendanceRecord[]>(selectedSessionId ? `/api/v1/attendance-sessions/${selectedSessionId}/records` : "/api/v1/attendance-sessions");
  useEffect(() => {
    if (!selectedSessionId) {
      const active = sessions.data?.find((session) => session.status === "open");
      if (active) setSelectedSessionId(active.id);
    }
  }, [sessions.data, selectedSessionId]);
  async function createSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const sectionId = new FormData(event.currentTarget).get("section_id");
    if (!sectionId) return;
    setSaving(true);
    try {
      await run(() => apiRequest(`/api/v1/class-sections/${sectionId}/attendance-sessions`, {
        method: "POST",
        body: JSON.stringify({ confidence_threshold: "0.800" }),
      }));
      sessions.reload();
    } catch { /* Error is presented in the page. */ } finally { setSaving(false); }
  }
  async function scheduleSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const sectionId = String(form.get("section_id") ?? "");
    const scheduledFor = String(form.get("scheduled_for") ?? "");
    if (!sectionId || !scheduledFor) return;
    setSaving(true);
    try {
      await run(() => apiRequest(`/api/v1/class-sections/${sectionId}/attendance-sessions`, {
        method: "POST",
        body: JSON.stringify({
          status: "scheduled",
          scheduled_for: new Date(scheduledFor).toISOString(),
          confidence_threshold: "0.800",
        }),
      }));
      sessions.reload();
    } catch { /* Error is presented in the page. */ } finally { setSaving(false); }
  }
  async function recordStudent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedSessionId || !selectedStudentId) return;
    setSaving(true);
    try {
      await run(() => apiRequest(`/api/v1/attendance-sessions/${selectedSessionId}/records`, {
        method: "POST",
        body: JSON.stringify({ student_id: selectedStudentId, mark, method: "manual", source_event_id: crypto.randomUUID() }),
      }));
      records.reload();
      sessions.reload();
    } catch { /* Error is presented in the page. */ } finally { setSaving(false); }
  }
  async function closeSession() {
    if (!selectedSessionId) return;
    setSaving(true);
    try {
      await run(() => apiRequest(`/api/v1/attendance-sessions/${selectedSessionId}/close`, { method: "POST" }));
      sessions.reload();
    } catch { /* Error is presented in the page. */ } finally { setSaving(false); }
  }
  async function startScheduledSession(id: string) {
    setSaving(true);
    try {
      await run(() => apiRequest(`/api/v1/attendance-sessions/${id}/start`, { method: "POST" }));
      sessions.reload();
    } catch { /* Error is presented in the page. */ } finally { setSaving(false); }
  }
  const session = sessions.data?.find((item) => item.id === selectedSessionId);
  const sectionLabel = (id: string) => {
    const section = sections.data?.find((item) => item.id === id);
    return section ? `Section ${section.section_code}` : id;
  };
  return (
    <>
      <PageHeader eyebrow="CLASS ROLL CALL" title="Attendance sessions" description="Open a class session, mark attendance manually, and review the roster. No camera recognition is used." />
      {mutationError && <div className="verity-alert verity-alert-error" role="alert">{mutationError}</div>}
      <div className="verity-dashboard-grid">
        <section className="verity-panel"><div className="verity-panel-heading"><div><span className="panel-kicker">START</span><h2>Begin an attendance session</h2></div></div>
          <form className="academic-inline-form" onSubmit={(event) => void createSession(event)}><label>Class section<select name="section_id" required defaultValue=""><option value="">Select a class</option>{(sections.data ?? []).map((item) => <option key={item.id} value={item.id}>{sectionLabel(item.id)}</option>)}</select></label><button className="button button-primary" disabled={saving || !sections.data?.length}>Start now</button></form>
          <div className="scheduled-session-divider"><span>Schedule for later</span></div>
          <form className="academic-inline-form" onSubmit={(event) => void scheduleSession(event)}><label>Class section<select name="section_id" required defaultValue=""><option value="">Select a class</option>{(sections.data ?? []).map((item) => <option key={item.id} value={item.id}>{sectionLabel(item.id)}</option>)}</select></label><label>Start date and time<input name="scheduled_for" type="datetime-local" min={localDateTimeInput()} required /></label><button className="button button-secondary" disabled={saving || !sections.data?.length}>Schedule</button></form>
        </section>
        <section className="verity-panel"><div className="verity-panel-heading"><div><span className="panel-kicker">MANUAL ROLL CALL</span><h2>Record attendance</h2></div></div>
          <form className="academic-inline-form" onSubmit={(event) => void recordStudent(event)}><label>Session<select value={selectedSessionId} onChange={(event) => setSelectedSessionId(event.target.value)}><option value="">Select active session</option>{(sessions.data ?? []).filter((item) => item.status === "open").map((item) => <option key={item.id} value={item.id}>{sectionLabel(item.class_section_id)} · {new Date(item.started_at).toLocaleString()}</option>)}</select></label><label>Student<select value={selectedStudentId} onChange={(event) => setSelectedStudentId(event.target.value)}><option value="">Select student</option>{(students.data ?? []).map((item) => <option key={item.id} value={item.id}>{item.student_number} · {item.first_name} {item.last_name}</option>)}</select></label><label>Mark<select value={mark} onChange={(event) => setMark(event.target.value as AttendanceRecord["mark"])}><option value="present">Present</option><option value="late">Late</option><option value="absent">Absent</option><option value="excused">Excused</option></select></label><button className="button button-primary" disabled={saving || !session || !selectedStudentId}>Record mark</button></form>
          {session?.status === "open" && <button className="button button-secondary" onClick={() => void closeSession()} disabled={saving}>Close session</button>}
        </section>
      </div>
      <section className="verity-panel">
        <div className="verity-panel-heading"><div><span className="panel-kicker">SESSION HISTORY</span><h2>Attendance records</h2></div><Link className="button button-secondary" to="/records">All records <ArrowRight size={15} /></Link></div>
        <ResourceState loading={sessions.loading || records.loading} error={sessions.error ?? records.error} empty={Boolean(sessions.data && sessions.data.length === 0)}>
          <div className="academic-table-wrap"><table className="academic-table"><thead><tr><th>Class</th><th>Session time</th><th>Status</th><th>Marks</th><th>Action</th></tr></thead><tbody>{(sessions.data ?? []).map((item) => <tr key={item.id}><td><button className="text-button" onClick={() => setSelectedSessionId(item.id)}>{sectionLabel(item.class_section_id)}</button></td><td>{item.scheduled_for ? new Date(item.scheduled_for).toLocaleString() : new Date(item.started_at).toLocaleString()}</td><td>{item.status}</td><td>{selectedSessionId === item.id ? records.data?.length ?? "—" : "Select to view"}</td><td>{item.status === "scheduled" && <button className="button button-secondary" disabled={saving} onClick={() => void startScheduledSession(item.id)}>Start now</button>}</td></tr>)}</tbody></table></div>
        </ResourceState>
      </section>
    </>
  );
}

export function RecognitionPage() {
  const sessions = useResource<AttendanceSession[]>("/api/v1/attendance-sessions");
  const students = useResource<Student[]>("/api/v1/students");
  const [sessionId, setSessionId] = useState("");
  const [result, setResult] = useState<RecognitionResult | null>(null);
  const [saving, setSaving] = useState(false);
  const { error, run } = useMutationError();
  const student = students.data?.find((item) => item.id === result?.candidate_student_id);
  async function recognize(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!sessionId) return;
    const form = new FormData(event.currentTarget);
    const image = form.get("image");
    if (!(image instanceof File) || image.size === 0) return;
    const body = new FormData();
    body.append("image", image);
    setSaving(true);
    setResult(null);
    try {
      const response = await run(() => apiRequest<RecognitionResult>(`/api/v1/attendance-sessions/${sessionId}/recognize`, { method: "POST", body }));
      setResult(response);
    } catch { /* Error is presented above the form. */ } finally { setSaving(false); }
  }
  async function confirmCandidate() {
    if (!sessionId || !result?.candidate_student_id) return;
    setSaving(true);
    try {
      await run(() => apiRequest(`/api/v1/attendance-sessions/${sessionId}/records`, {
        method: "POST",
        body: JSON.stringify({
          student_id: result.candidate_student_id,
          mark: "present",
          method: "manual",
          source_event_id: crypto.randomUUID(),
        }),
      }));
      setResult({ ...result, attendance_recorded: true, review_required: false });
    } catch { /* Error is presented above the form. */ } finally { setSaving(false); }
  }
  return (
    <>
      <PageHeader eyebrow="RECOGNITION" title="Live recognition" description="Run local YuNet and SFace inference, then verify any suggested identity before attendance is recorded." />
      <div className="verity-alert"><Fingerprint size={18} /><span>Images are processed in memory and not retained. Automatic attendance is disabled unless a model-hash-matched validation manifest is explicitly approved. Without calibrated thresholds, every result is uncertain.</span></div>
      {error && <div className="verity-alert verity-alert-error" role="alert">{error}</div>}
      <section className="verity-panel">
        <div className="verity-panel-heading"><div><span className="panel-kicker">SINGLE-FACE CHECK</span><h2>Review a student image</h2></div></div>
        <form className="academic-inline-form" onSubmit={(event) => void recognize(event)}>
          <label>Open attendance session<select value={sessionId} onChange={(event) => { setSessionId(event.target.value); setResult(null); }} required><option value="">Select an open session</option>{(sessions.data ?? []).filter((item) => item.status === "open").map((item) => <option key={item.id} value={item.id}>{item.id} · {new Date(item.started_at).toLocaleString()}</option>)}</select></label>
          <label>Image file<input name="image" type="file" accept="image/jpeg,image/png,image/webp" required /></label>
          <button className="button button-primary" disabled={saving || !sessionId || !sessions.data?.some((item) => item.id === sessionId && item.status === "open")}>{saving ? "Processing…" : "Analyze face"}</button>
        </form>
        <p className="device-note">Use one consenting student at a time. Low brightness, poor contrast, blur, or a small face causes rejection. A match suggestion never bypasses manual confirmation unless an approved validation manifest and explicit deployment flag are both present.</p>
        {result && <div className="recognition-result" role="status">
          <strong>Outcome: {result.outcome.replace(/_/g, " ")}</strong>
          {result.candidate_student_id && <p>Suggested student: {student ? `${student.student_number} · ${student.first_name} ${student.last_name}` : result.candidate_student_id}</p>}
          {result.similarity !== null && <p>Similarity: {result.similarity.toFixed(4)} · margin: {result.margin?.toFixed(4) ?? "—"}</p>}
          <p>Quality warnings: {Array.isArray(result.quality.warnings) && result.quality.warnings.length ? result.quality.warnings.join(", ") : "none"}</p>
          {result.validation_id && <p>Threshold validation: {result.validation_id}</p>}
          {result.attendance_recorded && <p>Attendance recorded after explicit manual confirmation.</p>}
          {result.already_recorded && <p>This student already has a mark for the selected session.</p>}
          {result.candidate_student_id && result.review_required && <button className="button button-primary" disabled={saving} onClick={() => void confirmCandidate()}>Verify identity and mark present</button>}
          {!result.candidate_student_id && <p>No identity was assigned. Use the manual roll call workflow for verification.</p>}
        </div>}
      </section>
      <div className="verity-dashboard-grid"><CameraQualityCard /><section className="verity-panel"><div className="verity-panel-heading"><div><span className="panel-kicker">LIMITATIONS</span><h2>Safe operating mode</h2></div><ShieldCheck size={18} /></div><ul className="plain-checklist"><li>One face per inference; no group identification.</li><li>Manual attendance is always available as a non-biometric alternative.</li><li>USB RGB webcam input does not provide a validated liveness or presentation-attack signal.</li><li>No classroom dataset is available, so thresholds and demographic error rates are not validated.</li></ul></section></div>
    </>
  );
}

export function FacialEnrolmentPage() {
  const students = useResource<Student[]>("/api/v1/students");
  const [status, setStatus] = useState<RecognitionStatus | null>(null);
  const [studentId, setStudentId] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void apiRequest<RecognitionStatus>("/api/v1/recognition/status", { signal: controller.signal })
      .then(setStatus)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Recognition readiness is unavailable.");
      });
    return () => controller.abort();
  }, []);
  async function enroll(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!studentId) return;
    const form = new FormData(event.currentTarget);
    const image = form.get("image");
    if (!(image instanceof File) || image.size === 0) return;
    const body = new FormData();
    body.append("image", image);
    body.append("consent_confirmed", String(form.get("consent_confirmed") === "true"));
    body.append("consent_record_id", String(form.get("consent_record_id") ?? ""));
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const response = await apiRequest<{ expires_at: string; model_version: string }>(`/api/v1/students/${studentId}/face-template`, { method: "POST", body });
      setMessage(`Encrypted template enrolled. Retention ends ${new Date(response.expires_at).toLocaleDateString()}. Model: ${response.model_version}.`);
      event.currentTarget.reset();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Enrollment could not be completed.");
    } finally {
      setSaving(false);
    }
  }
  async function deleteTemplate() {
    if (!studentId || !window.confirm("Delete this student's biometric template? This cannot be undone.")) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await apiRequest<void>(`/api/v1/students/${studentId}/face-template`, { method: "DELETE" });
      setMessage("Biometric template deleted.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Template deletion failed.");
    } finally {
      setSaving(false);
    }
  }
  return <>
    <PageHeader eyebrow="BIOMETRIC PRIVACY" title="Facial enrolment" description="Enroll only with documented student or guardian consent; templates are encrypted and expire under the configured retention policy." />
    <div className="verity-alert"><ShieldCheck size={18} /><span>Enrollment readiness: {status ? status.enrollment_ready ? "ready" : status.reason ?? "not configured" : "checking…"}. The API stores only an encrypted SFace embedding, not the uploaded image. Secure key material is external to the database.</span></div>
    {error && <div className="verity-alert verity-alert-error" role="alert">{error}</div>}
    {message && <div className="verity-alert" role="status">{message}</div>}
    <section className="verity-panel">
      <div className="verity-panel-heading"><div><span className="panel-kicker">CONSENTED TEMPLATE</span><h2>Enroll or erase one student</h2></div></div>
      <label>Student<select value={studentId} onChange={(event) => setStudentId(event.target.value)}><option value="">Select a student</option>{(students.data ?? []).map((item) => <option key={item.id} value={item.id}>{item.student_number} · {item.first_name} {item.last_name}</option>)}</select></label>
      <form className="academic-inline-form" onSubmit={(event) => void enroll(event)}>
        <label>Single-face image<input name="image" type="file" accept="image/jpeg,image/png,image/webp" required /></label>
        <label>Consent record reference<input name="consent_record_id" type="text" minLength={1} maxLength={255} required /></label>
        <label className="consent-checkbox"><input name="consent_confirmed" type="checkbox" value="true" required /> I confirm that current, documented student/guardian consent for facial processing has been obtained.</label>
        <button className="button button-primary" disabled={saving || !studentId || status?.enrollment_ready !== true}>{saving ? "Processing…" : "Encrypt and enroll"}</button>
        <button type="button" className="button button-secondary" disabled={saving || !studentId} onClick={() => void deleteTemplate()}>Delete template / withdraw</button>
      </form>
    </section>
    <div className="device-note">A consent checkbox is not a substitute for the institution's lawful consent process. This interface stores an opaque consent reference only; do not enter the consent document itself.</div>
  </>;
}

export function AttendanceRecordsPage() {
  const sessions = useResource<AttendanceSession[]>("/api/v1/attendance-sessions");
  const [sessionId, setSessionId] = useState("");
  const [editingId, setEditingId] = useState("");
  const [editMark, setEditMark] = useState<AttendanceRecord["mark"]>("present");
  const [reason, setReason] = useState("");
  const { error: correctionError, run } = useMutationError();
  const records = useResource<AttendanceRecord[]>(sessionId ? `/api/v1/attendance-sessions/${sessionId}/records` : "/api/v1/attendance-sessions");
  const students = useResource<Student[]>("/api/v1/students");
  const studentName = new Map((students.data ?? []).map((student) => [student.id, `${student.student_number} · ${student.first_name} ${student.last_name}`]));
  const selectedSession = sessions.data?.find((session) => session.id === sessionId);
  async function saveCorrection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!sessionId || !editingId) return;
    try {
      await run(() => apiRequest(`/api/v1/attendance-sessions/${sessionId}/records/${editingId}`, {
        method: "PATCH",
        body: JSON.stringify({ mark: editMark, reason }),
      }));
      setEditingId("");
      setReason("");
      records.reload();
    } catch { /* Error is presented in the page. */ }
  }
  return (
    <>
      <PageHeader eyebrow="VERIFIED RECORDS" title="Attendance records" description="Review real attendance marks stored for a classroom session." action={sessionId ? <a className="button button-secondary" href={`/api/v1/attendance-sessions/${sessionId}/records.csv`}><Download size={15} /> Export CSV</a> : undefined} />
      <section className="verity-panel"><label className="session-selector">Attendance session<select value={sessionId} onChange={(event) => setSessionId(event.target.value)}><option value="">Choose a session</option>{(sessions.data ?? []).map((item) => <option key={item.id} value={item.id}>{new Date(item.scheduled_for ?? item.started_at).toLocaleString()} · {item.status}</option>)}</select></label>
        {correctionError && <div className="verity-alert verity-alert-error" role="alert">{correctionError}</div>}
        {!sessionId ? <div className="verity-panel-empty">Select a session to view its attendance records.</div> : <ResourceState loading={records.loading || students.loading} error={records.error ?? students.error} empty={Boolean(records.data && records.data.length === 0)}><div className="academic-table-wrap"><table className="academic-table"><thead><tr><th>Student</th><th>Attendance mark</th><th>Method</th><th>Recorded at</th><th>Correction</th></tr></thead><tbody>{(records.data ?? []).map((record) => <tr key={record.id}><td>{studentName.get(record.student_id) ?? "Student record unavailable"}</td><td>{record.mark}</td><td>{record.method.replace(/_/g, " ")}</td><td>{new Date(record.marked_at).toLocaleString()}</td><td>{editingId === record.id ? <form className="correction-form" onSubmit={(event) => void saveCorrection(event)}><select aria-label="Corrected mark" value={editMark} onChange={(event) => setEditMark(event.target.value as AttendanceRecord["mark"])}><option value="present">Present</option><option value="late">Late</option><option value="absent">Absent</option><option value="excused">Excused</option></select><input aria-label="Correction reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Reason required" minLength={3} required /><button className="text-button">Save</button><button type="button" className="text-button" onClick={() => setEditingId("")}>Cancel</button></form> : <button className="text-button" onClick={() => { setEditingId(record.id); setEditMark(record.mark); }}>Correct</button>}</td></tr>)}</tbody></table></div></ResourceState>}
        {selectedSession?.status === "closed" && <p className="device-note">This session is closed. Records are read-only.</p>}
      </section>
    </>
  );
}

export function ReportsPage() {
  const sessions = useResource<AttendanceSession[]>("/api/v1/attendance-sessions");
  return (
    <>
      <PageHeader eyebrow="REPORTING" title="Attendance reports" description="Export attendance records by class session. Reports are derived from persisted marks." />
      <ResourceState loading={sessions.loading} error={sessions.error} empty={Boolean(sessions.data && sessions.data.length === 0)}>
        <section className="verity-panel"><div className="verity-panel-heading"><div><span className="panel-kicker">CSV EXPORT</span><h2>Session reports</h2></div></div><div className="academic-table-wrap"><table className="academic-table"><thead><tr><th>Class section</th><th>Started</th><th>Status</th><th>Export</th></tr></thead><tbody>{(sessions.data ?? []).map((item) => <tr key={item.id}><td>{item.class_section_id}</td><td>{new Date(item.started_at).toLocaleString()}</td><td>{item.status}</td><td><a href={`/api/v1/attendance-sessions/${item.id}/records.csv`} className="button button-secondary"><Download size={14} /> CSV</a></td></tr>)}</tbody></table></div></section>
      </ResourceState>
      <div className="device-note">PDF exports and cross-session analytics are not implemented.</div>
    </>
  );
}

export function UsersPage() {
  return <><PageHeader eyebrow="ACCESS CONTROL" title="Users and permissions" description="Authentication and server-side administrator, staff, and lecturer roles are enabled." /><div className="verity-alert"><ShieldCheck size={18} /><span>User invitation and role editing are not implemented. Provision a lecturer account using the secure CLI: <code>python -m app.cli create-user --email lecturer@example.edu --role lecturer</code>. API permissions are enforced server-side.</span></div></>;
}

export function AuditLogsPage() {
  return <><PageHeader eyebrow="ACCOUNTABILITY" title="Audit logs" description="Attendance and academic mutations are recorded in the append-only audit log." /><div className="verity-alert"><ShieldCheck size={18} /><span>Audit writes are enabled. An authenticated audit-event browsing and export screen is not implemented yet.</span></div></>;
}

export function SettingsPage() {
  return <><PageHeader eyebrow="PRIVACY & OPERATIONS" title="Settings" description="Device and data-protection readiness." /><div className="verity-dashboard-grid"><section className="verity-panel"><h2>Biometric privacy</h2><p>Face identification is disabled. No face images or templates are captured by the application.</p><p>Consent and automatic retention enforcement are not yet implemented. Do not upload or enroll real biometric data.</p></section><section className="verity-panel"><h2>Offline and device support</h2><p>Offline attendance queue and server synchronization are not enabled. Camera and light readings appear only while a user starts a local browser preview.</p><p>Battery status is shown only when the browser exposes a device reading; otherwise it is reported unavailable.</p></section></div></>;
}
