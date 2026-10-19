import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./components/AppLayout";
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

function AdministratorOnly({ children }: { children: JSX.Element }) {
  const { role } = usePeople();
  return role === "administrator" ? children : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
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
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
