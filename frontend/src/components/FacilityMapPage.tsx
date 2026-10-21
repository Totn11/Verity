import { useEffect, useMemo, useState } from "react";
import { ArrowRight, DoorOpen, Info, MapPin, Search, ShieldCheck, Users, X } from "lucide-react";
import { Link } from "react-router-dom";
import Avatar from "./Avatar";
import PageHeader from "./PageHeader";
import QueryState from "./QueryState";
import StatusBadge from "./StatusBadge";
import { usePeople } from "../data/PeopleContext";
import { useFacilityQueries } from "../data/useFacilityQueries";
import {
  facilityFloors,
  formatEventTime,
  getRoomPeople,
  getSourceLabel,
  type FacilityRoom,
  type LocationState,
} from "../data/facilityData";

const stateLabel: Record<LocationState, string> = {
  confirmed: "Recent confirmation",
  stale: "Stale event",
  unknown: "No location event",
};

function roomState(room: FacilityRoom, registeredPeople: ReturnType<typeof usePeople>["people"], locationEvents: ReturnType<typeof usePeople>["locationEvents"]): LocationState {
  const people = getRoomPeople(room, Date.now(), registeredPeople, locationEvents);
  if (people.some((entry) => entry.state === "confirmed")) return "confirmed";
  if (people.some((entry) => entry.state === "stale")) return "stale";
  return "unknown";
}

function RoomPlan({ room, selected, matched, registeredPeople, locationEvents, onSelect }: { room: FacilityRoom; selected: boolean; matched: boolean; registeredPeople: ReturnType<typeof usePeople>["people"]; locationEvents: ReturnType<typeof usePeople>["locationEvents"]; onSelect: () => void }) {
  const people = getRoomPeople(room, Date.now(), registeredPeople, locationEvents);
  const state = roomState(room, registeredPeople, locationEvents);
  const { x, y, width, height } = room.bounds;
  const isAccessPoint = room.kind === "entrance" || room.kind === "exit" || room.kind === "access";
  const fill = isAccessPoint ? "#f7f9fa" : room.color === "blue" ? "#f0f5fc" : room.color === "purple" ? "#f5f1fb" : room.color === "amber" ? "#fff8ec" : "#eef8f6";
  const stroke = selected ? "#188f84" : matched ? "#57b9ae" : state === "confirmed" ? "#89c9bf" : state === "stale" ? "#d6b471" : "#cbd4dc";

  return (
    <g
      className={`map-room map-room-${state} ${selected ? "map-room-selected" : ""} ${matched ? "map-room-match" : ""}`}
      role="button"
      tabIndex={0}
      aria-label={`${room.name}, ${people.length} recorded ${people.length === 1 ? "person" : "people"}, ${stateLabel[state]}`}
      aria-pressed={selected}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
    >
      <rect x={x} y={y} width={width} height={height} rx="8" fill={fill} stroke={stroke} strokeWidth={selected ? 3 : matched ? 2.5 : 1.5} strokeDasharray={state === "unknown" ? "5 4" : undefined} />
      <circle cx={x + width - 20} cy={y + 19} r="5" className={`map-state-dot map-state-${state}`} />
      <text x={x + 14} y={y + 24} className="map-room-title">{room.name}</text>
      {room.capacity > 0 ? (
        <>
          <text x={x + 14} y={y + 43} className="map-room-meta">{people.length} recorded · {room.capacity} capacity</text>
          <text x={x + 14} y={y + 59} className="map-room-status">{stateLabel[state]}</text>
          {people.slice(0, 4).map(({ person }, index) => {
            const dotX = x + 18 + index * 30;
            const dotY = y + height - 20;
            return (
              <g key={person.id} aria-hidden="true">
                <circle cx={dotX} cy={dotY} r="10" className={`map-person-marker marker-${state}`} />
                <text x={dotX} y={dotY + 3} className="map-person-initials">{person.initials}</text>
              </g>
            );
          })}
          {people.length > 4 && <text x={x + 18 + 4 * 30} y={y + height - 17} className="map-room-meta">+{people.length - 4}</text>}
        </>
      ) : (
        <>
          <text x={x + 14} y={y + 45} className="map-room-status">{people.length ? `${people.length} recorded event${people.length === 1 ? "" : "s"}` : room.kind === "corridor" ? "Corridor" : room.kind === "access" ? "Access point" : room.kind === "exit" ? "Exit" : "Entrance"}</text>
          {room.kind !== "corridor" && <DoorOpen x={x + width - 32} y={y + height - 31} size={18} className="map-access-icon" />}
        </>
      )}
    </g>
  );
}

