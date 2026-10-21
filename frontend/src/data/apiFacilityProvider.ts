import { api, type AttendanceEvent, type Person as ApiPerson, type Room as ApiRoom } from "../lib/api";
import { facilityRooms } from "./facilityData";
import type { AttendanceRecord, FacilityRoom, Person } from "./models";
import type { AttendanceCommand, FacilityDataProvider, PersonWrite } from "./facilityProvider";

function roomSlug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function mapRoom(room: ApiRoom): FacilityRoom {
  const slug = roomSlug(room.code);
  const known = facilityRooms.find((candidate) =>
    candidate.id === slug
    || roomSlug(candidate.name) === slug
    || roomSlug(candidate.id) === slug
    || roomSlug(candidate.name) === roomSlug(room.name),
  );
  const template = known ?? facilityRooms.find((candidate) => candidate.capacity > 0) ?? facilityRooms[0];
  return {
    ...template,
    id: room.id,
    name: room.name,
    floorId: room.floor <= 1 ? "level-1" : "level-2",
    floorLabel: `Floor ${room.floor}`,
    capacity: room.capacity,
    events: [],
  };
}

function buildAttendance(
  events: AttendanceEvent[],
  people: ApiPerson[],
  rooms: ApiRoom[],
): AttendanceRecord[] {
  const peopleById = new Map(people.map((person) => [person.id, person]));
  const roomsById = new Map(rooms.map((room) => [room.id, room]));
  return events.map((event) => {
    const person = peopleById.get(event.person_id);
    const room = event.room_id ? roomsById.get(event.room_id) : undefined;
    return {
      id: event.id,
      personId: event.person_id,
      personName: person?.full_name ?? "Unknown person",
      initials: person?.full_name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2) ?? "?",
      avatar: person?.photo_url ?? "",
      action: event.kind === "check_in" ? "Check-in" : "Check-out",
      timestamp: event.occurred_at,
      department: person?.department ?? "",
      room: room?.name ?? "No room recorded",
      source: event.source === "terminal"
        ? "authorized-terminal"
        : event.source === "import"
          ? "imported-attendance"
          : "manual-attendance",
      recordStatus: "confirmed",
    };
  });
}

export const apiFacilityProvider: FacilityDataProvider = {
  async listPeople() {
    const [people, events, rooms] = await Promise.all([
      api.listPeople(),
      api.listAttendance(),
      api.listRooms(),
    ]);
    const records = buildAttendance(events, people, rooms);
    return people.map((person) => {
      const latest = records.find((record) => record.personId === person.id);
      const active = person.status !== "inactive";
      return {
        id: person.id,
        name: person.full_name,
        role: person.title,
        department: person.department,
        status: latest?.action === "Check-in" ? "Present" : "Absent",
        room: latest?.action === "Check-in" ? latest.room : "No recent confirmation",
        lastSeen: latest ? new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", hour12: true }).format(new Date(latest.timestamp)) : "No confirmed attendance",
        avatar: person.photo_url ?? "",
        initials: person.full_name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2),
        email: person.email,
        badge: person.external_ref,
        registrationStatus: active ? "Active" : "Inactive",
        locationTimestamp: latest?.timestamp ?? "",
      } satisfies Person;
    });
  },
  async listAttendance(personId) {
    const [events, people, rooms] = await Promise.all([
      api.listAttendance(personId),
      api.listPeople(),
      api.listRooms(),
    ]);
    return buildAttendance(events, people, rooms);
  },
  async listRooms() {
    return (await api.listRooms()).map(mapRoom);
  },
  async listLocationEvents() {
    const [events, rooms] = await Promise.all([
      api.listAttendance(),
      api.listRooms(),
    ]);
    const roomsById = new Map(rooms.map((room) => [room.id, mapRoom(room)]));
    return events.flatMap((event) => {
      if (!event.room_id || !roomsById.has(event.room_id)) return [];
      return [{
        id: event.id,
        personId: event.person_id,
        roomId: event.room_id,
        timestamp: event.occurred_at,
        source: event.source === "terminal"
          ? "authorized-terminal"
          : event.source === "import"
            ? "imported-attendance"
            : "manual-attendance",
        eventType: event.kind === "check_in" ? "check-in" : "check-out",
      }];
    });
  },
  async createPerson(input: PersonWrite) {
    await api.createPerson(input);
  },
  async updatePerson(id: string, changes: Partial<PersonWrite>) {
    await api.updatePerson(id, changes);
  },
  async checkIn(command: AttendanceCommand) {
    await api.checkIn(
      {
        person_id: command.personId,
        room_id: command.roomId ?? null,
        occurred_at: command.timestamp,
      },
      command.idempotencyKey,
    );
  },
  async checkOut(command: AttendanceCommand) {
    await api.checkOut(
      {
        person_id: command.personId,
        room_id: command.roomId ?? null,
        occurred_at: command.timestamp,
      },
      command.idempotencyKey,
    );
  },
};
