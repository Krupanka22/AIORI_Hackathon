import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { useWebSocket } from './useWebSocket';
import Sidebar from './Sidebar';
import Dashboard from './pages/Dashboard';
import DevicesPage from './pages/DevicesPage';
import IPv6Page from './pages/IPv6Page';
import NetworkPage from './pages/NetworkPage';
import AIPage from './pages/AIPage';
import AlertsPage from './pages/AlertsPage';
import BlockchainPage from './pages/BlockchainPage';
import ExperimentsPage from './pages/ExperimentsPage';
import './index.css';

export default function App() {
  const { connected, subscribe } = useWebSocket();

  return (
    <BrowserRouter>
      <div className="app-shell">
        <Sidebar wsConnected={connected} />
        <main className="app-main">
          <Routes>
            <Route path="/" element={<Dashboard subscribe={subscribe} />} />
            <Route path="/devices" element={<DevicesPage />} />
            <Route path="/ipv6" element={<IPv6Page />} />
            <Route path="/network" element={<NetworkPage />} />
            <Route path="/ai" element={<AIPage />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/blockchain" element={<BlockchainPage />} />
            <Route path="/experiments" element={<ExperimentsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
