import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Activity, ArrowLeft, ArrowRight, Building2, CalendarDays, Check, ChevronDown, CircleAlert, Download, Filter, Fingerprint, KeyRound, LayoutGrid, List, MapPin, MoreHorizontal, Pencil, Search, Settings2, ShieldCheck, UserPlus, Users, UserRoundX } from "lucide-react";
import Avatar from "../components/Avatar";
import DataTable from "../components/DataTable";
import FacilityMapPage from "../components/FacilityMapPage";
import RecognitionTerminal from "../components/RecognitionTerminal";
import PageHeader from "../components/PageHeader";
import PersonEditorDialog from "../components/PersonEditorDialog";
import StatusBadge from "../components/StatusBadge";
import { facilityRooms } from "../data/facilityData";
import type { Person } from "../data/mockData";
import { usePeople, type PersonInput } from "../data/PeopleContext";

function formatLocationTime(value: string) {
  if (!value) return "No recent confirmation";
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return "Time unavailable";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(timestamp);
}
export function LoginPage() {
  const [submitted, setSubmitted] = useState(false);
  return (
    <div className="login-screen">
      <div className="login-brand"><span className="brand-mark"><Fingerprint size={21} /></span><span className="brand-name">verity<span>.</span></span></div>
      <div className="login-card"><span className="login-kicker">WELCOME BACK</span><h1>Sign in to your workspace</h1><p>Manage attendance and facility operations securely.</p>
        {submitted && <div className="inline-success"><Check size={16} /> Demo sign-in submitted. Authentication is not connected yet.</div>}
        <form onSubmit={(event) => { event.preventDefault(); setSubmitted(true); }}>
          <label>Email address<input type="email" placeholder="you@company.com" required /></label>
          <label>Password<input type="password" placeholder="Enter your password" required /></label>
          <div className="login-options"><label className="checkbox-label"><input type="checkbox" /> Remember me</label><a href="mailto:support@verity.example">Forgot password?</a></div>
          <button className="button button-primary login-submit" type="submit">Sign in <ArrowRight size={16} /></button>
        </form>
        <div className="login-security"><ShieldCheck size={15} /> Protected with enterprise-grade security</div>
      </div>
      <div className="login-foot">© 2026 Verity Systems <span>·</span> <a href="mailto:privacy@verity.example">Privacy</a></div>
    </div>
  );
}

