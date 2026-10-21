import { createContext, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { facilityRooms } from "./facilityData";
import {
  initialAttendanceRecords,
  initialRecognitionEvents,
  people as samplePeople,
} from "./mockData";
import type {
  AttendanceAction,
  AttendanceRecord,
  LocationEvent,
  Person,
  RecognitionEvent,
} from "./models";
import type { AttendanceCommand, FacilityDataProvider, PersonWrite } from "./facilityProvider";

export type PersonInput = Pick<Person, "name" | "id" | "department" | "role" | "status" | "registrationStatus" | "avatar" | "initials" | "email"> & { phone: string };
export type DemoRole = "administrator" | "staff";
export type TerminalAttendanceEvent = {
  id: string;
  personId: string;
  personName: string;
  initials: string;
  avatar: string;
  action: AttendanceAction;
  timestamp: string;
  terminal: string;
  location: string;
  roomId?: string;
  source: "mock-terminal";
};

type PeopleContextValue = {
  people: Person[];
  terminalEvents: TerminalAttendanceEvent[];
  attendanceRecords: AttendanceRecord[];
  recognitionEvents: RecognitionEvent[];
  locationEvents: LocationEvent[];
  role: DemoRole;
  setRole: (role: DemoRole) => void;
  addPerson: (input: PersonInput) => void;
  updatePerson: (id: string, input: PersonInput) => void;
  deactivatePerson: (id: string) => void;
  recordRecognitionEvent: (event: RecognitionEvent) => void;
  recordTerminalEvent: (event: TerminalAttendanceEvent) => boolean;
  dataProvider: FacilityDataProvider;
};

const initialLocationEvents = facilityRooms.flatMap((room) => room.events);
const PeopleContext = createContext<PeopleContextValue | null>(null);

export function PeopleProvider({ children }: { children: ReactNode }) {
  const [people, setPeople] = useState<Person[]>(samplePeople);
  const [terminalEvents, setTerminalEvents] = useState<TerminalAttendanceEvent[]>([]);
  const [attendanceRecords, setAttendanceRecords] = useState<AttendanceRecord[]>(initialAttendanceRecords);
  const [recognitionEvents, setRecognitionEvents] = useState<RecognitionEvent[]>(initialRecognitionEvents);
  const [locationEvents, setLocationEvents] = useState<LocationEvent[]>(initialLocationEvents);
  const [role, setRole] = useState<DemoRole>("administrator");
  const terminalEventsRef = useRef(terminalEvents);

  function recordTerminalEvent(event: TerminalAttendanceEvent): boolean {
    const latestForPerson = terminalEventsRef.current.find((entry) => entry.personId === event.personId);
    if (latestForPerson && Date.now() - new Date(latestForPerson.timestamp).getTime() < 3_000) return false;

    const person = people.find((entry) => entry.id === event.personId);
    if (!person || person.registrationStatus !== "Active") return false;

    const timestamp = event.timestamp;
    const isCheckIn = event.action === "Check-in";
    const updatedTerminalEvents = [event, ...terminalEventsRef.current];
    terminalEventsRef.current = updatedTerminalEvents;
    setTerminalEvents(updatedTerminalEvents);
    setAttendanceRecords((current) => [{
      id: event.id,
      personId: person.id,
      personName: person.name,
      initials: person.initials,
      avatar: person.avatar,
      action: event.action,
      timestamp,
      department: person.department,
      room: event.location,
      source: event.source,
      recordStatus: "confirmed",
    }, ...current]);
    setPeople((current) => current.map((entry) => entry.id === person.id ? {
      ...entry,
      status: isCheckIn ? "Present" : "Absent",
      room: event.location,
      lastSeen: new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", hour12: true }).format(new Date(timestamp)),
      locationTimestamp: timestamp,
    } : entry));
    setLocationEvents((current) => [{
      id: `location-${event.id}`,
      personId: person.id,
      roomId: event.roomId ?? "east-entrance",
      timestamp,
      source: event.source,
      eventType: isCheckIn ? "check-in" : "check-out",
    }, ...current]);
    return true;
  }

  const dataProvider = useMemo<FacilityDataProvider>(() => ({
    listPeople: async () => people,
    listAttendance: async (personId) => personId
      ? attendanceRecords.filter((record) => record.personId === personId)
      : attendanceRecords,
    listRooms: async () => facilityRooms,
    listLocationEvents: async () => locationEvents,
    createPerson: async (input: PersonWrite) => {
      const name = input.full_name;
      const initials = name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
      setPeople((current) => [{
        id: input.external_ref,
        name,
        role: input.title,
        department: input.department,
        status: "Absent",
        room: "No recent confirmation",
        lastSeen: "No confirmed attendance",
        avatar: input.photo_url ?? "",
        initials,
        email: input.email,
        phone: input.phone,
        badge: input.external_ref,
        registrationStatus: input.status === "inactive" ? "Inactive" : "Active",
        locationTimestamp: "",
      }, ...current]);
    },
    updatePerson: async (id: string, changes: Partial<PersonWrite>) => {
      setPeople((current) => current.map((person) => person.id === id ? {
        ...person,
        ...(changes.full_name ? { name: changes.full_name } : {}),
        ...(changes.title ? { role: changes.title } : {}),
        ...(changes.department ? { department: changes.department } : {}),
        ...(changes.email ? { email: changes.email } : {}),
        ...(changes.phone ? { phone: changes.phone } : {}),
        ...(changes.photo_url !== undefined ? { avatar: changes.photo_url ?? "" } : {}),
        ...(changes.status ? { registrationStatus: changes.status === "inactive" ? "Inactive" : "Active" } : {}),
      } : person));
    },
    checkIn: async (command: AttendanceCommand) => {
      const person = people.find((entry) => entry.id === command.personId);
      if (!person) throw new Error("Person not found.");
      const timestamp = command.timestamp ?? new Date().toISOString();
      const room = facilityRooms.find((entry) => entry.id === command.roomId);
      const recorded = recordTerminalEvent({
        id: command.idempotencyKey ?? `demo-${person.id}-${Date.now()}`,
        personId: person.id,
        personName: person.name,
        initials: person.initials,
        avatar: person.avatar,
        action: "Check-in",
        timestamp,
        terminal: "DEMO",
        location: room?.name ?? "East entrance",
        roomId: room?.id,
        source: "mock-terminal",
      });
      if (!recorded) throw new Error("A duplicate attendance event was blocked.");
    },
    checkOut: async (command: AttendanceCommand) => {
      const person = people.find((entry) => entry.id === command.personId);
      if (!person) throw new Error("Person not found.");
      const timestamp = command.timestamp ?? new Date().toISOString();
      const room = facilityRooms.find((entry) => entry.id === command.roomId);
      const recorded = recordTerminalEvent({
        id: command.idempotencyKey ?? `demo-${person.id}-${Date.now()}`,
        personId: person.id,
        personName: person.name,
        initials: person.initials,
        avatar: person.avatar,
        action: "Check-out",
        timestamp,
        terminal: "DEMO",
        location: room?.name ?? "East entrance",
        roomId: room?.id,
        source: "mock-terminal",
      });
      if (!recorded) throw new Error("A duplicate attendance event was blocked.");
    },
  }), [people, attendanceRecords, locationEvents]);

  const value = useMemo<PeopleContextValue>(() => ({
    people,
    terminalEvents,
    attendanceRecords,
    recognitionEvents,
    locationEvents,
    role,
    setRole,
    dataProvider,
    addPerson: (input) => setPeople((current) => [{
      ...input,
      room: "No recent confirmation",
      lastSeen: "No confirmed attendance",
      locationTimestamp: "",
      email: "",
      badge: input.id,
    }, ...current]),
    updatePerson: (id, input) => setPeople((current) => current.map((person) => person.id === id ? {
      ...person,
      ...input,
      room: input.status === "Present" ? person.room : "No recent confirmation",
      lastSeen: input.status === "Present" ? person.lastSeen : "No confirmed attendance",
      locationTimestamp: input.status === "Present" ? person.locationTimestamp : "",
    } : person)),
    deactivatePerson: (id) => setPeople((current) => current.map((person) => person.id === id ? {
      ...person,
      registrationStatus: "Inactive",
      status: "Absent",
    } : person)),
    recordRecognitionEvent: (event) => {
      setRecognitionEvents((current) => [event, ...current]);
    },
    recordTerminalEvent,
  }), [people, terminalEvents, attendanceRecords, recognitionEvents, locationEvents, role, dataProvider]);

  return <PeopleContext.Provider value={value}>{children}</PeopleContext.Provider>;
}

export function usePeople() {
  const context = useContext(PeopleContext);
  if (!context) throw new Error("usePeople must be used inside PeopleProvider.");
  return context;
}
