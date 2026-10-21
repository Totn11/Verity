import { useMemo, useState } from "react";
import { Activity, ArrowRight, CalendarDays, ChevronDown, CircleAlert, Fingerprint, MapPin, Search, UserCheck, UserRoundX, Users } from "lucide-react";
import { Link } from "react-router-dom";
import AttendanceChart from "../components/AttendanceChart";
import Avatar from "../components/Avatar";
import DataTable from "../components/DataTable";
import PageHeader from "../components/PageHeader";
import StatusBadge from "../components/StatusBadge";
import SummaryCard from "../components/SummaryCard";
import QueryState from "../components/QueryState";
import { getRoomPeople } from "../data/facilityData";
import { usePeople } from "../data/PeopleContext";
import { useFacilityQueries } from "../data/useFacilityQueries";

const pageSize = 4;

function localDateValue(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export default function DashboardPage() {
  const { recognitionEvents, role } = usePeople();
  const facility = useFacilityQueries();
  const people = facility.people.data ?? [];
  const attendanceRecords = facility.attendance.data ?? [];
  const locationEvents = facility.locationEvents.data ?? [];
  const facilityRooms = facility.rooms.data ?? [];
  const visibleRecognitionEvents = facility.isApi ? [] : recognitionEvents;
  const [selectedDate, setSelectedDate] = useState(() => localDateValue(new Date()));
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All statuses");
  const [departmentFilter, setDepartmentFilter] = useState("All departments");
  const [page, setPage] = useState(0);
  const trendData = useMemo(() => {
    const anchor = new Date(`${selectedDate}T12:00:00`);
    return Array.from({ length: 7 }, (_, index) => {
      const day = new Date(anchor);
      day.setDate(anchor.getDate() - 6 + index);
      const key = localDateValue(day);
      return {
        day: new Intl.DateTimeFormat("en-US", { weekday: "short" }).format(day),
        value: attendanceRecords.filter((record) =>
          record.action === "Check-in" && record.timestamp.slice(0, 10) === key,
        ).length,
      };
    });
  }, [attendanceRecords, selectedDate]);
  const isToday = selectedDate === localDateValue(new Date());
  const activePeople = people.filter((person) => person.registrationStatus === "Active");
  const selectedDateRecords = attendanceRecords.filter((record) => record.timestamp.slice(0, 10) === selectedDate);
  const present = isToday
    ? activePeople.filter((person) => person.status === "Present").length
    : new Set(selectedDateRecords.filter((record) => record.action === "Check-in").map((record) => record.personId)).size;
  const registered = activePeople.length;
  const absent = isToday ? registered - present : 0;
  const dashboardRooms = facilityRooms.filter((room) => room.capacity > 0 || locationEvents.some((event) => event.roomId === room.id));
  const rooms = dashboardRooms.map((room) => ({
    ...room,
    people: getRoomPeople(room, Date.now(), people, locationEvents).length,
  }));
  const inside = present;
  const roomCapacity = rooms.reduce((total, room) => total + room.capacity, 0);
  const occupancy = Math.round((inside / roomCapacity) * 100);

  const visiblePeople = useMemo(() => {
    const query = search.trim().toLowerCase();
    return selectedDateRecords.flatMap((record) => {
      const person = people.find((entry) => entry.id === record.personId);
      if (!person) return [];
      const matchesQuery = !query || `${person.name} ${person.id} ${person.department} ${record.room}`.toLowerCase().includes(query);
      const matchesStatus = statusFilter === "All statuses" || person.status === statusFilter;
      const matchesDepartment = departmentFilter === "All departments" || person.department === departmentFilter;
      return matchesQuery && matchesStatus && matchesDepartment ? [{ person, record }] : [];
    });
  }, [search, statusFilter, departmentFilter, selectedDateRecords, people]);
  const pageCount = Math.max(1, Math.ceil(visiblePeople.length / pageSize));
  const currentPage = Math.min(page, pageCount - 1);
  const pagePeople = visiblePeople.slice(currentPage * pageSize, (currentPage + 1) * pageSize);
  const dateLabel = new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" }).format(new Date(`${selectedDate}T12:00:00`));

  function updateStatus(value: string) {
    setStatusFilter(value);
    setPage(0);
  }

  function updateDepartment(value: string) {
    setDepartmentFilter(value);
    setPage(0);
  }

  if (facility.isPending) return <QueryState loading error={null} />;
  if (facility.error) return <QueryState loading={false} error={facility.error} />;

  return (
    <>
      <PageHeader
        eyebrow={dateLabel.toUpperCase()}
        title={`Good morning, ${role === "administrator" ? "Sarah" : "there"}`}
        description="Here’s your attendance and facility overview."
        action={<label className="date-picker-wrap"><CalendarDays size={16} /><input className="date-picker" type="date" aria-label="Select dashboard date" value={selectedDate} onChange={(event) => setSelectedDate(event.target.value || localDateValue(new Date()))} /><ChevronDown size={14} /></label>}
      />
      {!facility.isApi && <div className="demo-banner"><span className="demo-banner-icon"><Fingerprint size={16} /></span><span><strong>Demo environment</strong> — recognition events and attendance records are simulated. No live camera or live location tracking is connected.</span></div>}
      {facility.isApi && <div className="demo-banner"><span className="demo-banner-icon"><Fingerprint size={16} /></span><span><strong>API data source</strong> — attendance and people are loaded from the facility API. Recognition/location events are not available from this API.</span></div>}

      <section className="stats-grid" aria-label="Attendance summary">
        <SummaryCard label="Total registered" value={registered.toLocaleString()} note={facility.isApi ? "Active API profiles" : "Active fictional profiles"} icon={Users} tone="blue" />
        <SummaryCard label={isToday ? "Present today" : "Present on selected date"} value={present.toLocaleString()} note={isToday ? "Attendance confirmed today" : `Check-ins on ${selectedDate}`} icon={UserCheck} tone="green" />
        <SummaryCard label={isToday ? "Absent today" : "Absent on selected date"} value={absent.toLocaleString()} note={isToday ? "No active check-in on selected date" : "Not calculated for historical dates"} icon={UserRoundX} tone="amber" />
        <SummaryCard label="Currently inside" value={inside.toLocaleString()} note="Recorded check-ins · not live occupancy" icon={Activity} tone="purple" />
      </section>

      <section className="dashboard-grid">
        <div className="panel trend-panel">
          <div className="panel-heading"><div><h2>Attendance trend</h2><p>Daily check-ins over the last seven days</p></div><span className="demo-tag">{facility.isApi ? "API DATA" : "DEMO DATA"}</span></div>
          <AttendanceChart data={facility.isApi ? trendData : undefined} isDemo={!facility.isApi} />
        </div>

        <div className="panel occupancy-panel">
          <div className="panel-heading"><div><h2>Facility occupancy</h2><p>Last confirmed room counts</p></div><Link to="/facility" className="text-link">Facility map <ArrowRight size={14} /></Link></div>
          <div className="occupancy-total"><strong>{occupancy}<span>%</span></strong><span className="occupancy-caption">{inside} of {roomCapacity} room capacity</span><div className="occupancy-ring" style={{ background: `conic-gradient(#1da99b ${occupancy}%, #e7f5f3 0)` }}><span>{occupancy}%</span></div></div>
          <div className="room-list">
            {rooms.map((room) => <div className="room-row" key={room.name}><div className={`room-mark room-${room.color}`}><MapPin size={14} /></div><div className="room-details"><strong>{room.name}</strong><small>{room.floorLabel} · last recorded events</small></div><div className="room-count"><strong>{room.people}{room.capacity > 0 && <small> / {room.capacity}</small>}</strong>{room.capacity > 0 && <div className="mini-progress"><span style={{ width: `${Math.min(100, (room.people / room.capacity) * 100)}%` }} /></div>}</div></div>)}
          </div>
          <div className="occupancy-disclaimer"><MapPin size={13} /> Rooms update from confirmed events; not live tracking.</div>
        </div>
      </section>

      <section className="dashboard-grid lower-grid">
        <div className="panel attendance-table-panel">
          <div className="panel-heading"><div><h2>Recent attendance</h2><p>{facility.isApi ? "API records" : "Demo records"} for {dateLabel}</p></div><Link to="/attendance" className="text-link">Full attendance <ArrowRight size={14} /></Link></div>
          <div className="dashboard-table-toolbar">
            <label className="search-field table-search"><Search size={15} /><input aria-label="Search attendance records" placeholder="Search name, ID, room..." value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); }} /></label>
            <select className="native-select" aria-label="Filter attendance status" value={statusFilter} onChange={(event) => updateStatus(event.target.value)}>
              <option>All statuses</option><option>Present</option><option>Absent</option><option>On leave</option>
            </select>
            <select className="native-select department-filter" aria-label="Filter department" value={departmentFilter} onChange={(event) => updateDepartment(event.target.value)}>
              <option>All departments</option>{Array.from(new Set(people.map((person) => person.department))).sort().map((department) => <option key={department}>{department}</option>)}
            </select>
          </div>
          <DataTable headers={["PERSON", "CHECK-IN", "DEPARTMENT", "LAST CONFIRMED LOCATION", "STATUS"]} empty={pagePeople.length === 0} emptyMessage={`No attendance records are available for ${dateLabel}.`}>
            {pagePeople.map(({ person, record }) => (
              <tr key={record.id}>
                <td><Link to={`/people/${person.id}`} className="person-cell"><Avatar person={person} size="sm" /><span><strong>{person.name}</strong><small>{person.id}</small></span></Link></td>
                <td>{new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", hour12: true }).format(new Date(record.timestamp))}</td>
                <td>{record.department}</td>
                <td>{record.room}</td>
                <td><StatusBadge tone={record.action === "Check-in" ? "green" : "amber"}>{record.action}</StatusBadge></td>
              </tr>
            ))}
          </DataTable>
          <div className="table-pagination"><span>{visiblePeople.length ? `Showing ${currentPage * pageSize + 1}–${Math.min((currentPage + 1) * pageSize, visiblePeople.length)} of ${visiblePeople.length}` : "No records"} · {facility.isApi ? "API records" : "Demo records"}</span><div><button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button><button disabled={currentPage >= pageCount - 1} onClick={() => setPage(currentPage + 1)}>Next</button></div></div>
        </div>

        <div className="panel recognition-panel">
          <div className="panel-heading"><div><h2>Recent recognition events</h2><p>Simulated attempts · not a live camera feed</p></div><Link to="/check-in" className="icon-more" aria-label="Open recognition terminal"><ArrowRight size={16} /></Link></div>
          {visibleRecognitionEvents.slice(0, 5).map((event) => <div className="recognition-row" key={event.id}><span className={`recognition-indicator ${event.outcome}`}><Fingerprint size={15} /></span><div className="recognition-copy"><strong>{event.personName}</strong><span>{event.outcome === "success" ? `${event.confidence} simulated match` : "No match · review"}</span></div><time>{new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", hour12: true }).format(new Date(event.timestamp))}</time></div>)}
          {visibleRecognitionEvents.length === 0 && <p className="report-footnote">{facility.isApi ? "Recognition events are not provided by the facility API." : "No recognition events are available."}</p>}
          <div className="alert-note"><CircleAlert size={15} /><span><strong>Failed attempts need review</strong><small>Sample recognition data only</small></span><Link to="/attendance" aria-label="Review recognition events"><ArrowRight size={15} /></Link></div>
        </div>
      </section>

      <div className="dashboard-footer"><span><span className="live-dot" /> {facility.isApi ? "API data" : "Sample data"} · selected date {selectedDate}</span><span>{facility.isApi ? "No live camera or location source connected" : "Demo only · no camera or live location source connected"}</span></div>
    </>
  );
}
