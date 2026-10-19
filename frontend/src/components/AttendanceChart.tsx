const week = [
  { day: "Mon", value: 662 },
  { day: "Tue", value: 714 },
  { day: "Wed", value: 689 },
  { day: "Thu", value: 758 },
  { day: "Fri", value: 805 },
  { day: "Sat", value: 524 },
  { day: "Sun", value: 846 },
];

export default function AttendanceChart() {
  const points = week.map(({ value }, index) => {
    const x = (index / (week.length - 1)) * 720;
    const y = 178 - (value / 1000) * 155;
    return `${index ? "L" : "M"}${x} ${y}`;
  }).join(" ");
  const lastY = 178 - (week[week.length - 1].value / 1000) * 155;

  return (
    <>
      <div className="chart-summary"><strong>Daily attendance</strong><span className="chart-summary-note">Last 7 days · demo data</span></div>
      <div className="chart">
        <div className="chart-y-labels"><span>1,000</span><span>750</span><span>500</span><span>250</span><span>0</span></div>
        <div className="chart-area">
          <div className="chart-gridlines"><i /><i /><i /><i /><i /></div>
          <svg viewBox="0 0 720 190" preserveAspectRatio="none" role="img" aria-label="Daily attendance for the last seven days, demonstration data">
            <defs><linearGradient id="attendance-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#43b9ad" stopOpacity=".24" /><stop offset="100%" stopColor="#43b9ad" stopOpacity="0" /></linearGradient></defs>
            <path d={`${points} L720 190 L0 190 Z`} fill="url(#attendance-fill)" />
            <path d={points} fill="none" stroke="#1da99b" strokeWidth="3" vectorEffect="non-scaling-stroke" />
            <circle cx="720" cy={lastY} r="5" fill="#fff" stroke="#1da99b" strokeWidth="3" vectorEffect="non-scaling-stroke" />
          </svg>
          <div className="chart-x-labels">{week.map(({ day }) => <span key={day}>{day}</span>)}</div>
        </div>
      </div>
      <div className="chart-legend"><span><i className="legend-dot teal-dot" /> Daily attendance</span></div>
    </>
  );
}