export function AttendancePage() {
  const { people, attendanceRecords, recognitionEvents } = usePeople();
  const [query, setQuery] = useState("");
  const [date, setDate] = useState(() => {
    const today = new Date();
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  });
  const [eventFilter, setEventFilter] = useState("All events");
  const [page, setPage] = useState(0);
  const pageSize = 8;
  const dateRecords = attendanceRecords.filter((record) => record.timestamp.slice(0, 10) === date);
  const dateRecognitions = recognitionEvents.filter((event) => event.timestamp.slice(0, 10) === date);
  const allEvents = [
    ...dateRecords.map((record) => ({
      id: record.id,
      personId: record.personId,
      personName: record.personName,
      eventType: record.action,
      timestamp: record.timestamp,
      location: record.room,
      confidence: record.recordStatus === "sample" ? "Sample attendance" : "Recorded",
      state: "success" as const,
    })),
    ...dateRecognitions.map((event) => ({
      id: event.id,
      personId: event.personId,
      personName: event.personName,
      eventType: event.outcome === "success" ? "Recognition" : "Unmatched",
      timestamp: event.timestamp,
      location: event.location,
      confidence: event.confidence,
      state: event.outcome,
    })),
  ].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  const visibleEvents = allEvents.filter((event) => {
    const matchesQuery = `${event.personName} ${event.location} ${event.personId ?? ""}`.toLowerCase().includes(query.trim().toLowerCase());
    const matchesType = eventFilter === "All events"
      || (eventFilter === "Check-ins" && event.eventType === "Check-in")
      || (eventFilter === "Check-outs" && event.eventType === "Check-out")
      || (eventFilter === "Unmatched" && event.eventType === "Unmatched");
    return matchesQuery && matchesType;
  });
  const pageCount = Math.max(1, Math.ceil(visibleEvents.length / pageSize));
  const currentPage = Math.min(page, pageCount - 1);
  const pageEvents = visibleEvents.slice(currentPage * pageSize, (currentPage + 1) * pageSize);
  const confirmedCount = dateRecords.filter((record) => record.action === "Check-in").length;
  const reviewCount = dateRecognitions.filter((event) => event.outcome === "failed").length;
  const latestEvent = allEvents[0];
  return (
    <>
      <PageHeader eyebrow="ATTENDANCE" title="Live attendance" description="Monitor check-ins and recognition activity across your facility." action={<button className="button button-primary"><Download size={16} /> Export report</button>} />
      <div className="demo-banner"><span className="demo-banner-icon"><Activity size={16} /></span><span><strong>Simulated activity</strong> — this demo does not connect to live cameras. Events below are illustrative only.</span><button aria-label="Dismiss notice">×</button></div>
      <div className="compact-stats"><div><span>Confirmed check-ins</span><strong>{confirmedCount}</strong><small>From shared demo attendance data</small></div><div><span>Recognition attempts</span><strong>{dateRecognitions.length}</strong><small>Simulated results</small></div><div><span>Needs review</span><strong className="text-amber">{reviewCount}</strong><small>Unmatched attempts</small></div><div><span>Last event</span><strong className="small-stat">{latestEvent ? new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", hour12: true }).format(new Date(latestEvent.timestamp)) : "—"}</strong><small>{latestEvent?.location ?? "No events for selected date"}</small></div></div>
      <div className="panel page-table-panel"><div className="toolbar"><div className="search-field table-search"><Search size={16} /><input aria-label="Search people or rooms" placeholder="Search people or rooms..." value={query} onChange={(event) => { setQuery(event.target.value); setPage(0); }} /></div><label className="button button-secondary"><CalendarDays size={15} /><input className="date-picker" aria-label="Filter attendance by date" type="date" value={date} onChange={(event) => { setDate(event.target.value); setPage(0); }} /></label><label className="button button-secondary"><Filter size={15} /><select className="native-select" aria-label="Filter attendance events" value={eventFilter} onChange={(event) => { setEventFilter(event.target.value); setPage(0); }}><option>All events</option><option>Check-ins</option><option>Check-outs</option><option>Unmatched</option></select></label></div>
        <div className="table-scroll"><table className="data-table"><thead><tr><th>PERSON</th><th>EVENT</th><th>TIME</th><th>LAST CONFIRMED LOCATION</th><th>RECORD</th><th>STATUS</th></tr></thead><tbody>{pageEvents.map((event) => {
          const person = event.personId ? people.find((entry) => entry.id === event.personId) : undefined;
          const eventTime = new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true }).format(new Date(event.timestamp));
          const personContent = <span className="person-cell"><Avatar person={person ?? { name: event.personName, initials: "?", avatar: "" }} size="sm" /><span><strong>{event.personName}</strong><small>{person?.id ?? "No registered match"}</small></span></span>;
          return <tr key={event.id}><td>{person ? <Link to={`/people/${person.id}`} className="person-cell">{personContent}</Link> : personContent}</td><td>{event.eventType}</td><td>{eventTime}</td><td><span className="table-time"><MapPin size={13} />{event.location}</span></td><td><span className={event.state === "failed" ? "text-amber" : "text-green"}>{event.confidence}</span></td><td><StatusBadge tone={event.state === "failed" ? "amber" : "green"}>{event.state === "failed" ? "Review" : event.eventType === "Recognition" ? "Simulated" : "Recorded"}</StatusBadge></td></tr>;
        })}</tbody></table>
          {pageEvents.length === 0 && <div className="directory-empty"><span><Search size={20} /></span><strong>No matching events</strong><p>Try a different search, date, or event filter.</p></div>}
        </div>
        <div className="table-pagination"><span>Showing {visibleEvents.length ? `${currentPage * pageSize + 1}–${Math.min((currentPage + 1) * pageSize, visibleEvents.length)} of ${visibleEvents.length}` : "0"} events · Demo data</span><div><button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button><button disabled={currentPage >= pageCount - 1} onClick={() => setPage(currentPage + 1)}>Next</button></div></div>
      </div>
    </>
  );
}

