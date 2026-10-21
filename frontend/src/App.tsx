import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import AppLayout from "./components/AppLayout";
import { useAuth } from "./data/AuthContext";
import { usePeople } from "./data/PeopleContext";
import {
  AttendancePage,
  AuditLogsPage,
  CheckInPage,
  DirectoryPage,
  FacilityPage,
  LoginPage,
  PersonProfilePage,
  ReportsPage,
  SettingsPage,
  UsersPage,
} from "./pages/Pages";
import DashboardPage from "./pages/DashboardPage";

function RequireAuth() {
  const { status } = useAuth();
  if (status === "checking") return <div className="auth-loading" role="status">Checking sign-in…</div>;
  return status === "authenticated" ? <Outlet /> : <Navigate to="/login" replace />;
}

function AdministratorOnly({ children }: { children: JSX.Element }) {
  const { role } = usePeople();
  return role === "administrator" ? children : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="attendance" element={<AttendancePage />} />
          <Route path="audit" element={<AdministratorOnly><AuditLogsPage /></AdministratorOnly>} />
          <Route path="people" element={<DirectoryPage />} />
          <Route path="people/:personId" element={<PersonProfilePage />} />
          <Route path="facility" element={<FacilityPage />} />
          <Route path="check-in" element={<CheckInPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="users" element={<AdministratorOnly><UsersPage /></AdministratorOnly>} />
          <Route path="settings" element={<AdministratorOnly><SettingsPage /></AdministratorOnly>} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
