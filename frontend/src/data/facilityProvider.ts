import type { AttendanceRecord, FacilityRoom, LocationEvent, Person } from "./models";

export type PersonWrite = {
  external_ref: string;
  full_name: string;
  email: string;
  phone: string;
  department: string;
  title: string;
  status: "active" | "inactive" | "visitor";
  photo_url: string | null;
};

export type AttendanceCommand = {
  personId: string;
  roomId?: string;
  timestamp?: string;
  idempotencyKey?: string;
};

export interface FacilityDataProvider {
  listPeople(): Promise<Person[]>;
  listAttendance(personId?: string): Promise<AttendanceRecord[]>;
  listRooms(): Promise<FacilityRoom[]>;
  listLocationEvents(): Promise<LocationEvent[]>;
  createPerson(input: PersonWrite): Promise<void>;
  updatePerson(id: string, changes: Partial<PersonWrite>): Promise<void>;
  checkIn(command: AttendanceCommand): Promise<void>;
  checkOut(command: AttendanceCommand): Promise<void>;
}
