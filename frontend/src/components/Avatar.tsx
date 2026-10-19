import type { Person } from "../data/mockData";

export default function Avatar({ person, size = "md" }: { person: Pick<Person, "avatar" | "initials" | "name">; size?: "sm" | "md" | "lg" }) {
  return (
    <span className={`avatar avatar-${size}`}>
      {person.avatar ? <img src={person.avatar} alt={person.name} /> : person.initials}
    </span>
  );
}
