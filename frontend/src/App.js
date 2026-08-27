import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth, roleHome } from "./context/AuthContext";
import { Spinner } from "./components/ui";
import Login from "./pages/Login";
import SelfRegister from "./pages/SelfRegister";
import AdminDashboard from "./pages/AdminDashboard";
import Desk from "./pages/Desk";
import Clinical from "./pages/Clinical";
import PrintPrescription from "./pages/PrintPrescription";
import PrintSlip from "./pages/PrintSlip";

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
  return children;
}

function HomeRedirect() {
  const { user, loading } = useAuth();
  if (loading || user === null) return <FullLoader />;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={roleHome(user.role)} replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HomeRedirect />} />
          <Route path="/login" element={<Login />} />
          <Route path="/self-register" element={<SelfRegister />} />
          <Route path="/admin" element={<Protected roles={["admin"]}><AdminDashboard /></Protected>} />
          <Route path="/desk" element={<Protected roles={["admin", "team_lead", "volunteer"]}><Desk /></Protected>} />
          <Route path="/clinical" element={<Protected roles={["admin", "clinical_desk_operator"]}><Clinical /></Protected>} />
          <Route path="/print/prescription/:id" element={<Protected roles={["admin", "team_lead", "volunteer"]}><PrintPrescription /></Protected>} />
          <Route path="/print/slip/:id" element={<Protected roles={["admin", "clinical_desk_operator"]}><PrintSlip /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
