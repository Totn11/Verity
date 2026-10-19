import type { Person } from "../data/mockData";

export type MockRecognitionResult =
  | { status: "match"; person: Person; confidence: number; simulated: true }
  | { status: "no-match"; simulated: true };

export async function runMockRecognition(personId: string | null, people: Person[]): Promise<MockRecognitionResult> {
  await new Promise((resolve) => window.setTimeout(resolve, 650));
  if (!personId) return { status: "no-match", simulated: true };
  const person = people.find((entry) => entry.id === personId && entry.registrationStatus === "Active");
  if (!person) return { status: "no-match", simulated: true };
  return {
    status: "match",
    person,
    confidence: 98.4,
    simulated: true,
  };
}
