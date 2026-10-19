export type AttendanceStatus = "Present" | "Absent" | "On leave";
export type RegistrationStatus = "Active" | "Inactive";
export type AttendanceAction = "Check-in" | "Check-out";
export type LocationSource = "authorized-terminal" | "access-reader" | "approved-sensor" | "mock-terminal";
export type LocationState = "confirmed" | "stale" | "unknown";

export interface Person {
  id: string;
  name: string;
  role: string;
  department: string;
  status: AttendanceStatus;
  room: string;
  lastSeen: string;
  avatar: string;
  initials: string;
  email: string;
  badge: string;
  registrationStatus: RegistrationStatus;
  locationTimestamp: string;
}

export interface AttendanceRecord {
  id: string;
  personId: string;
  personName: string;
  initials: string;
  avatar: string;
  action: AttendanceAction;
  timestamp: string;
  department: string;
  room: string;
  source: LocationSource;
  recordStatus: "confirmed" | "sample";
}

export interface RecognitionEvent {
  id: string;
  personId: string | null;
  personName: string;
  outcome: "success" | "failed";
  timestamp: string;
  source: LocationSource;
  location: string;
  confidence: string;
  isDemo: boolean;
}

export interface LocationEvent {
  id: string;
  personId: string;
  roomId: string;
  timestamp: string;
  source: LocationSource;
  eventType: "recognition" | "access" | "check-in" | "check-out";
}

export interface FacilityRoom {
  id: string;
  name: string;
  floorId: string;
  floorLabel: string;
  capacity: number;
  color: "teal" | "blue" | "purple" | "amber";
  kind: "workspace" | "meeting" | "lounge" | "corridor" | "entrance" | "exit" | "access";
  bounds: { x: number; y: number; width: number; height: number };
  events: LocationEvent[];
}
