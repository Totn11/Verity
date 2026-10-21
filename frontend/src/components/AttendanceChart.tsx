const demoWeek = [
  { day: "Mon", value: 662 },
  { day: "Tue", value: 714 },
  { day: "Wed", value: 689 },
  { day: "Thu", value: 758 },
  { day: "Fri", value: 805 },
  { day: "Sat", value: 524 },
  { day: "Sun", value: 846 },
];

type AttendancePoint = { day: string; value: number };

export default function AttendanceChart({
  data,
  isDemo = true,
}: {
  data?: AttendancePoint[];
  isDemo?: boolean;
}) {
  const week = data ?? demoWeek;
  const maximum = Math.max(1, Math.ceil(Math.max(...week.map(({ value }) => value), 0) / 250) * 250);
  const points = week.map(({ value }, index) => {
    const x = (index / (week.length - 1)) * 720;
    const y = 178 - (value / maximum) * 155;
    return `${index ? "L" : "M"}${x} ${y}`;
  }).join(" ");
  const lastY = 178 - (week[week.length - 1].value / maximum) * 155;
  const labels = [maximum, Math.round(maximum * 0.75), Math.round(maximum * 0.5), Math.round(maximum * 0.25), 0];

  return (
    <>
      <div className="chart-summary"><strong>Daily check-ins</strong><span className="chart-summary-note">Last 7 days · {isDemo ? "demo data" : "API data"}</span></div>
      <div className="chart">
        <div className="chart-y-labels">{labels.map((label, index) => <span key={index}>{label.toLocaleString()}</span>)}</div>
        <div className="chart-area">
          <div className="chart-gridlines"><i /><i /><i /><i /><i /></div>
          <svg viewBox="0 0 720 190" preserveAspectRatio="none" role="img" aria-label={`Daily check-ins for the last seven days, ${isDemo ? "demo" : "API"} data`}>
            <defs><linearGradient id="attendance-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#43b9ad" stopOpacity=".24" /><stop offset="100%" stopColor="#43b9ad" stopOpacity="0" /></linearGradient></defs>
            <path d={`${points} L720 190 L0 190 Z`} fill="url(#attendance-fill)" />
            <path d={points} fill="none" stroke="#1da99b" strokeWidth="3" vectorEffect="non-scaling-stroke" />
            <circle cx="720" cy={lastY} r="5" fill="#fff" stroke="#1da99b" strokeWidth="3" vectorEffect="non-scaling-stroke" />
          </svg>
          <div className="chart-x-labels">{week.map(({ day }, index) => <span key={`${day}-${index}`}>{day}</span>)}</div>
        </div>
      </div>
      <div className="chart-legend"><span><i className="legend-dot teal-dot" /> Daily attendance</span></div>
    </>
  );
}
