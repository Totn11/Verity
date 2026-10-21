import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFacilityProvider } from "./apiFacilityProvider";
import { api } from "../lib/api";
import { usePeople } from "./PeopleContext";
import type { AttendanceCommand, PersonWrite } from "./facilityProvider";

export const facilityQueryKeys = {
  people: ["facility", "people"] as const,
  attendance: (personId?: string) => ["facility", "attendance", personId ?? "all"] as const,
  rooms: ["facility", "rooms"] as const,
  locationEvents: ["facility", "location-events"] as const,
};

export function useFacilityQueries(personId?: string) {
  const demo = usePeople();
  const isApi = import.meta.env.VITE_DATA_SOURCE === "api";
  const source = isApi ? apiFacilityProvider : demo.dataProvider;
  const people = useQuery({
    queryKey: facilityQueryKeys.people,
    queryFn: () => source.listPeople(),
  });
  const attendance = useQuery({
    queryKey: facilityQueryKeys.attendance(personId),
    queryFn: () => source.listAttendance(personId),
  });
  const rooms = useQuery({
    queryKey: facilityQueryKeys.rooms,
    queryFn: () => source.listRooms(),
  });
  const locationEvents = useQuery({
    queryKey: facilityQueryKeys.locationEvents,
    queryFn: () => source.listLocationEvents(),
  });

  return {
    people,
    attendance,
    rooms,
    locationEvents,
    source,
    isApi,
    isPending: people.isPending || attendance.isPending || rooms.isPending || locationEvents.isPending,
    error: people.error ?? attendance.error ?? rooms.error ?? locationEvents.error,
  };
}

export function useAttendanceMutation() {
  const queries = useQueryClient();
  const { dataProvider } = usePeople();
  const source = import.meta.env.VITE_DATA_SOURCE === "api"
    ? apiFacilityProvider
    : dataProvider;

  return useMutation({
    mutationFn: ({ action, ...command }: AttendanceCommand & { action: "Check-in" | "Check-out" }) =>
      action === "Check-in" ? source.checkIn(command) : source.checkOut(command),
    onSuccess: async () => {
      await Promise.all([
        queries.invalidateQueries({ queryKey: facilityQueryKeys.people }),
        queries.invalidateQueries({ queryKey: ["facility", "attendance"] }),
        queries.invalidateQueries({ queryKey: facilityQueryKeys.rooms }),
        queries.invalidateQueries({ queryKey: facilityQueryKeys.locationEvents }),
      ]);
    },
  });
}

export function usePersonMutations() {
  const queries = useQueryClient();
  const { dataProvider } = usePeople();
  const source = import.meta.env.VITE_DATA_SOURCE === "api"
    ? apiFacilityProvider
    : dataProvider;
  const invalidate = () => Promise.all([
    queries.invalidateQueries({ queryKey: facilityQueryKeys.people }),
    queries.invalidateQueries({ queryKey: ["facility", "attendance"] }),
  ]);

  return {
    create: useMutation({
      mutationFn: (input: PersonWrite) => source.createPerson(input),
      onSuccess: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ id, changes }: { id: string; changes: Partial<PersonWrite> }) =>
        source.updatePerson(id, changes),
      onSuccess: invalidate,
    }),
  };
}

export function useAttendanceSummary(from: string, to: string) {
  const enabled = import.meta.env.VITE_DATA_SOURCE === "api";
  return useQuery({
    queryKey: ["facility", "attendance-summary", from, to],
    queryFn: () => api.attendanceSummary(`${from}T00:00:00Z`, `${to}T23:59:59Z`),
    enabled,
  });
}