export function AuditLogsPage() {
  const entries = [
    { actor: "Sarah Chen", action: "Viewed attendance dashboard", resource: "Attendance", time: "Today, 9:45 AM", status: "Sample" },
    { actor: "David Park", action: "Exported attendance report", resource: "Reports", time: "Today, 8:51 AM", status: "Sample" },
    { actor: "Sarah Chen", action: "Updated workspace settings", resource: "Settings", time: "Yesterday, 4:12 PM", status: "Sample" },
    { actor: "Maya Patel", action: "Reviewed unmatched recognition attempt", resource: "Recognition events", time: "Yesterday, 2:37 PM", status: "Sample" },
  ];
  return (
    <>
      <PageHeader eyebrow="ADMINISTRATION" title="Audit logs" description="Review administrative activity in the workspace." action={<button className="button button-secondary"><Download size={16} /> Export logs</button>} />
      <div className="demo-banner"><span className="demo-banner-icon"><ShieldCheck size={16} /></span><span><strong>Sample audit history</strong> — entries shown are illustrative and are not production records.</span></div>
      <div className="panel page-table-panel">
        <div className="toolbar"><div className="search-field table-search"><Search size={16} /><input placeholder="Search actor or action..." aria-label="Search audit logs" /></div><button className="button button-secondary"><CalendarDays size={15} /> Last 7 days <ChevronDown size={14} /></button><button className="button button-secondary"><Filter size={15} /> Event type</button></div>
        <div className="table-scroll"><table className="data-table"><thead><tr><th>ACTOR</th><th>ACTION</th><th>RESOURCE</th><th>DATE & TIME</th><th>RECORD</th></tr></thead><tbody>{entries.map((entry) => <tr key={`${entry.actor}-${entry.action}`}><td><span className="person-cell"><span className="avatar avatar-sm admin-table-avatar">{entry.actor.split(" ").map((part) => part[0]).join("")}</span><span><strong>{entry.actor}</strong><small>Workspace administrator</small></span></span></td><td>{entry.action}</td><td>{entry.resource}</td><td>{entry.time}</td><td><StatusBadge tone="gray">{entry.status}</StatusBadge></td></tr>)}</tbody></table></div>
        <div className="table-pagination"><span>Showing 1–{entries.length} of {entries.length} sample events</span><div><button disabled>Previous</button><button disabled>Next</button></div></div>
      </div>
    </>
  );
}

