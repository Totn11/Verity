import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import AppLayout from "./components/AppLayout";
import { useAuth } from "./data/AuthContext";
import {
  AttendanceRecordsPage,
  AttendanceSessionsPage,
  AuditLogsPage,
  CoursesPage,
  FacialEnrolmentPage,
  LoginPage,
  RecognitionPage,
  ReportsPage,
  SettingsPage,
  StudentsPage,
  UsersPage,
} from "./pages/ClassroomPages";
import DashboardPage from "./pages/DashboardPage";

function RequireAuth() {
  const { status } = useAuth();
  if (status === "checking") return <div className="auth-loading" role="status">Checking sign-in…</div>;
  return status === "authenticated" ? <Outlet /> : <Navigate to="/login" replace />;
}

function AdministratorOnly({ children }: { children: JSX.Element }) {
  const { user } = useAuth();
  return user?.role === "admin" ? children : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="students" element={<StudentsPage />} />
          <Route path="facial-enrolment" element={<AdministratorOnly><FacialEnrolmentPage /></AdministratorOnly>} />
          <Route path="courses" element={<CoursesPage />} />
          <Route path="attendance" element={<AttendanceSessionsPage />} />
          <Route path="recognition" element={<RecognitionPage />} />
          <Route path="records" element={<AttendanceRecordsPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="audit" element={<AdministratorOnly><AuditLogsPage /></AdministratorOnly>} />
          <Route path="users" element={<AdministratorOnly><UsersPage /></AdministratorOnly>} />
          <Route path="settings" element={<AdministratorOnly><SettingsPage /></AdministratorOnly>} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
