import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import { Loading } from "./components/ui";
import AlertsPage from "./pages/Alerts";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import MapPage from "./pages/MapPage";
import Recipients from "./pages/Recipients";
import Reports from "./pages/Reports";
import RwDetail from "./pages/RwDetail";
import SensorDetail from "./pages/SensorDetail";
import Sensors from "./pages/Sensors";
import Thresholds from "./pages/Thresholds";
import Users from "./pages/Users";

export default function App() {
  const { me, ready } = useAuth();
  if (!ready)
    return (
      <div className="p-8">
        <Loading />
      </div>
    );
  if (!me) return <Login />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="peta" element={<MapPage />} />
        <Route path="rw/:id" element={<RwDetail />} />
        <Route path="peringatan" element={<AlertsPage />} />
        <Route path="sensor" element={<Sensors />} />
        <Route path="sensor/:id" element={<SensorDetail />} />
        <Route path="penerima" element={<Recipients />} />
        <Route path="ambang" element={<Thresholds />} />
        <Route path="laporan" element={<Reports />} />
        <Route path="pengguna" element={<Users />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
