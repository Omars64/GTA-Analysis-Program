import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import Dashboard from './pages/Dashboard.jsx'
import History from './pages/History.jsx'
import Settings from './pages/Settings.jsx'
import VehicleBrowser from './pages/VehicleBrowser.jsx'
import IntelHub from './pages/IntelHub.jsx'
import AuthGate from './components/AuthGate.jsx'

export default function App() {
  return (
    <AuthGate><Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/history" element={<History />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/vehicles" element={<VehicleBrowser />} />
        <Route path="/hub" element={<IntelHub />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout></AuthGate>
  )
}
