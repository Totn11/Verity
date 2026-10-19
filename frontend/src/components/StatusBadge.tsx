type Props = { children: string; tone?: "green" | "red" | "amber" | "blue" | "gray" };

export default function StatusBadge({ children, tone = "gray" }: Props) {
  return <span className={`status-badge status-${tone}`}><span className="status-dot" />{children}</span>;
}