export function DirectoryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("search") ?? "");
  const [department, setDepartment] = useState("All departments");
  const [role, setRole] = useState("All roles");
  const [attendance, setAttendance] = useState("All attendance");
  const [registration, setRegistration] = useState("All registration");
  const [view, setView] = useState<"table" | "grid">("table");
  const [page, setPage] = useState(0);
  const [editing, setEditing] = useState<Person | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const { people, addPerson, updatePerson, deactivatePerson, role: userRole } = usePeople();
  const canManageDirectory = userRole === "administrator";
  const pageSize = view === "table" ? 6 : 8;
  const departments = useMemo(() => Array.from(new Set(people.map((person) => person.department))).sort(), [people]);
  const roles = useMemo(() => Array.from(new Set(people.map((person) => person.role))).sort(), [people]);
  const filteredPeople = useMemo(() => people.filter((person) => {
    const queryMatch = `${person.name} ${person.id}`.toLowerCase().includes(query.trim().toLowerCase());
    return queryMatch
      && (department === "All departments" || person.department === department)
      && (role === "All roles" || person.role === role)
      && (attendance === "All attendance" || person.status === attendance)
      && (registration === "All registration" || person.registrationStatus === registration);
  }), [people, query, department, role, attendance, registration]);
  const pageCount = Math.max(1, Math.ceil(filteredPeople.length / pageSize));
  const currentPage = Math.min(page, pageCount - 1);
  const pagePeople = filteredPeople.slice(currentPage * pageSize, (currentPage + 1) * pageSize);
  const activeCount = people.filter((person) => person.registrationStatus === "Active").length;
  const presentCount = people.filter((person) => person.registrationStatus === "Active" && person.status === "Present").length;

  function setFilter(setter: (value: string) => void, value: string) {
    setter(value);
    setPage(0);
  }

  function savePerson(values: PersonInput) {
    if (editing) {
      updatePerson(editing.id, values);
    } else {
      addPerson(values);
      clearFilters();
    }
    setEditing(null);
    setAddOpen(false);
  }

  function handleDeactivate(person: Person) {
    if (person.registrationStatus === "Inactive") return;
    if (window.confirm(`Deactivate ${person.name}'s registration? The record will remain in the directory.`)) deactivatePerson(person.id);
  }

  function clearFilters() {
    setQuery("");
    setDepartment("All departments");
    setRole("All roles");
    setAttendance("All attendance");
    setRegistration("All registration");
    setSearchParams({});
    setPage(0);
  }

  return (
    <>
      <PageHeader eyebrow="DIRECTORY" title="People directory" description="View authorized facility profiles, registration, and attendance information." action={canManageDirectory ? <button className="button button-primary" onClick={() => setAddOpen(true)}><UserPlus size={16} /> Register person</button> : undefined} />
      <div className="directory-summary"><div><span className="summary-icon"><Users size={17} /></span><span><strong>{activeCount} active registrations</strong><small>{people.length} fictional demo profiles · {departments.length} departments</small></span></div><div className="summary-right"><span className="summary-present"><i /> {presentCount} present</span><span className="summary-absent"><i /> {activeCount - presentCount} not confirmed</span></div></div>
      <div className="directory-privacy"><ShieldCheck size={15} /><span>Prototype role-based UI only—not access control. This directory uses fictional records; uploaded photos are not used to match arbitrary images.</span></div>
      <div className="panel directory-panel">
        <div className="directory-toolbar">
          <label className="search-field directory-search"><Search size={16} /><input aria-label="Search people by name or ID" value={query} onChange={(event) => { setQuery(event.target.value); setPage(0); setSearchParams(event.target.value ? { search: event.target.value } : {}); }} placeholder="Search name or ID..." /></label>
          <select className="native-select" aria-label="Filter department" value={department} onChange={(event) => setFilter(setDepartment, event.target.value)}><option>All departments</option>{departments.map((value) => <option key={value}>{value}</option>)}</select>
          <select className="native-select" aria-label="Filter role" value={role} onChange={(event) => setFilter(setRole, event.target.value)}><option>All roles</option>{roles.map((value) => <option key={value}>{value}</option>)}</select>
          <select className="native-select" aria-label="Filter attendance status" value={attendance} onChange={(event) => setFilter(setAttendance, event.target.value)}><option>All attendance</option><option>Present</option><option>Absent</option><option>On leave</option></select>
          <select className="native-select" aria-label="Filter registration status" value={registration} onChange={(event) => setFilter(setRegistration, event.target.value)}><option>All registration</option><option>Active</option><option>Inactive</option></select>
          <div className="directory-view-toggle" role="group" aria-label="Directory display mode"><button className={view === "table" ? "view-toggle-active" : ""} aria-label="Table view" aria-pressed={view === "table"} onClick={() => { setView("table"); setPage(0); }}><List size={16} /></button><button className={view === "grid" ? "view-toggle-active" : ""} aria-label="Grid view" aria-pressed={view === "grid"} onClick={() => { setView("grid"); setPage(0); }}><LayoutGrid size={16} /></button></div>
        </div>
        {view === "table" ? (
          <DataTable headers={["PERSON", "ID NUMBER", "DEPARTMENT", "ROLE", "REGISTRATION", "ATTENDANCE", "LAST CONFIRMED LOCATION", "LOCATION TIME", ""]} empty={pagePeople.length === 0} emptyMessage={<div className="directory-empty-inline"><strong>No people match these filters</strong><span>Try another name or ID, or clear the active filters.</span><button className="button button-secondary" onClick={clearFilters}>Clear filters</button></div>}>
            {pagePeople.map((person) => (
              <tr key={person.id}>
                <td><Link to={`/people/${person.id}`} className="person-cell"><Avatar person={person} size="sm" /><span><strong>{person.name}</strong><small>{person.id}</small></span></Link></td>
                <td>{person.id}</td><td>{person.department}</td><td>{person.role}</td>
                <td><StatusBadge tone={person.registrationStatus === "Active" ? "green" : "gray"}>{person.registrationStatus}</StatusBadge></td>
                <td><StatusBadge tone={person.status === "Present" ? "green" : person.status === "Absent" ? "amber" : "gray"}>{person.status}</StatusBadge></td>
                <td>{person.room}</td><td>{formatLocationTime(person.locationTimestamp)}</td>
                <td>{canManageDirectory && <span className="directory-row-actions"><button className="icon-more" aria-label={`Edit ${person.name}`} onClick={() => setEditing(person)}><Pencil size={15} /></button><button className="icon-more" aria-label={`Deactivate ${person.name}`} disabled={person.registrationStatus === "Inactive"} onClick={() => handleDeactivate(person)}><UserRoundX size={15} /></button></span>}</td>
              </tr>
            ))}
          </DataTable>
        ) : (
          pagePeople.length ? <div className="people-card-grid">{pagePeople.map((person) => <article className="person-card panel" key={person.id}>
            <div className="person-card-top"><Avatar person={person} size="lg" />{canManageDirectory && <span className="directory-row-actions"><button className="icon-more" aria-label={`Edit ${person.name}`} onClick={() => setEditing(person)}><Pencil size={15} /></button><button className="icon-more" aria-label={`Deactivate ${person.name}`} disabled={person.registrationStatus === "Inactive"} onClick={() => handleDeactivate(person)}><UserRoundX size={15} /></button></span>}</div>
            <Link to={`/people/${person.id}`} className="person-card-name">{person.name}</Link><span className="person-card-role">{person.role} · {person.department}</span>
            <div className="person-card-id"><span>ID</span><strong>{person.id}</strong></div>
            <div className="person-card-badges"><StatusBadge tone={person.registrationStatus === "Active" ? "green" : "gray"}>{person.registrationStatus}</StatusBadge><StatusBadge tone={person.status === "Present" ? "green" : person.status === "Absent" ? "amber" : "gray"}>{person.status}</StatusBadge></div>
            <div className="person-card-location"><MapPin size={14} /><span><strong>{person.room}</strong><small>{formatLocationTime(person.locationTimestamp)}</small></span></div>
          </article>)}</div> : <div className="directory-empty"><span><UserRoundX size={22} /></span><strong>No people found</strong><p>Try another name or ID, or adjust the department, role, and status filters.</p><button className="button button-secondary" onClick={clearFilters}>Clear filters</button></div>
        )}
        <div className="table-pagination"><span>{filteredPeople.length ? `Showing ${currentPage * pageSize + 1}–${Math.min((currentPage + 1) * pageSize, filteredPeople.length)} of ${filteredPeople.length} profiles` : "No profiles"} · Demonstration records</span><div><button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button><button disabled={currentPage >= pageCount - 1} onClick={() => setPage(currentPage + 1)}>Next</button></div></div>
      </div>
      {canManageDirectory && addOpen && <PersonEditorDialog existingIds={people.map((person) => person.id)} onClose={() => setAddOpen(false)} onSave={savePerson} />}
      {canManageDirectory && editing && <PersonEditorDialog person={editing} existingIds={people.map((person) => person.id)} onClose={() => setEditing(null)} onSave={savePerson} />}
    </>
  );
}

