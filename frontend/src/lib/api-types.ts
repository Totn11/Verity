export type PersonStatus = "active" | "inactive" | "visitor";
export type AttendanceKind = "check_in" | "check_out";
export type EventSource = "terminal" | "manual" | "import";

export type Page<T> = {
  items: T[];
  next_cursor: string | null;
};

export type Person = {
  id: string;
  external_ref: string;
  full_name: string;
  email: string;
  phone: string;
  department: string;
  title: string;
  status: PersonStatus;
  photo_url: string | null;
  created_at: string;
  updated_at: string;
};

export type Room = {
  id: string;
  code: string;
  name: string;
  floor: number;
  capacity: number;
  pos_x: number;
  pos_y: number;
};

export type AttendanceEvent = {
  id: string;
  person_id: string;
  kind: AttendanceKind;
  occurred_at: string;
  source: EventSource;
  source_event_id: string | null;
  room_id: string | null;
  actor_user_id: string | null;
  created_at: string;
};

export type AttendanceSummary = {
  day: string;
  room_id: string | null;
  room_code: string | null;
  room_name: string | null;
  check_ins: number;
  check_outs: number;
};

export type AttendanceWrite = {
  person_id: string;
  room_id?: string | null;
  occurred_at?: string;
};
