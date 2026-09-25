import React, { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth, roleHome } from "./context/AuthContext";
import { ADMIN_ROLES, DESK_ROLES, CLINICAL_ROLES, LEAD_ROLES } from "./constants/roles";
import { Spinner } from "./components/ui";
import ErrorBoundary from "./components/ErrorBoundary";
import Layout from "./components/Layout";
import Login from "./pages/Login";
const SelfRegister = lazy(() => import("./pages/SelfRegister"));
const AdminDashboard = lazy(() => import("./pages/AdminDashboard"));
const Desk = lazy(() => import("./pages/Desk"));
const Clinical = lazy(() => import("./pages/Clinical"));
const Board = lazy(() => import("./pages/Board"));
const Team = lazy(() => import("./pages/Team"));

function FullLoader() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <Spinner className="w-8 h-8 text-emerald-500" />
    </div>
  );
}

function Protected({ roles, children }) {
  const { user, loading } = useAuth();
  if (loading || user === null) return <FullLoader />;
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to={roleHome(user.role)} replace />;
  if (user.must_change_pin) return <Layout />;
  return children;
}

function Home() {
  const { user, loading } = useAuth();
  if (loading || user === null) return <FullLoader />;
  if (!user) return <SelfRegister />;
  return <Navigate to={roleHome(user.role)} replace />;
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <BrowserRouter>
        <Suspense fallback={<FullLoader />}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/self-register" element={<SelfRegister />} />
          <Route path="/admin" element={<Protected roles={ADMIN_ROLES}><AdminDashboard /></Protected>} />
          <Route path="/desk" element={<Protected roles={DESK_ROLES}><Desk /></Protected>} />
          <Route path="/clinical" element={<Protected roles={CLINICAL_ROLES}><Clinical /></Protected>} />
          <Route path="/analytics" element={<Protected roles={LEAD_ROLES}><Board /></Protected>} />
          <Route path="/board" element={<Navigate to="/analytics" replace />} />
          <Route path="/team" element={<Protected roles={LEAD_ROLES}><Team /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </ErrorBoundary>
  );
}