export function PersonProfilePage() {
  const { personId } = useParams();
  const { people, updatePerson, deactivatePerson, attendanceRecords, role: userRole } = usePeople();
  const [editing, setEditing] = useState(false);
  const person = people.find((entry) => entry.id === personId);
  if (!person) return <div className="directory-empty panel"><span><UserRoundX size={22} /></span><strong>Person not found</strong><p>This record may have been removed from the current demo session.</p><Link className="button button-secondary" to="/people">Back to directory</Link></div>;
  const selectedPerson = person;
  const canManageDirectory = userRole === "administrator";
  const personAttendance = attendanceRecords.filter((record) => record.personId === person.id).sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  const attendanceDays = new Set(personAttendance.filter((record) => record.action === "Check-in").map((record) => record.timestamp.slice(0, 10))).size;
  const checkoutCount = personAttendance.filter((record) => record.action === "Check-out").length;
  function savePerson(values: PersonInput) {
    updatePerson(selectedPerson.id, values);
    setEditing(false);
  }
  function handleDeactivate() {
    if (selectedPerson.registrationStatus === "Inactive") return;
    if (window.confirm(`Deactivate ${selectedPerson.name}'s registration? The record will remain in the directory.`)) deactivatePerson(selectedPerson.id);
  }
  return (
    <>
      <Link to="/people" className="back-link"><ArrowLeft size={15} /> Back to people</Link>
      <div className="profile-hero panel"><Avatar person={person} size="lg" /><div className="profile-hero-copy"><div className="profile-name-line"><h1>{person.name}</h1><StatusBadge tone={person.registrationStatus === "Active" ? "green" : "gray"}>{person.registrationStatus}</StatusBadge><StatusBadge tone={person.status === "Present" ? "green" : person.status === "Absent" ? "amber" : "gray"}>{person.status}</StatusBadge></div><p>{person.role} <span>·</span> {person.department} <span>·</span> {person.id}</p><div className="profile-contact">Last confirmed: {formatLocationTime(person.locationTimestamp)}</div></div>{canManageDirectory && <div className="profile-actions"><button className="button button-secondary" onClick={() => setEditing(true)}><Pencil size={15} /> Edit profile</button><button className="button button-secondary" disabled={person.registrationStatus === "Inactive"} onClick={handleDeactivate}><UserRoundX size={15} /> {person.registrationStatus === "Inactive" ? "Inactive" : "Deactivate"}</button></div>}</div>
      <div className="profile-grid"><div className="panel profile-info"><div className="panel-heading"><div><h2>Last confirmed location</h2><p>Not a live location feed</p></div><span className="info-icon"><MapPin size={17} /></span></div><div className="last-location"><span className="location-pin"><MapPin size={17} /></span><div><strong>{person.room}</strong><small>{formatLocationTime(person.locationTimestamp)}</small></div></div><div className="location-note">Location is based on the most recent confirmed attendance event. This demo does not provide live location tracking.</div></div>
        <div className="panel profile-info"><div className="panel-heading"><div><h2>Attendance in demo data</h2><p>Derived from recorded attendance events</p></div><span className="info-icon"><CalendarDays size={17} /></span></div><div className="month-metrics"><div><strong>{attendanceDays}</strong><span>Days checked in</span></div><div><strong>{checkoutCount}</strong><span>Check-outs</span></div><div><strong>{personAttendance.length}</strong><span>Total events</span></div></div></div></div>
      <div className="panel page-table-panel profile-history"><div className="panel-heading"><div><h2>Attendance history</h2><p>Recorded events for {person.name}</p></div><span className="demo-tag">DEMO DATA</span></div><div className="table-scroll"><table className="data-table"><thead><tr><th>DATE & TIME</th><th>EVENT</th><th>LAST CONFIRMED ROOM</th><th>SOURCE</th><th>STATUS</th></tr></thead><tbody>{personAttendance.map((record) => <tr key={record.id}><td>{formatLocationTime(record.timestamp)}</td><td>{record.action}</td><td>{record.room}</td><td><span className="table-time"><Fingerprint size={14} /> {record.source === "mock-terminal" ? "Mock terminal" : "Sample event"}</span></td><td><StatusBadge tone={record.action === "Check-in" ? "green" : "amber"}>{record.recordStatus === "sample" ? "Sample" : "Recorded"}</StatusBadge></td></tr>)}</tbody></table>{personAttendance.length === 0 && <div className="directory-empty"><strong>No attendance history</strong><p>No attendance events are available for this person in this demo session.</p></div>}</div></div>
      {canManageDirectory && editing && <PersonEditorDialog person={person} existingIds={people.map((entry) => entry.id)} onClose={() => setEditing(false)} onSave={savePerson} />}
    </>
  );
}

