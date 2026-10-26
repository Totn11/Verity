import { useState, type FormEvent } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import {
  Activity, BookOpenCheck, CalendarCheck, ClipboardList, FileBarChart2,
  Fingerprint, GraduationCap, LayoutDashboard, LogOut, Menu, Search,
  Settings, ShieldCheck, ScanFace, UserPlus, Users, X,
} from "lucide-react";
import { useAuth } from "../data/AuthContext";

const navGroups: { label: string; links: { to: string; label: string; icon: LucideIcon; end?: boolean }[] }[] = [
  {
    label: "ATTENDANCE",
    links: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
      { to: "/students", label: "Students", icon: Users },
      { to: "/facial-enrolment", label: "Facial Enrolment", icon: UserPlus },
      { to: "/courses", label: "Courses and Classes", icon: GraduationCap },
      { to: "/attendance", label: "Attendance Sessions", icon: CalendarCheck },
      { to: "/recognition", label: "Live Recognition", icon: ScanFace },
      { to: "/records", label: "Attendance Records", icon: ClipboardList },
      { to: "/reports", label: "Reports", icon: FileBarChart2 },
    ],
  },
  {
    label: "ADMINISTRATION",
    links: [
      { to: "/users", label: "Users and Permissions", icon: ShieldCheck },
      { to: "/audit", label: "Audit Logs", icon: Activity },
      { to: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

const pageTitles: Record<string, string> = {
  "/": "Dashboard",
  "/students": "Students",
  "/facial-enrolment": "Facial Enrolment",
  "/courses": "Courses and Classes",
  "/attendance": "Attendance Sessions",
  "/recognition": "Live Recognition",
  "/records": "Attendance Records",
  "/reports": "Reports",
  "/users": "Users and Permissions",
  "/audit": "Audit Logs",
  "/settings": "Settings",
};

export default function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [search, setSearch] = useState("");
  const location = useLocation();
  const navigate = useNavigate();
  const { user, signOut } = useAuth();
  const [signOutError, setSignOutError] = useState<string | null>(null);
  const pageName = pageTitles[location.pathname] ?? "Verity";
  const initials = user?.email.slice(0, 2).toUpperCase() ?? "VT";

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    navigate(search.trim() ? `/students?search=${encodeURIComponent(search.trim())}` : "/students");
    setSearch("");
  }

  async function handleSignOut() {
    setSignOutError(null);
    try {
      await signOut();
      navigate("/login", { replace: true });
    } catch (error) {
      setSignOutError(error instanceof Error ? error.message : "Unable to sign out.");
    }
  }

  return (
    <div className="app-shell">
      {menuOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
      <aside className={`sidebar ${menuOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <span className="brand-mark"><Fingerprint size={21} strokeWidth={2.3} /></span>
          <span className="brand-name">verity<span>.</span></span>
          <button className="icon-button sidebar-close" aria-label="Close menu" onClick={() => setMenuOpen(false)}><X size={18} /></button>
        </div>
        <div className="workspace-select" aria-label="Current workspace">
          <span className="workspace-icon"><BookOpenCheck size={17} /></span>
          <span className="workspace-copy"><strong>Classroom workspace</strong><small>Attendance management</small></span>
        </div>
        <nav className="sidebar-nav" aria-label="Main navigation">
          {navGroups.map((group) => (
            <div className="nav-group" key={group.label}>
              <div className="nav-label">{group.label}</div>
              {group.links.map(({ to, label, icon: Icon, end }) => (
                <NavLink key={to} to={to} end={end} onClick={() => setMenuOpen(false)} className={({ isActive }) => `nav-link ${isActive ? "nav-link-active" : ""}`}>
                  <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="help-card">
            <div className="help-icon"><ShieldCheck size={17} /></div>
            <strong>Privacy-first attendance</strong>
            <span>Camera preview is local. Recognition and offline sync are not enabled.</span>
          </div>
          <button className="profile-menu" onClick={() => void handleSignOut()} title="Sign out">
            <span className="admin-avatar">{initials}</span>
            <span className="profile-copy"><strong>{user?.email ?? "Signed-in account"}</strong><small>Authenticated account</small></span>
            <LogOut size={15} />
          </button>
          {signOutError && <p role="alert" className="sign-out-error">{signOutError}</p>}
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMenuOpen(true)}><Menu size={21} /></button>
          <div className="breadcrumbs"><span>Verity</span><span className="crumb-slash">/</span><strong>{pageName}</strong></div>
          <div className="topbar-actions">
            <form className="search-field" onSubmit={submitSearch}><Search size={16} /><input aria-label="Search students" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search students..." /><kbd>↵</kbd></form>
            <span className="topbar-divider" />
            <span className="topbar-date">{new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" }).format(new Date())}</span>
          </div>
        </header>
        <div className="content-wrap"><Outlet /></div>
      </main>
    </div>
  );
}
