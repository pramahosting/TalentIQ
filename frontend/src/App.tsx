import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import LandingPage    from "./pages/LandingPage";
import LoginPage      from "./pages/LoginPage";
import RegisterPage   from "./pages/RegisterPage";
import DashboardPage  from "./pages/DashboardPage";
import JobHuntPage    from "./pages/JobHuntPage";
import JobIntelPage   from "./pages/JobIntelPage";
import LinkLensPage   from "./pages/LinkLensPage";
import CVIntelPage    from "./pages/CVIntelPage";
import JobLensPage    from "./pages/JobLensPage";
import PublicInterviewPage from "./pages/PublicInterviewPage";
import SettingsPage   from "./pages/SettingsPage";
import AdminSetupPage from "./pages/AdminSetupPage";
import FileManagerPage from "./pages/FileManagerPage";
import AppLayout      from "./components/layout/AppLayout";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="tiq-spinner-wrap"><div className="tiq-spinner" /></div>;
  return user ? <>{children}</> : <Navigate to="/login" replace />;
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="tiq-spinner-wrap"><div className="tiq-spinner" /></div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== "admin") return <Navigate to="/app" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/interview/:token" element={<PublicInterviewPage />} />
            <Route path="/app" element={<PrivateRoute><AppLayout /></PrivateRoute>}>
              <Route index element={<DashboardPage />} />
              <Route path="jobhunt"    element={<JobHuntPage />} />
              <Route path="jobintel"   element={<JobIntelPage />} />
              <Route path="linklens"   element={<LinkLensPage />} />
              <Route path="cvintel"    element={<CVIntelPage />} />
              <Route path="joblens"    element={<JobLensPage />} />
              <Route path="settings"   element={<SettingsPage />} />
              <Route path="admin-setup"  element={<AdminRoute><AdminSetupPage /></AdminRoute>} />
              <Route path="file-manager" element={<AdminRoute><FileManagerPage /></AdminRoute>} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}