export function FacilityPage() {
  return <FacilityMapPage />;
}

export function CheckInPage() {
  return <RecognitionTerminal />;
}

export function ReportsPage() {
  const { people, attendanceRecords, recognitionEvents } = usePeople();
  const [endDate, setEndDate] = useState(() => {
    const today = new Date();
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  });
  const [department, setDepartment] = useState("All departments");
  const activePeople = people.filter((person) => person.registrationStatus === "Active");
  const departments = Array.from(new Set(activePeople.map((person) => person.department))).sort();
  const rangeEnd = new Date(`${endDate}T23:59:59`);
  const rangeStart = new Date(rangeEnd);
  rangeStart.setDate(rangeStart.getDate() - 6);
  const startKey = `${rangeStart.getFullYear()}-${String(rangeStart.getMonth() + 1).padStart(2, "0")}-${String(rangeStart.getDate()).padStart(2, "0")}`;
  const rangeRecords = attendanceRecords.filter((record) => {
    const person = people.find((entry) => entry.id === record.personId);
    return record.timestamp.slice(0, 10) >= startKey
      && record.timestamp.slice(0, 10) <= endDate
      && (department === "All departments" || person?.department === department);
  });
  const checkIns = rangeRecords.filter((record) => record.action === "Check-in");
  const averageAttendance = (checkIns.length / 7).toFixed(1);
  const presentCount = activePeople.filter((person) => person.status === "Present" && (department === "All departments" || person.department === department)).length;
  const capacity = facilityRooms.reduce((total, room) => total + room.capacity, 0);
  const roomUtilization = Math.round((presentCount / capacity) * 100);
  const unmatchedCount = recognitionEvents.filter((event) => event.outcome === "failed" && event.timestamp.slice(0, 10) >= startKey && event.timestamp.slice(0, 10) <= endDate).length;
  const dailyCounts = Array.from({ length: 7 }, (_, index) => {
    const day = new Date(rangeStart);
    day.setDate(rangeStart.getDate() + index);
    const key = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
    const count = checkIns.filter((record) => record.timestamp.slice(0, 10) === key).length;
    return { key, label: new Intl.DateTimeFormat("en-US", { weekday: "short" }).format(day), count };
  });
  const maxDailyCount = Math.max(1, ...dailyCounts.map((day) => day.count));
  const departmentRows = departments.map((name) => {
    const count = activePeople.filter((person) => person.department === name && person.status === "Present").length;
    return { name, count, width: Math.round((count / Math.max(1, presentCount)) * 100) };
  }).filter((entry) => department === "All departments" || entry.name === department);
  return (
    <>
      <PageHeader eyebrow="INSIGHTS" title="Reports & analytics" description="Understand attendance patterns and facility utilization." action={<button className="button button-primary"><Download size={16} /> Export report</button>} />
      <div className="toolbar report-toolbar"><label className="button button-secondary"><CalendarDays size={15} /><span>7 days ending</span><input className="date-picker" aria-label="Report end date" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label><label className="button button-secondary"><Filter size={15} /><select className="native-select" aria-label="Filter report department" value={department} onChange={(event) => setDepartment(event.target.value)}><option>All departments</option>{departments.map((name) => <option key={name}>{name}</option>)}</select></label></div>
      <div className="stats-grid report-stats"><div className="stat-card"><span className="stat-label">Average daily check-ins</span><div className="stat-value">{averageAttendance}</div><div className="stat-foot"><span>7-day sample</span></div></div><div className="stat-card"><span className="stat-label">Present records today</span><div className="stat-value">{presentCount}</div><div className="stat-foot"><span>From attendance status</span></div></div><div className="stat-card"><span className="stat-label">Recorded room utilization</span><div className="stat-value">{roomUtilization}%</div><div className="stat-foot"><span>Across configured room capacity</span></div></div><div className="stat-card"><span className="stat-label">Unmatched attempts</span><div className="stat-value">{unmatchedCount}</div><div className="stat-foot"><span>Simulated recognition events</span></div></div></div>
      <div className="report-grid"><div className="panel report-chart-panel"><div className="panel-heading"><div><h2>Attendance by day</h2><p>Daily confirmed check-ins · shared demo records</p></div><span className="demo-tag">7 DAYS</span></div><div className="bar-chart">{dailyCounts.map((day) => <div className="bar-group" key={day.key} title={`${day.count} check-ins`}><span style={{ height: `${Math.max(8, (day.count / maxDailyCount) * 100)}%` }} /><small>{day.label}</small></div>)}</div></div><div className="panel departments-panel"><div className="panel-heading"><div><h2>By department</h2><p>Present demo profiles</p></div><MoreHorizontal size={18} /></div>{departmentRows.map(({ name, count, width }) => <div className="department-row" key={name}><div><span>{name}</span><strong>{count}</strong></div><div className="mini-progress"><span style={{ width: `${width}%` }} /></div></div>)}{departmentRows.length === 0 && <p className="report-footnote">No department records match this filter.</p>}</div></div>
      <div className="report-footnote">All analytics on this page use demonstration data and are not operational records.</div>
    </>
  );
}

