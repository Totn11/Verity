import type { ReactNode } from "react";

export default function DataTable({ headers, children, empty = false, emptyMessage = "No attendance records match these filters." }: { headers: string[]; children: ReactNode; empty?: boolean; emptyMessage?: ReactNode }) {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead>
        <tbody>{empty ? <tr><td className="empty-table" colSpan={headers.length}>{emptyMessage}</td></tr> : children}</tbody>
      </table>
    </div>
  );
}
