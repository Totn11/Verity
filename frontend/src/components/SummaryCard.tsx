import type { LucideIcon } from "lucide-react";
import { MoreHorizontal } from "lucide-react";

type SummaryCardProps = {
  label: string;
  value: string;
  note: string;
  icon: LucideIcon;
  tone: "blue" | "green" | "amber" | "purple";
};

export default function SummaryCard({ label, value, note, icon: Icon, tone }: SummaryCardProps) {
  return (
    <article className="stat-card">
      <div className="stat-top">
        <span className={`stat-icon stat-icon-${tone}`}><Icon size={18} /></span>
        <button className="more-button" aria-label={`More about ${label}`}><MoreHorizontal size={19} /></button>
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      <div className="stat-foot">{note}</div>
    </article>
  );
}