export function UsersPage() {
  const admins = [{ name: "Sarah Chen", email: "sarah.chen@northstar.example", role: "Owner", status: "Active", initials: "SC" }, { name: "David Park", email: "david.park@northstar.example", role: "Administrator", status: "Active", initials: "DP" }, { name: "Maya Patel", email: "maya.patel@northstar.example", role: "Security reviewer", status: "Active", initials: "MP" }, { name: "James Wilson", email: "james.wilson@northstar.example", role: "Read only", status: "Pending", initials: "JW" }];
  return (
    <>
      <PageHeader eyebrow="ADMINISTRATION" title="Team & permissions" description="Control who can access your facility workspace." action={<button className="button button-primary"><UserPlus size={16} /> Invite user</button>} />
      <div className="security-callout"><ShieldCheck size={19} /><div><strong>Access is limited to authorized staff</strong><span>Review role permissions regularly, especially for biometric and attendance records.</span></div><Link to="/settings">Manage security <ArrowRight size={14} /></Link></div>
      <div className="compact-stats admin-stats"><div><span>Workspace users</span><strong>12</strong><small>Across 4 roles</small></div><div><span>Active sessions</span><strong>4</strong><small>Current sessions</small></div><div><span>Pending invites</span><strong>2</strong><small>Expires in 7 days</small></div></div>
      <div className="panel page-table-panel"><div className="panel-heading table-panel-heading"><div><h2>Workspace users</h2><p>Manage roles and access</p></div><button className="button button-secondary"><Filter size={15} /> Filter</button></div><div className="table-scroll"><table className="data-table"><thead><tr><th>USER</th><th>ROLE</th><th>STATUS</th><th>LAST ACTIVE</th><th></th></tr></thead><tbody>{admins.map((admin, index) => <tr key={admin.email}><td><span className="person-cell"><span className="avatar avatar-sm admin-table-avatar">{admin.initials}</span><span><strong>{admin.name}</strong><small>{admin.email}</small></span></span></td><td>{admin.role}</td><td><StatusBadge tone={admin.status === "Active" ? "green" : "amber"}>{admin.status}</StatusBadge></td><td>{index === 0 ? "Just now" : `${index * 2 + 1} hours ago`}</td><td><button className="icon-more" aria-label={`More actions for ${admin.name}`}><MoreHorizontal size={18} /></button></td></tr>)}</tbody></table></div></div>
      <div className="roles-grid"><div className="panel role-card"><span className="role-icon role-blue"><KeyRound size={18} /></span><div><strong>Owner</strong><p>Full workspace access, including billing and security settings.</p><small>1 user</small></div></div><div className="panel role-card"><span className="role-icon role-teal"><Settings2 size={18} /></span><div><strong>Administrator</strong><p>Manage people, attendance, and facility configuration.</p><small>3 users</small></div></div><div className="panel role-card"><span className="role-icon role-purple"><ShieldCheck size={18} /></span><div><strong>Security reviewer</strong><p>Review recognition events and audit history.</p><small>2 users</small></div></div></div>
    </>
  );
}

