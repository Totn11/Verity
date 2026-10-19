import { useState, type FormEvent } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import {
  Activity, Bell, Building2, ChevronDown, ClipboardCheck, FileBarChart2,
  Fingerprint, LayoutDashboard, LogOut, Menu, Search, Settings, Users, X,
  ScrollText, UserCog, ScanFace,
} from "lucide-react";
import { usePeople } from "../data/PeopleContext";

const navGroups: { label: string; links: { to: string; label: string; icon: LucideIcon; badge?: string; end?: boolean }[] }[] = [
  {
    label: "WORKSPACE",
    links: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
      { to: "/attendance", label: "Attendance", icon: Activity },
      { to: "/people", label: "People", icon: Users },
      { to: "/facility", label: "Facility map", icon: Building2 },
      { to: "/reports", label: "Reports", icon: FileBarChart2 },
      { to: "/check-in", label: "Recognition terminal", icon: ScanFace },
    ],
  },
  {
    label: "ADMINISTRATION",
    links: [
      { to: "/users", label: "User management", icon: UserCog },
      { to: "/audit", label: "Audit logs", icon: ScrollText },
      { to: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

export default function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { role, setRole } = usePeople();
  const pageTitles: Record<string, string> = {
    "/": "Dashboard",
    "/attendance": "Attendance",
    "/people": "People",
    "/facility": "Facility map",
    "/reports": "Reports",
    "/check-in": "Recognition terminal",
    "/users": "User management",
    "/audit": "Audit logs",
    "/settings": "Settings",
    "/login": "Login",
  };
  const pageName = pageTitles[location.pathname] ?? (location.pathname.startsWith("/people/") ? "Person profile" : "Dashboard");

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    navigate(search.trim() ? `/people?search=${encodeURIComponent(search.trim())}` : "/people");
    setSearch("");
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
        <button className="workspace-select">
          <span className="workspace-icon"><Building2 size={17} /></span>
          <span className="workspace-copy"><strong>Northstar HQ</strong><small>Enterprise plan</small></span>
          <ChevronDown size={15} className="workspace-chevron" />
        </button>
        <nav className="sidebar-nav" aria-label="Main navigation">
          {navGroups.filter((group) => role === "administrator" || group.label !== "ADMINISTRATION").map((group) => (
            <div className="nav-group" key={group.label}>
              <div className="nav-label">{group.label}</div>
              {group.links.map(({ to, label, icon: Icon, badge, end }) => (
                <NavLink key={to} to={to} end={end} onClick={() => setMenuOpen(false)} className={({ isActive }) => `nav-link ${isActive ? "nav-link-active" : ""}`}>
                  <Icon size={18} strokeWidth={1.8} />
                  <span>{label}</span>
                  {badge && <span className="nav-live">{badge}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="help-card">
            <div className="help-icon"><ClipboardCheck size={17} /></div>
            <strong>Need a hand?</strong>
            <span>Visit the help center for setup guides.</span>
            <a href="mailto:support@verity.example">Get support <span aria-hidden="true">↗</span></a>
          </div>
          <label className="demo-role-control sidebar-demo-role">Prototype role<select aria-label="Switch prototype role" value={role} onChange={(event) => setRole(event.target.value === "staff" ? "staff" : "administrator")}><option value="administrator">Administrator</option><option value="staff">Staff</option></select><small>UI preview only—not access control.</small></label>
          <Link className="profile-menu" to="/login" title="Sign out and return to login">
            <span className="admin-avatar">{role === "administrator" ? "SC" : "FS"}</span>
            <span className="profile-copy"><strong>{role === "administrator" ? "Sarah Chen" : "Facility staff"}</strong><small>{role === "administrator" ? "Administrator · demo" : "Staff · demo view"}</small></span>
            <LogOut size={15} />
          </Link>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMenuOpen(true)}><Menu size={21} /></button>
          <div className="breadcrumbs"><span>Northstar HQ</span><span className="crumb-slash">/</span><strong>{pageName}</strong></div>
          <div className="topbar-actions">
            <form className="search-field" onSubmit={submitSearch}><Search size={16} /><input aria-label="Search people" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search people..." /><kbd>↵</kbd></form>
            <div className="topbar-popover-wrap">
              <button className="icon-button notification-button" aria-label="Notifications" aria-expanded={notificationsOpen} onClick={() => setNotificationsOpen(!notificationsOpen)}><Bell size={18} /><i /></button>
              {notificationsOpen && <div className="topbar-popover"><strong>Notifications</strong><p><span className="popover-dot amber" />1 unmatched demo recognition needs review.</p><p><span className="popover-dot teal" />Demo activity refreshed at 9:45 AM.</p><button onClick={() => setNotificationsOpen(false)}>Dismiss</button></div>}
            </div>
            <span className="topbar-divider" />
            <span className="topbar-date">{new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" }).format(new Date())}</span>
            <div className="topbar-popover-wrap profile-trigger-wrap">
              <button className="topbar-profile" aria-label="Demo account menu" aria-expanded={profileOpen} onClick={() => setProfileOpen(!profileOpen)}><span className="admin-avatar">{role === "administrator" ? "SC" : "FS"}</span><ChevronDown size={13} /></button>
              {profileOpen && <div className="topbar-popover profile-popover"><strong>{role === "administrator" ? "Sarah Chen" : "Facility staff"}</strong><small>{role === "administrator" ? "Facility administrator" : "Ordinary staff view"}</small><label className="demo-role-control">Prototype role<select aria-label="Switch prototype role" value={role} onChange={(event) => setRole(event.target.value === "staff" ? "staff" : "administrator")}><option value="administrator">Administrator</option><option value="staff">Staff</option></select></label><p className="demo-role-note">View-only UI simulation. This is not authentication or production access control.</p>{role === "administrator" && <Link to="/settings" onClick={() => setProfileOpen(false)}><Settings size={14} /> Account settings</Link>}<Link to="/login" onClick={() => setProfileOpen(false)}><LogOut size={14} /> Sign out</Link></div>}
            </div>
          </div>
        </header>
        <div className="content-wrap"><Outlet /></div>
      </main>
    </div>
  );
}
