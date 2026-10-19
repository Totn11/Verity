import type { FacilityRoom, LocationEvent, LocationSource, LocationState, Person } from "./models";
import { people } from "./mockData";

export type { FacilityRoom, LocationEvent, LocationSource, LocationState } from "./models";

export type RoomPerson = {
  person: Person;
  event: LocationEvent;
  state: LocationState;
};

export type FacilityFloor = {
  id: string;
  name: string;
};

export const facilityFloors: FacilityFloor[] = [
  { id: "level-1", name: "Level 1" },
  { id: "level-2", name: "Level 2" },
];

const event = (id: string, personId: string, roomId: string, timestamp: string, eventType: LocationEvent["eventType"] = "recognition"): LocationEvent => ({
  id,
  personId,
  roomId,
  timestamp,
  source: eventType === "access" ? "access-reader" : "authorized-terminal",
  eventType,
});

export const facilityRooms: FacilityRoom[] = [
  {
    id: "north-workspace", name: "North Wing workspace", floorId: "level-2", floorLabel: "Level 2", capacity: 30, color: "blue", kind: "workspace",
    bounds: { x: 76, y: 90, width: 510, height: 300 },
    events: [
      event("evt-marcus", "VR-2049", "north-workspace", "2026-10-19T09:08:42", "access"),
      event("evt-leila", "VR-2056", "north-workspace", "2026-10-19T08:27:26", "recognition"),
      event("evt-ethan", "VR-2051", "north-workspace", "2026-10-18T17:12:00", "access"),
    ],
  },
  {
    id: "meeting-a", name: "Meeting room A", floorId: "level-2", floorLabel: "Level 2", capacity: 10, color: "purple", kind: "meeting",
    bounds: { x: 620, y: 90, width: 210, height: 135 },
    events: [event("evt-nia", "VR-2052", "meeting-a", "2026-10-19T08:48:33")],
  },
  {
    id: "studio-02", name: "Studio 02", floorId: "level-2", floorLabel: "Level 2", capacity: 16, color: "teal", kind: "workspace",
    bounds: { x: 620, y: 245, width: 210, height: 145 },
    events: [event("evt-amara", "VR-2048", "studio-02", "2026-10-19T09:12:18")],
  },
  {
    id: "quiet-lounge", name: "Quiet lounge", floorId: "level-2", floorLabel: "Level 2", capacity: 12, color: "amber", kind: "lounge",
    bounds: { x: 76, y: 425, width: 170, height: 100 },
    events: [],
  },
  {
    id: "central-corridor", name: "Central corridor", floorId: "level-2", floorLabel: "Level 2", capacity: 0, color: "teal", kind: "corridor",
    bounds: { x: 265, y: 425, width: 321, height: 100 },
    events: [],
  },
  {
    id: "level2-lift", name: "Elevators", floorId: "level-2", floorLabel: "Level 2", capacity: 0, color: "blue", kind: "access",
    bounds: { x: 620, y: 425, width: 90, height: 100 },
    events: [],
  },
  {
    id: "north-exit", name: "North exit", floorId: "level-2", floorLabel: "Level 2", capacity: 0, color: "amber", kind: "exit",
    bounds: { x: 744, y: 425, width: 86, height: 100 },
    events: [],
  },
  {
    id: "reception", name: "Reception", floorId: "level-1", floorLabel: "Level 1", capacity: 14, color: "blue", kind: "entrance",
    bounds: { x: 76, y: 90, width: 228, height: 165 },
    events: [event("evt-sofia", "VR-2050", "reception", "2026-10-19T09:01:05", "access")],
  },
  {
    id: "cafeteria", name: "Cafeteria", floorId: "level-1", floorLabel: "Level 1", capacity: 48, color: "amber", kind: "workspace",
    bounds: { x: 332, y: 90, width: 254, height: 165 },
    events: [event("evt-priya", "VR-2054", "cafeteria", "2026-10-19T08:35:14", "access")],
  },
  {
    id: "south-workspace", name: "South workspace", floorId: "level-1", floorLabel: "Level 1", capacity: 24, color: "teal", kind: "workspace",
    bounds: { x: 76, y: 285, width: 360, height: 160 },
    events: [],
  },
  {
    id: "central-hall", name: "Central hall", floorId: "level-1", floorLabel: "Level 1", capacity: 0, color: "blue", kind: "corridor",
    bounds: { x: 462, y: 285, width: 124, height: 160 },
    events: [],
  },
  {
    id: "level1-meeting", name: "Meeting room B", floorId: "level-1", floorLabel: "Level 1", capacity: 12, color: "purple", kind: "meeting",
    bounds: { x: 612, y: 90, width: 218, height: 165 },
    events: [],
  },
  {
    id: "east-entrance", name: "East entrance", floorId: "level-1", floorLabel: "Level 1", capacity: 0, color: "amber", kind: "entrance",
    bounds: { x: 612, y: 285, width: 99, height: 160 },
    events: [],
  },
  {
    id: "level1-exit", name: "South exit", floorId: "level-1", floorLabel: "Level 1", capacity: 0, color: "amber", kind: "exit",
    bounds: { x: 735, y: 285, width: 95, height: 160 },
    events: [],
  },
];

const sampleLocationEvents = facilityRooms.flatMap((facilityRoom) => facilityRoom.events);

export function getRoomPeople(room: FacilityRoom, now = Date.now(), registeredPeople: Person[] = people, locationEvents: LocationEvent[] = sampleLocationEvents): RoomPerson[] {
  const lastEventByPerson = new Map<string, LocationEvent>();
  locationEvents.forEach((locationEvent) => {
    const existing = lastEventByPerson.get(locationEvent.personId);
    if (!existing || new Date(locationEvent.timestamp).getTime() > new Date(existing.timestamp).getTime()) lastEventByPerson.set(locationEvent.personId, locationEvent);
  });
  return Array.from(lastEventByPerson.values()).flatMap((locationEvent) => {
    if (locationEvent.roomId !== room.id) return [];
    const person = registeredPeople.find((entry) => entry.id === locationEvent.personId);
    if (!person) return [];
    const ageMs = now - new Date(locationEvent.timestamp).getTime();
    const isValidTime = Number.isFinite(ageMs) && ageMs >= 0;
    return [{
      person,
      event: locationEvent,
      state: !isValidTime ? "unknown" as const : ageMs > 4 * 60 * 60 * 1000 ? "stale" as const : "confirmed" as const,
    }];
  });
}

export function formatEventTime(value: string) {
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return "Timestamp unavailable";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" }).format(timestamp);
}

export function getSourceLabel(source: LocationSource) {
  if (source === "mock-terminal") return "Simulated authorized terminal";
  if (source === "authorized-terminal") return "Authorized recognition terminal";
  if (source === "access-reader") return "Access-control reader";
  return "Approved location source";
}