export function SettingsPage() {
  const [saved, setSaved] = useState(false);
  return (
    <>
      <PageHeader eyebrow="ADMINISTRATION" title="Settings & audit" description="Manage workspace configuration, privacy controls, and security history." />
      <div className="settings-layout"><div className="settings-nav panel"><a className="settings-nav-active" href="#workspace"><Building2Icon /> Workspace</a><a href="#privacy"><ShieldCheck size={16} /> Privacy & data</a><a href="#audit"><Activity size={16} /> Audit log</a><a href="#notifications"><CircleAlert size={16} /> Notifications</a></div>
        <div className="settings-content"><section className="panel settings-card" id="workspace"><div className="panel-heading"><div><h2>Workspace details</h2><p>General information about your facility</p></div></div><label className="form-row">Workspace name<input defaultValue="Northstar HQ" /></label><label className="form-row">Timezone<select defaultValue="America/New_York"><option value="America/New_York">Eastern Time (US & Canada)</option><option value="UTC">UTC</option><option value="America/Los_Angeles">Pacific Time</option></select></label><label className="form-row">Attendance day starts at<input type="time" defaultValue="06:00" /></label></section>
        <section className="panel settings-card" id="privacy"><div className="panel-heading"><div><h2>Privacy & data</h2><p>Controls for sensitive attendance and biometric information</p></div></div><div className="setting-toggle"><div><strong>Require consent before check-in</strong><span>Prompt individuals before any biometric processing.</span></div><input type="checkbox" defaultChecked aria-label="Require consent before check-in" /></div><div className="setting-toggle"><div><strong>Limit location history retention</strong><span>Retain room confirmations only as long as your policy allows.</span></div><input type="checkbox" defaultChecked aria-label="Limit location history retention" /></div><div className="settings-note"><CircleAlert size={16} /><span>Production data controls must be implemented and reviewed before connecting biometric data.</span></div></section>
        <section className="panel settings-card" id="audit"><div className="panel-heading"><div><h2>Recent audit log</h2><p>Recent administrative activity · sample entries</p></div><button className="text-link">View all <ArrowRight size={14} /></button></div>{[["Sarah Chen", "Updated workspace settings", "Today, 9:34 AM"], ["David Park", "Exported attendance report", "Today, 8:51 AM"], ["Sarah Chen", "Invited James Wilson", "Yesterday, 4:12 PM"]].map(([user, action, time]) => <div className="audit-row" key={action}><span className="audit-dot" /><div><strong>{action}</strong><small>{user} · {time}</small></div><StatusBadge tone="gray">Sample</StatusBadge></div>)}</section>
        <div className="settings-save">{saved && <span className="save-confirm"><Check size={15} /> Settings saved locally for this demo.</span>}<button className="button button-primary" onClick={() => setSaved(true)}>Save changes</button></div>
      </div></div>
    </>
  );
}

function Building2Icon() {
  return <Building2 size={16} />;
}