export default function FacilityMapPage() {
  const facility = useFacilityQueries();
  const people = facility.people.data ?? [];
  const locationEvents = facility.locationEvents.data ?? [];
  const rooms = facility.rooms.data ?? [];
  const [floorId, setFloorId] = useState(facilityFloors[1].id);
  const [query, setQuery] = useState("");
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null);
  useEffect(() => {
    if (facility.isApi && rooms.length && !rooms.some((room) => room.floorId === floorId)) {
      setFloorId(rooms[0].floorId);
    }
  }, [facility.isApi, floorId, rooms]);
  const floorRooms = useMemo(() => rooms.filter((room) => room.floorId === floorId), [floorId, rooms]);
  const selectedRoom = floorRooms.find((room) => room.id === selectedRoomId) ?? null;
  const normalizedQuery = query.trim().toLowerCase();
  const matchingRooms = floorRooms.filter((room) => {
    if (!normalizedQuery) return false;
    return room.name.toLowerCase().includes(normalizedQuery)
      || getRoomPeople(room, Date.now(), people, locationEvents).some(({ person }) => `${person.name} ${person.id}`.toLowerCase().includes(normalizedQuery));
  });
  const matchedIds = new Set(matchingRooms.map((room) => room.id));
  const activePeople = selectedRoom ? getRoomPeople(selectedRoom, Date.now(), people, locationEvents) : [];
  const allFloorPeople = floorRooms.flatMap((room) => getRoomPeople(room, Date.now(), people, locationEvents));
  const roomCount = floorRooms.filter((room) => room.capacity > 0).length;
  const selectedRoomLocationState = selectedRoom ? roomState(selectedRoom, people, locationEvents) : "unknown";

  function changeFloor(value: string) {
    setFloorId(value);
    setSelectedRoomId(null);
  }

  if (facility.isPending) return <QueryState loading error={null} />;
  if (facility.error) return <QueryState loading={false} error={facility.error} />;

  return (
    <>
      <PageHeader eyebrow="FACILITY" title="Facility map" description={`Explore floor plans and review room associations from ${facility.isApi ? "API attendance" : "sample events"}.`} action={<label className="floor-select-label"><span>Floor</span><select className="native-select floor-select" aria-label="Select facility floor" value={floorId} onChange={(event) => changeFloor(event.target.value)}>{facilityFloors.map((floor) => <option key={floor.id} value={floor.id}>{floor.name}</option>)}</select></label>} />
      {!facility.isApi && <div className="demo-banner"><span className="demo-banner-icon"><MapPin size={16} /></span><span><strong>Demonstration location events</strong> — a recognition or access event confirms a person at that point and time only. It does not establish their current location.</span></div>}
      {facility.isApi && <div className="demo-banner"><span className="demo-banner-icon"><MapPin size={16} /></span><span><strong>API attendance locations</strong> — room events are derived from attendance records, not live tracking.</span></div>}

      <div className="facility-map-toolbar">
        <label className="search-field facility-search"><Search size={16} /><input aria-label="Search people and rooms" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search people, IDs, or rooms..." />{query && <button type="button" className="search-clear" aria-label="Clear map search" onClick={() => setQuery("")}><X size={14} /></button>}</label>
        <span className="map-data-tag"><span className="demo-tag">{facility.isApi ? "API" : "SAMPLE"}</span> Last event records · not live tracking</span>
      </div>

      {normalizedQuery && matchingRooms.length === 0 && <div className="map-search-empty"><Info size={15} /> No rooms or people on this floor match “{query}”.</div>}

      <div className="facility-map-layout">
        <section className="panel interactive-map-panel" aria-label={`${facilityFloors.find((floor) => floor.id === floorId)?.name} floor plan`}>
          <div className="map-panel-heading"><div><h2>Northstar HQ · {facilityFloors.find((floor) => floor.id === floorId)?.name}</h2><p>Selectable floor plan · choose a room for its event details</p></div><span className="map-room-count">{roomCount} rooms</span></div>
          {rooms.length === 0 && !facility.isPending && !facility.error
            ? <div className="directory-empty"><strong>No rooms configured</strong><p>Add rooms to the facility API to display them on the map.</p></div>
            : <div className="svg-floor-wrap">
            <svg className="svg-floorplan" viewBox="0 0 900 610" role="group" aria-label="Interactive facility floor plan">
              <defs><pattern id="floor-grid" width="16" height="16" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#e7ecef" /></pattern></defs>
              <rect x="0" y="0" width="900" height="610" rx="12" fill="url(#floor-grid)" />
              <rect x="48" y="58" width="810" height="500" rx="13" fill="#fff" stroke="#dce4e9" strokeWidth="2" />
              <text x="450" y="43" textAnchor="middle" className="map-direction-label">NORTH ↑</text>
              <text x="450" y="585" textAnchor="middle" className="map-direction-label">SOUTH</text>
              <rect x="60" y="400" width="786" height="27" rx="5" fill="#f4f6f7" stroke="#dfe5e9" />
              <text x="453" y="418" textAnchor="middle" className="map-corridor-label">MAIN CORRIDOR · CENTRAL ACCESS ROUTE</text>
              <path d="M165 390v10 M354 390v10 M700 390v10 M260 427v-10 M580 427v-10" stroke="#a9b6c0" strokeWidth="3" />
              <path d="M445 400v27" stroke="#72879a" strokeWidth="4" strokeDasharray="4 4" />
              <text x="450" y="446" textAnchor="middle" className="map-access-label">LIFT / STAIR CORE</text>
              {floorId === "level-1" && <g aria-label="Main entrance and exits"><path d="M48 320h12 M846 320h12 M450 558v-12" stroke="#168f84" strokeWidth="5" /><text x="68" y="312" className="map-access-label">MAIN ENTRANCE</text><text x="748" y="312" className="map-access-label">EAST ENTRANCE</text><text x="450" y="543" textAnchor="middle" className="map-access-label">SOUTH EXIT</text></g>}
              {floorId === "level-2" && <g aria-label="North exit"><path d="M450 58v12" stroke="#168f84" strokeWidth="5" /><text x="450" y="85" textAnchor="middle" className="map-access-label">NORTH EXIT</text></g>}
              {floorRooms.map((room) => <RoomPlan key={room.id} room={room} selected={selectedRoomId === room.id} matched={matchedIds.has(room.id)} registeredPeople={people} locationEvents={locationEvents} onSelect={() => setSelectedRoomId(room.id)} />)}
            </svg>
            </div>}
          {rooms.length > 0 && floorRooms.length === 0 && <div className="directory-empty"><strong>No rooms configured on this floor</strong><p>Choose another floor to view its room records.</p></div>}
          <div className="map-legend">
            <span><i className="map-legend-dot legend-confirmed" /> Recent event <small>within 4 hours</small></span>
            <span><i className="map-legend-dot legend-stale" /> Stale event <small>over 4 hours</small></span>
            <span><i className="map-legend-dot legend-unknown" /> Unknown <small>no room event</small></span>
            <span><i className="legend-capacity" /> Recorded event count / room capacity</span>
          </div>
          <div className="map-caveat"><ShieldCheck size={14} /> “Recent” means an event was recorded at its source at that time—not a live or current position.</div>
        </section>

        <aside className="panel room-details-panel" aria-label="Room and location details">
          {selectedRoom ? (
            <>
              <div className="room-detail-heading"><div className={`room-mark room-${selectedRoom.color}`}><MapPin size={15} /></div><div><h2>{selectedRoom.name}</h2><p>{selectedRoom.floorLabel} · {selectedRoom.kind === "corridor" ? "Corridor" : selectedRoom.kind}</p></div><button className="icon-button" aria-label="Clear selected room" onClick={() => setSelectedRoomId(null)}><X size={16} /></button></div>
              <div className="room-stat-strip"><div><strong>{activePeople.length}</strong><span>Recorded events</span></div><div><strong>{selectedRoom.capacity || "—"}</strong><span>{selectedRoom.capacity ? "Room capacity" : "Capacity not set"}</span></div><StatusBadge tone={selectedRoomLocationState === "confirmed" ? "green" : selectedRoomLocationState === "stale" ? "amber" : "gray"}>{stateLabel[selectedRoomLocationState]}</StatusBadge></div>
              <div className="room-people-heading"><strong>People associated with room</strong><span>{facility.isApi ? "From attendance records" : "From recorded demo events"}</span></div>
              {activePeople.length ? <div className="room-people-list">{activePeople.map(({ person, event, state }) => <article className="room-person-item" key={event.id}>
                <Link to={`/people/${person.id}`} className="room-person-link"><Avatar person={person} size="sm" /><span><strong>{person.name}</strong><small>{person.id} · {person.department}</small></span><ArrowRight size={14} /></Link>
                <div className="location-event-meta"><span className={`location-state-dot location-state-${state}`} />{stateLabel[state]}<time>{formatEventTime(event.timestamp)}</time></div>
                <div className="location-source"><DoorOpen size={12} /> {getSourceLabel(event.source)} · {event.eventType === "recognition" ? "recognition event" : facility.isApi ? `recorded ${event.eventType}` : event.eventType === "check-in" ? "demo check-in" : event.eventType === "check-out" ? "demo check-out" : "access event"}</div>
              </article>)}</div> :               <div className="room-empty"><span><Users size={19} /></span><strong>No location events for this room</strong><p>There are no people associated with this room in the {facility.isApi ? "attendance data" : "sample event data"}. This does not prove that the room is empty.</p></div>}
            </>
          ) : (
            <>
              <div className="panel-heading room-list-heading"><div><h2>Rooms on this floor</h2><p>Select a room to inspect its events</p></div></div>
              <div className="floor-room-list">{floorRooms.map((room) => {
                const roomPeople = getRoomPeople(room, Date.now(), people, locationEvents);
                const state = roomState(room, people, locationEvents);
                const visible = !normalizedQuery || matchedIds.has(room.id);
                if (!visible) return null;
                return <button key={room.id} className={`floor-room-row ${matchedIds.has(room.id) && normalizedQuery ? "floor-room-match" : ""}`} onClick={() => setSelectedRoomId(room.id)}>
                  <span className={`room-mark room-${room.color}`}><MapPin size={14} /></span>
                  <span className="floor-room-copy"><strong>{room.name}</strong><small>{room.capacity ? `${roomPeople.length} recorded · ${room.capacity} capacity` : room.kind}</small></span>
                  <span className={`location-state-dot location-state-${state}`} title={stateLabel[state]} />
                  <ArrowRight size={14} className="floor-room-arrow" />
                </button>;
              })}</div>
              <div className="room-panel-note"><Info size={14} /><span>{allFloorPeople.length} people have recorded location events on this floor. Select a room to inspect event times, source, and profile links.</span></div>
            </>
          )}
        </aside>
      </div>
    </>
  );
}
